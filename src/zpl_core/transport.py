"""Print transports for ZPL output: TCP 9100, USB printer queue, Windows spooler, file preview.

Raw ZPL over TCP/USB reaches the printer's ZPL interpreter directly (the
Link-OS way). Sending to a Windows print queue works only when the queue
driver is a Zebra ZPL driver — otherwise the job is treated as a document and
the printer prints it as text, so we always return a rendering preview too.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import tempfile
import unicodedata
from pathlib import Path

SCRATCH = Path(os.environ.get("ZPL_CORE_OUT") or os.environ.get("ZEBRA_MCP_OUT")
               or Path(tempfile.gettempdir()) / "zpl-core")
SCRATCH.mkdir(parents=True, exist_ok=True)

TCP_DEFAULT_PORT = 9100  # Link-OS/Zebra 9100 raw port


def _clean_zpl(zpl: str, encoding: str = "") -> bytes:
    """Encode ZPL text to bytes.

    Auto: ^CI28/^CI29/^CI30 + non-ASCII -> UTF-8 bytes (raw ^FD data is printed
    through as-is; a ^CI28 label with a TrueType CJK font such as
    E:SIMSUN.TTF needs the UTF-8 codepoints on the wire, cp1252 would replace
    them with '?'). Otherwise cp1252 as before. encoding= overrides.
    """
    enc = encoding or ""
    if not enc:
        if re.search(r"\^CI(?:28|29|30)\b", zpl) and any(ord(c) > 127 for c in zpl):
            enc = "utf-8"
        else:
            enc = "cp1252"
    try:
        return zpl.encode(enc, errors="replace")
    except LookupError:
        return zpl.encode("cp1252", errors="replace")


def send_tcp(host: str, zpl: str, port: int = TCP_DEFAULT_PORT, timeout: float = 5.0) -> dict:
    """Send raw ZPL to an Ethernet/Wi-Fi Zebra printer on the 9100 port."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            data = _clean_zpl(zpl)
            s.sendall(data)
            # Zebra 9100 usually does not echo; wait briefly for possible error text
            s.settimeout(1.0)
            resp = b""
            try:
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
                    if len(resp) > 4096:
                        break
            except socket.timeout:
                pass
        return {"ok": True, "transport": f"tcp://{host}:{port}",
                "bytes_sent": len(data),
                "response": resp.decode("cp1252", "replace").strip() or None,
                "note": "no ^XA error echo received" if not resp else None}
    except OSError as e:
        return {"ok": False, "transport": f"tcp://{host}:{port}",
                "error": f"{type(e).__name__}: {e}",
                "hint": "check printer IP (get it with printer_status sgd 'device.ip.address'), "
                        "port 9100 (Zebra default), and that the host can reach the printer"}


# ---------------------------------------------------------------------------
# Closed loop: did it actually print? (~~HS p.233-236, ^HV p.239)
# ---------------------------------------------------------------------------
STX, ETX = 0x02, 0x03

# ~HS string 1: aaa,b,c,dddd,eee,f,g,h,iii,j,k,l   (p.233)
# ~HS string 2: mmm,n,o,p,q,r,s,t,uuuuuuuu,v,www   (p.234-235)
# ~HS string 3: xxxx,y                             (p.236)
_BAUD = {0b0000: 110, 0b0001: 300, 0b0010: 600, 0b0011: 1200, 0b0100: 2400,
         0b0101: 4800, 0b0110: 9600, 0b0111: 19200, 0b1000: 28800, 0b1001: 38400,
         0b1010: 57600, 0b1011: 14400}
_PRINT_MODES = {"0": "rewind", "1": "peel-off", "2": "tear-off", "3": "cutter",
                "4": "applicator", "5": "delayed cut", "6": "linerless peel",
                "7": "linerless rewind", "8": "partial cutter", "9": "rfid",
                "K": "kiosk", "S": "kiosk cutstream", "A": "kiosk cutstream"}

# flag -> (human name, severity, ZBI II status code from knowledge.STATUS_NOTES)
_FLAG_ERRORS = (
    ("paper_out",         "PAPER OUT",            "error", "0003"),
    ("head_open",         "HEAD OPEN",            "error", "0002"),
    ("ribbon_out",        "RIBBON OUT",           "error", None),
    ("over_temperature",  "TOO HOT",              "error", "8000"),
    ("under_temperature", "HEAD COLD",            "warn",  "0008"),
    ("paused",            "PAUSED",               "warn",  "0010"),
    ("corrupt_ram",       "CONFIGURATION LOST",   "warn",  "0004"),
    ("buffer_full",       "RECEIVE BUFFER FULL",  "warn",  None),
    ("partial_format",    "PARTIAL FORMAT",       "warn",  None),
)

# From the ~HS note (p.233): in these states the printer stays silent, so an
# empty answer is itself a diagnosis, not a transport bug.
_SILENT_STATES = ("MEDIA OUT", "RIBBON OUT", "HEAD OPEN", "REWINDER FULL",
                  "HEAD OVER-TEMPERATURE")


def parse_host_status(raw) -> dict:
    """Parse the three ``~HS`` strings into named fields (p.233-236).

    Pure function on purpose: the status parser is the part most likely to be
    wrong and the part you cannot test against a printer that is misbehaving.
    """
    if isinstance(raw, bytes):
        text = raw.decode("latin-1", "replace")
    else:
        text = str(raw or "")
    parts = [p.strip(" \r\n") for p in text.split(chr(ETX))]
    strings = [p.lstrip(chr(STX)) for p in parts if p.strip(" \r\n" + chr(STX))]
    out = {"ok": False, "raw": text, "strings": strings, "errors": [], "flags": {}}

    def nums(seg, count):
        vals = (seg.split(",") + [""] * count)[:count]
        return vals

    flags = out["flags"]
    try:
        s1 = nums(strings[0], 12)
        comm = int(s1[0] or 0)
        flags.update({
            "paper_out": s1[1] == "1",
            "paused": s1[2] == "1",
            "buffer_full": s1[5] == "1",
            "diagnostic_mode": s1[6] == "1",
            "partial_format": s1[7] == "1",
            "corrupt_ram": s1[9] == "1",
            "under_temperature": s1[10] == "1",
            "over_temperature": s1[11] == "1",
        })
        out.update({
            "label_length_dots": int(s1[3] or 0),
            "formats_in_buffer": int(s1[4] or 0),
            # baud is a8 a2 a1 a0 (p.234): bit 7 then bits 2..0
            "baud": _BAUD.get(((comm >> 7) & 1) << 3 | ((comm >> 2) & 1) << 2
                              | ((comm >> 1) & 1) << 1 | (comm & 1)),
            "data_bits": 8 if comm & 0b00001000 else 7,
            "stop_bits": 1 if comm & 0b00010000 else 2,
            "parity": "even" if comm & 0b01000000 else "odd",
            "handshake": "dtr" if comm & 0b10000000 else "xon/xoff",
        })
    except (IndexError, ValueError):
        return out

    try:
        s2 = nums(strings[1], 11)
        mmm = int(s2[0] or 0)
        flags.update({
            "head_open": s2[2] == "1",           # "head in up position"
            "ribbon_out": s2[3] == "1",
            "thermal_transfer": s2[4] == "1",
            "label_waiting": s2[7] == "1",
        })
        out.update({
            "media_type": "continuous" if mmm & 0b10000000 else "die-cut",
            "sensor_profile": bool(mmm & 0b01000000),
            "print_mode": _PRINT_MODES.get(str(s2[5]).upper(), s2[5]),
            "print_width_mode": s2[6],
            "labels_remaining": int(s2[8] or 0),
            "graphics_stored": int(s2[10] or 0) if s2[10].isdigit() else 0,
        })
    except (IndexError, ValueError):
        return out

    try:
        s3 = nums(strings[2], 2)
        out["static_ram"] = s3[1].strip() == "1"
    except (IndexError, ValueError):
        pass

    errors = []
    for key, name, severity, zbi in _FLAG_ERRORS:
        if flags.get(key):
            errors.append({"flag": key, "name": name, "severity": severity,
                           "zbi_code": zbi})
    out["errors"] = errors
    out["ready"] = not any(e["severity"] == "error" for e in errors) and \
        not flags.get("paused")
    out["idle"] = out.get("formats_in_buffer", 0) == 0 and \
        out.get("labels_remaining", 0) == 0
    out["ok"] = len(strings) >= 2
    return out


def _read_socket(sock, *, deadline: float, stop: bytes | None = None,
                 min_bytes: int = 1) -> bytes:
    """Read until `stop` appears, `min_bytes` arrived, or the deadline passes."""
    import time
    buf = b""
    while time.time() < deadline:
        sock.settimeout(max(0.05, min(0.5, deadline - time.time())))
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            if len(buf) >= min_bytes and stop is None:
                break
            continue
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if stop is not None and buf.count(stop) >= max(1, min_bytes):
            break
    return buf


def query_status(host: str, *, port: int = TCP_DEFAULT_PORT, timeout: float = 3.0) -> dict:
    """Ask the printer for ``~HS`` and parse the answer.

    An empty reply is *not* automatically a network error: per the manual (p.233)
    the printer stays silent when media or ribbon is out, the head is open, the
    rewinder is full or the head is over-temperature. We report that explicitly.
    """
    import time
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(b"~HS")
            raw = _read_socket(s, deadline=time.time() + timeout, stop=bytes([ETX]),
                               min_bytes=3)
    except OSError as exc:
        return {"ok": False, "stage": "connect", "transport": f"tcp://{host}:{port}",
                "error": f"{type(exc).__name__}: {exc}",
                "hint": "check the IP/port; on a Link-OS printer 9100 is the raw port"}
    res = parse_host_status(raw)
    res["transport"] = f"tcp://{host}:{port}"
    if not raw:
        res["no_response"] = True
        res["hint"] = ("the printer answered nothing — per ~HS p.233 that happens when it is "
                       "in " + ", ".join(_SILENT_STATES) + ". Check the printer's display.")
    return res


def send_and_verify(host: str, zpl: str, *, port: int = TCP_DEFAULT_PORT,
                    timeout: float = 5.0, attempts: int = 2,
                    require_ready: bool = True, wait_idle: bool = True,
                    max_wait: float = 30.0, poll: float = 0.4) -> dict:
    """Send a label and prove it printed: preflight, send, poll until idle.

    ``send_tcp`` only proves the bytes left the host. This adds the two things a
    headless terminal needs: refuse to send when the printer is not ready (paper
    out, head open, paused), and keep asking ``~HS`` until the receive buffer and
    the label batch are empty, then report the final state.

    Returns ``{ok, stage, sent_bytes, attempts, status, timeline}``; ``stage`` is
    ``preflight`` / ``send`` / ``print`` so the caller can tell the three failure
    modes apart.
    """
    import time
    timeline = []
    status = query_status(host, port=port, timeout=timeout) if require_ready else None
    if status is not None:
        timeline.append({"at": "preflight", "ok": status.get("ok"),
                         "ready": status.get("ready"), "errors": status.get("errors")})
        if not status.get("ok"):
            return {"ok": False, "stage": "preflight", "status": status,
                    "error": status.get("error") or "no usable ~HS reply",
                    "hint": status.get("hint"), "timeline": timeline}
        if not status.get("ready"):
            return {"ok": False, "stage": "preflight", "status": status,
                    "error": "printer not ready: " + ", ".join(
                        e["name"] for e in status.get("errors") or [{"name": "paused"}]),
                    "hint": "fix the printer state (media/ribbon/head/pause) and retry",
                    "timeline": timeline}

    sent = 0
    last_err = None
    for attempt in range(1, max(1, attempts) + 1):
        res = send_tcp(host, zpl, port=port, timeout=timeout)
        timeline.append({"at": f"send#{attempt}", "ok": res.get("ok"),
                         "bytes": res.get("bytes_sent"), "error": res.get("error")})
        if res.get("ok"):
            sent = res.get("bytes_sent", 0)
            last_err = None
            break
        last_err = res
        time.sleep(poll)

    if last_err is not None:
        return {"ok": False, "stage": "send", "attempts": attempts, "status": status,
                "error": last_err.get("error"), "hint": last_err.get("hint"),
                "timeline": timeline}

    if not wait_idle:
        return {"ok": True, "stage": "sent", "sent_bytes": sent, "status": status,
                "timeline": timeline, "note": "wait_idle=False: bytes left the host only"}

    deadline = time.time() + max_wait
    final = status or {}
    while time.time() < deadline:
        time.sleep(poll)
        final = query_status(host, port=port, timeout=timeout)
        if final.get("no_response"):
            continue
        if final.get("errors"):
            break
        if final.get("idle"):
            break
    timeline.append({"at": "final", "ok": final.get("ok"), "idle": final.get("idle"),
                     "errors": final.get("errors")})

    failed = [e for e in final.get("errors") or [] if e["severity"] == "error"]
    if failed:
        return {"ok": False, "stage": "print", "sent_bytes": sent, "status": final,
                "error": "printer reported: " + ", ".join(e["name"] for e in failed),
                "timeline": timeline}
    if not final.get("idle"):
        return {"ok": False, "stage": "print", "sent_bytes": sent, "status": final,
                "error": f"still busy after {max_wait:g}s "
                         f"({final.get('labels_remaining')} labels, "
                         f"{final.get('formats_in_buffer')} formats queued)",
                "timeline": timeline}
    return {"ok": True, "stage": "printed", "sent_bytes": sent, "status": final,
            "timeline": timeline}


def send_and_read(host: str, zpl: str, *, port: int = TCP_DEFAULT_PORT,
                  timeout: float = 5.0, read_timeout: float = 3.0,
                  expect: dict | None = None) -> dict:
    """Send a job and read what the printer sends back (that is what ^HV does).

    ``expect = {"header": "CODE[", "terminator": "]"}` turns the reply into a list
    of field values, so a terminal can compare the *printer's* copy of the data
    with what it asked for instead of trusting its own log.
    """
    import time
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            data = _clean_zpl(zpl)
            s.sendall(data)
            raw = _read_socket(s, deadline=time.time() + read_timeout, stop=None)
    except OSError as exc:
        return {"ok": False, "transport": f"tcp://{host}:{port}",
                "error": f"{type(exc).__name__}: {exc}"}
    text = raw.decode("latin-1", "replace").replace(chr(STX), "").replace(chr(ETX), "")
    res = {"ok": True, "transport": f"tcp://{host}:{port}", "bytes_sent": len(data),
           "reply": text, "values": []}
    if expect:
        header = str(expect.get("header", ""))
        term = str(expect.get("terminator", ""))
        pat = re.escape(header) + r"(.*?)" + re.escape(term)
        res["values"] = re.findall(pat, text, re.S)
        res["matched"] = bool(res["values"])
    return res


def list_windows_printers() -> list[dict]:
    """Enumerate local Windows printers with PowerShell (stable; ctypes winspool
    crashes some Python builds).

    [Console]::OutputEncoding forces UTF-8 so non-ASCII queue names survive the
    trip through powershell.exe on a Chinese/Japanese Windows (default console
    code page would mangle them).
    """
    ps = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
          "Get-Printer | Select-Object Name,PortName,DriverName,PrinterStatus,Shared "
          "| ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, timeout=30)
        import json
        out = r.stdout.decode("utf-8", "replace").strip()
        if not out:
            return []
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


def _find_printer(name_query: str) -> dict | None:
    printers = list_windows_printers()
    q = name_query.lower()
    for p in printers:
        if not p.get("Name"):        # skip the {"error": ...} entry PowerShell failures return
            continue
        n = str(p["Name"]).lower()
        if q == n or q in n:
            return p
    return None


# --- Windows RAW spooling ------------------------------------------------------
# PowerShell has no cmdlet that spools raw bytes to a named queue (Print-File
# only exists on some hosts with the PrintManagement module, and Out-Printer
# sends text). winspool.drv's WritePrinter with datatype RAW is the documented
# way and works with any ZPL queue, driver-agnostic.
def _spool_raw_windows(printer_name: str, data: bytes, doc_name: str = "zebra-mcp") -> int:
    import ctypes
    from ctypes import wintypes

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [("pDocName", wintypes.LPWSTR),
                    ("pOutputFile", wintypes.LPWSTR),
                    ("pDatatype", wintypes.LPWSTR)]

    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE),
                                      ctypes.c_void_p]
    winspool.OpenPrinterW.restype = wintypes.BOOL
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                          ctypes.POINTER(DOC_INFO_1)]
    winspool.StartDocPrinterW.restype = wintypes.DWORD
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD)]
    winspool.WritePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]

    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(printer_name, ctypes.byref(handle), None):
        raise OSError(ctypes.get_last_error(), f"OpenPrinter failed for '{printer_name}'")
    try:
        di = DOC_INFO_1(doc_name, None, "RAW")
        job = winspool.StartDocPrinterW(handle, 1, ctypes.byref(di))
        if not job:
            raise OSError(ctypes.get_last_error(), "StartDocPrinter failed")
        try:
            if not winspool.StartPagePrinter(handle):
                raise OSError(ctypes.get_last_error(), "StartPagePrinter failed")
            written = wintypes.DWORD(0)
            buf = ctypes.create_string_buffer(data, len(data))
            if not winspool.WritePrinter(handle, buf, len(data), ctypes.byref(written)):
                raise OSError(ctypes.get_last_error(), "WritePrinter failed")
            winspool.EndPagePrinter(handle)
            return int(job)
        finally:
            winspool.EndDocPrinter(handle)
    finally:
        winspool.ClosePrinter(handle)


def send_windows_printer(printer_name: str, zpl: str) -> dict:
    """Send raw ZPL to a Windows printer queue (RAW datatype, driver-agnostic).

    The queue's driver normally passes RAW jobs straight to the printer, so a
    Zebra ZPL queue prints the label. If the queue is bound to a non-ZPL driver
    (e.g. a PDF/virtual printer) the job is accepted but nothing meaningful is
    printed — the preview file is the ground truth in that case.
    """
    printer = _find_printer(printer_name)
    if printer is None:
        avail = [p["Name"] for p in list_windows_printers() if p.get("Name")]
        return {"ok": False, "transport": "windows_spool", "printer": printer_name,
                "error": "printer not found", "available_printers": avail}
    data = _clean_zpl(zpl)
    path = SCRATCH / f"zpl_job_{os.getpid()}.prn"
    path.write_bytes(data)
    drv = str(printer.get("DriverName", ""))
    zebra_drv = bool(re.search(r"zebra|zd(esigner)?", drv, re.I))
    try:
        job = _spool_raw_windows(str(printer["Name"]), data)
        return {"ok": True, "transport": "windows_spool", "printer": printer["Name"],
                "driver": drv, "zebra_zpl_driver_detected": zebra_drv,
                "datatype": "RAW", "job_id": job, "bytes_sent": len(data),
                "preview": str(path),
                "hint": None if zebra_drv else
                "driver does not look like a Zebra ZPL driver — the queue may rasterize "
                "the RAW job; check the .prn preview or use a TCP raw transport"}
    except Exception as e:
        return {"ok": False, "transport": "windows_spool", "printer": printer["Name"],
                "driver": drv, "error": f"{type(e).__name__}: {e}", "preview": str(path),
                "hint": "RAW spooling needs the queue to accept raw bytes; for Zebra "
                        "printers prefer transport_kind=tcp (port 9100)"}


def send_usb(printer_name: str, zpl: str) -> dict:
    """USB transport = Windows print queue (USB printers are queue-backed on Windows).

    For raw USB without a driver, Windows cannot deliver raw ZPL; the documented
    Link-OS approach is the driver queue or the Zebra SDK. This path uses the
    queue and reports the driver kind.
    """
    printer = _find_printer(printer_name)
    if printer is None:
        avail = [p["Name"] for p in list_windows_printers() if p.get("Name")]
        return {"ok": False, "transport": "usb", "printer": printer_name,
                "error": "USB printer queue not found",
                "available_printers": avail,
                "hint": "install the Zebra Windows driver first; USB ZPL printing goes "
                        "through the Windows queue"}
    res = send_windows_printer(printer["Name"], zpl)
    res["transport"] = "usb"
    return res


def ascii_preview(zpl: str, width_mm: float = 100, height_mm: float = 50,
                  dpi: int = 203) -> str:
    """Rough text-mode preview of a ZPL label (for chat display without a printer).

    Parses ^FO/^A/^FD/^FS and barcode data blocks into a monospace approximation.
    """
    w_dots = max(1, int(width_mm * dpi / 25.4))
    h_dots = max(1, int(height_mm * dpi / 25.4))
    cols = max(20, w_dots // 6)
    rows = max(6, h_dots // 12)
    grid = [[" "] * cols for _ in range(rows)]

    def place(x_dots: int, y_dots: int, text: str):
        cx = min(cols - 1, max(0, x_dots // 6))
        ry = min(rows - 1, max(0, y_dots // 12))
        s = text[: cols - cx]
        for i, ch in enumerate(s):
            grid[ry][cx + i] = ch

    # parameters never contain '^', so [^^]* is a safe "up to the next command"
    # span — this also covers ^A@ TrueType calls (E:SIMSUN.TTF) that the old
    # [^F]* class cut short at the F in .TTF
    for m in re.finditer(r"\^FO(\d+),(\d+)\^(?:A[^^]*)?(?:\^FB[^^]*)?\^FD([^^]*)\^FS", zpl):
        place(int(m.group(1)), int(m.group(2)), m.group(3))
    for m in re.finditer(r"\^FO(\d+),(\d+)\^(?:B[A-Z0-9][^^]*)?(?:\^FH[^F^^]*)?\^FD([^^]*)\^FS", zpl):
        place(int(m.group(1)), int(m.group(2)), "|||||||||||||||||| " + m.group(3))
    out = "+" + "-" * cols + "+"
    for r in grid:
        out += "\n|" + "".join(r).rstrip().ljust(cols) + "|"
    out += "\n+" + "-" * cols + "+"
    return out


def write_preview(zpl: str, name: str = "") -> dict:
    """Write the exact bytes that would be sent to a .zpl file (per-process name
    so concurrent MCP calls do not overwrite each other's preview)."""
    path = SCRATCH / (name or f"label_preview_{os.getpid()}.zpl")
    path.write_bytes(_clean_zpl(zpl))
    return {"preview_file": str(path), "bytes": path.stat().st_size}
