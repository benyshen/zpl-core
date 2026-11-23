"""Tests for the three "edge terminal" features added in 0.3.0.

1. ``raster`` + ``^GF``   — a PNG/bitmap becomes a printed graphic (p.215).
2. ``^DF``/``^XF``/``^FN`` — store a format once, print it with a few bytes (p.174/372/200).
3. ``~HS``/``^HV``         — a closed loop: is the printer ready, did it print,
                            and what did it actually print (p.233-239).

The status/closed-loop tests run against a **fake printer** on localhost: a
socket that answers ``~HS`` with canned status strings and records the jobs it
received. That is the only way to test the failure paths without bricking a real
printer, and it keeps the suite hardware-free.

    python tests/test_edge.py
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zpl_core import builder, raster, transport  # noqa: E402

FAILED: list[str] = []
STX, ETX = chr(2), chr(3)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name)


# =============================================================== 1. ^GF images
print("-- ^GF: bitmap -> graphic field --")

b = raster.from_rows(["11110000", "00001111"])
check("8x2 bitmap packs to one byte per row", b.hex_data() == "F00F", b.hex_data())
check("^GFA carries b=c=bytes and d=bytes/row",
      b.to_gfa(10, 20) == "^FO10,20^GFA,2,2,1,F00F", b.to_gfa(10, 20))
check("position prefix is optional", b.to_gfa() == "^GFA,2,2,1,F00F", b.to_gfa())

b3 = raster.from_rows(["101", "010", "111"])
check("rows are padded to a byte boundary (3 dots -> 1 byte)", b3.hex_data() == "A040E0",
      b3.hex_data())
check("padding does not inflate the row count", b3.nbytes == 3, str(b3.nbytes))

try:
    raster.from_rows(["111", "11"])
    check("ragged rows rejected", False)
except ValueError:
    check("ragged rows rejected", True)

big = raster.from_rows([[1] * 400 for _ in range(300)])      # 50 bytes/row * 300 = 15000
check("bitmap size maths", big.bytes_per_row == 50 and big.nbytes == 15000,
      f"{big.bytes_per_row}x{big.height}")
try:
    raster.from_rows([[1] * 800 for _ in range(1200)]).to_gfa()   # 100 * 1200 = 120000
    check("^GF 99999-byte ceiling enforced", False)
except ValueError as exc:
    check("^GF 99999-byte ceiling enforced", "99999" in str(exc), str(exc)[:60])

zpl, issues = builder.build_label({"dpi": 203, "width_mm": 40, "height_mm": 20, "fields": [
    {"type": "image", "bitmap": ["11110000", "00001111"], "x_mm": 2, "y_mm": 2}]})
check("builder emits ^GFA from raw bits (stdlib only)",
      "^FO16,16^GFA,2,2,1,F00F^FS" in zpl, zpl)
check("generated label validates", builder.validate_zpl(zpl) == [], str(builder.validate_zpl(zpl)))
check("no issues for a small bitmap", not issues, str(issues))

zpl2, i2 = builder.build_label({"dpi": 203, "width_mm": 40, "height_mm": 20, "fields": [
    {"type": "image", "path": str(ROOT / "tests" / "fixtures" / "nope.png"), "x_mm": 2, "y_mm": 2}]})
check("missing image file is an error, not a crash",
      any(i["code"] == "IMG_PATH" for i in i2), str(i2)[:70])

zpl3, i3 = builder.build_label({"dpi": 203, "width_mm": 80, "height_mm": 80, "fields": [
    {"type": "image", "bitmap": [[1] * 480 for _ in range(400)], "x_mm": 2, "y_mm": 2}]})
check("large payload warns about transfer time",
      any(i["code"] == "GF_PAYLOAD" for i in i3), str(i3)[:80])

zpl4, _ = builder.build_label({"dpi": 203, "width_mm": 40, "height_mm": 20, "fields": [
    {"type": "image", "name": "logo.grf", "x_mm": 2, "y_mm": 2}]})
check("^XGR path still works for stored graphics", "^XGR:logo.grf" in zpl4, zpl4)

# the PIL path (needs the [render] extra)
try:
    from PIL import Image

    img = Image.new("L", (16, 4), 255)
    for x in range(8):
        for y in range(4):
            img.putpixel((x, y), 0)
    bmp = raster.from_image(img)
    check("PIL image -> bitmap (black left half)", bmp.hex_data() == "FF00FF00FF00FF00",
          bmp.hex_data())
    check("threshold/invert keep the format stable",
          raster.from_image(img, invert=True).hex_data() == "00FF00FF00FF00FF",
          raster.from_image(img, invert=True).hex_data())
    check("scaling keeps the aspect ratio",
          raster.from_image(img, width_dots=32).height == 8,
          str(raster.from_image(img, width_dots=32).height))
    tmp = Path(ROOT / "scratch" / "gf_logo.png")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    img.save(tmp)
    zpl5, i5 = builder.build_label({"dpi": 203, "width_mm": 40, "height_mm": 20, "fields": [
        {"type": "image", "path": str(tmp), "x_mm": 2, "y_mm": 2}]})
    check("PNG on disk -> ^GFA", "^GFA,8,8,2," in zpl5, zpl5[:80])
    check("PNG label validates", not [i for i in i5 if i["severity"] == "error"], str(i5)[:70])
except ImportError:
    print("  (PIL absent: pip install 'zpl-core[render]' -- image-file tests skipped)")

# =========================================================== 2. ^DF/^XF/^FN
print("\n-- ^DF/^XF/^FN: stored format with variables --")

spec = {"dpi": 203, "width_mm": 60, "height_mm": 40, "fields": [
    {"type": "text", "data": "FIXED", "x_mm": 2, "y_mm": 2, "size_mm": 3},
    {"type": "text", "var": "sku", "x_mm": 2, "y_mm": 8, "size_mm": 3},
    {"type": "barcode", "symbology": "code128", "var": "code", "x_mm": 2, "y_mm": 14,
     "height_mm": 10},
]}
tpl, fields, ti = builder.build_template(spec, name="SHIP")
check("^DF comes straight after ^XA", tpl.startswith("^XA^DFR:SHIP.ZPL"), tpl[:40])
check("literal field keeps its ^FD", "^FDFIXED^FS" in tpl, tpl)
check("variable text field carries ^FN and no ^FD", "^A0N,24^FN1^FS" in tpl, tpl)
check("variable barcode field carries ^FN and no ^FD", "^BCN,80^FN2^FS" in tpl, tpl)
check("field map is 1:sku 2:code", fields == {1: "sku", 2: "code"}, str(fields))
check("template validates", builder.validate_zpl(tpl) == [], str(builder.validate_zpl(tpl)))
check("template name >8 chars warns (^XF recalls 1-8)",
      any(i["code"] == "XF_NAME" for i in builder.build_template(spec, name="TOOLONGNAME1")[2]))

recall, ri = builder.fill_template("SHIP", {"sku": "A-1", "code": "693402451212"}, fields=fields)
check("recall uses ^XF + one ^FN per value",
      recall == "^XA^XFR:SHIP.ZPL^FN1^FDA-1^FS^FN2^FD693402451212^FS^XZ", recall)
check("recall validates", builder.validate_zpl(recall) == [], str(builder.validate_zpl(recall)))
check("numeric keys work too",
      builder.fill_template("SHIP", {1: "A-1"})[0] == "^XA^XFR:SHIP.ZPL^FN1^FDA-1^FS^XZ",
      builder.fill_template("SHIP", {1: "A-1"})[0])
check("unknown variable is an error",
      any(i["code"] == "FN_UNKNOWN" for i in builder.fill_template("SHIP", {"nope": 1},
                                                                  fields=fields)[1]))
check("recall name >8 chars is an error (not just a warning)",
      any(i["code"] == "XF_NAME" and i["severity"] == "error"
          for i in builder.fill_template("TOOLONGNAME1", {1: "x"})[1]))
check("quantity belongs to the recall",
      "^PQ3" in builder.fill_template("SHIP", {1: "a"}, quantity=3)[0])
q_tpl, _, q_iss = builder.build_template({**spec, "quantity": 3}, name="SHIP")
check("quantity is stripped from the template", "^PQ" not in q_tpl and
      any(i["code"] == "PQ_IN_TEMPLATE" for i in q_iss), q_tpl[:60])
check("template without variables warns",
      any(i["code"] == "DF_EMPTY" for i in
          builder.build_template({"dpi": 203, "fields": [{"type": "text", "data": "x"}]},
                                 name="SHIP")[2]))
check("escaping inside a value is preserved",
      "_5E" in builder.fill_template("SHIP", {1: "a^b"})[0],
      builder.fill_template("SHIP", {1: "a^b"})[0])

print("\n-- ^HV: ask the printer what it actually printed --")
hv_spec = {"dpi": 203, "width_mm": 60, "height_mm": 40, "fields": [
    {"type": "barcode", "symbology": "code128", "data": "693402451212", "x_mm": 2, "y_mm": 2,
     "hv": {"bytes": 16, "header": "CODE[", "terminator": "]"}}]}
hv_zpl, hv_iss = builder.build_label(hv_spec)
check("^HV follows the field it verifies", "^HV1,16,CODE[,],L^FS" in hv_zpl, hv_zpl)
check("^HV forces an ^FN number onto the field", "^FN1^FD" in hv_zpl, hv_zpl)
check("^HV label validates", builder.validate_zpl(hv_zpl) == [], str(builder.validate_zpl(hv_zpl)))
check("^HV byte count outside 1-256 errors",
      any(i["code"] == "HV_BYTES" for i in
          builder.build_label({"dpi": 203, "fields": [
              {"type": "text", "data": "x", "hv": {"bytes": 999}}]})[1]))

# ---------------------------------------- stacked 2D: h is one ROW (p.79/111)
print("\n-- ^B7/^BF: row height, rows, module width --")
pdf_spec = {"dpi": 200, "width_mm": 60, "height_mm": 50, "fields": [
    {"type": "barcode", "symbology": "pdf417", "data": "ZPL-CORE|0.3.0|PDF417",
     "x_mm": 3, "y_mm": 6, "module_width": 2, "columns": 6, "rows": 6,
     "row_height_dots": 12, "security_level": 2}]}
pdf_zpl, pdf_iss = builder.build_label(pdf_spec)
check("^BY is emitted before the symbol", "^BY2,3,10^B7N,12,2,6,6" in pdf_zpl, pdf_zpl)
check("row_height_dots goes into h (one row, not the symbol)",
      ",12," in pdf_zpl.split("^B7")[1][:12], pdf_zpl.split("^B7")[1][:20])
check("rows maps to r, not a ratio", pdf_zpl.split("^B7")[1].startswith("N,12,2,6,6"),
      pdf_zpl.split("^B7")[1][:14])
check("no warnings for a fully specified symbol",
      not [i for i in pdf_iss if i["severity"] in ("error", "warning")], str(pdf_iss))

legacy, legacy_iss = builder.build_label({"dpi": 200, "width_mm": 60, "height_mm": 50, "fields": [
    {"type": "barcode", "symbology": "pdf417", "data": "ABC", "height_mm": 8}]})
check("height_mm on ^B7 warns that h is a row height",
      any(i["code"] == "ROW_HEIGHT" for i in legacy_iss), str(legacy_iss)[:80])
check("…and is still written as the row height", "^B7N,63" in legacy, legacy)

check("a row height x 4 rows beyond the label is flagged",
      any(i["code"] == "ROW_TOO_TALL" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 20, "fields": [
              {"type": "barcode", "symbology": "pdf417", "data": "A",
               "row_height_dots": 60, "module_width": 2}]})[1]))
cap_warn, cap_iss = builder.build_label(
    {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
        {"type": "barcode", "symbology": "pdf417", "data": "ZPL-CORE|0.3.0|ZR668|TC201L|X|PDF417",
         "columns": 6, "rows": 6, "security_level": 2, "module_width": 2}]})
check("over-tight c x r is flagged (printer prints nothing, reports no error)",
      any(i["code"] == "BC_CAPACITY" for i in cap_iss), str(cap_iss)[:80])
check("…and the symbol is still emitted for the caller to inspect", "^B7" in cap_warn, cap_warn)
check("auto rows/columns never trips the capacity guard",
      not any(i["code"] == "BC_CAPACITY" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
              {"type": "barcode", "symbology": "pdf417", "data": "ZPL-CORE|0.3.0|" * 3,
               "module_width": 2, "row_height_dots": 12}]})[1]))
check("a 1x1 grid is an outright capacity error",
      any(i["code"] == "BC_CAPACITY" and i["severity"] == "error"
          for i in builder.build_label(
              {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
                  {"type": "barcode", "symbology": "pdf417", "data": "0123456789" * 3,
                   "columns": 2, "rows": 3, "module_width": 2}]})[1]))

check("no module_width on a stacked code warns about inherited ^BY",
      any(i["code"] == "BY_UNSET" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 30, "fields": [
              {"type": "barcode", "symbology": "pdf417", "data": "A"}]})[1]))

# ------------------------------- ^BF MicroPDF417 mode / ^BT TLC39 data format
print("\n-- ^BF / ^BT: the two that print nothing when the data is wrong --")
mp, mp_iss = builder.build_label({"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
    {"type": "barcode", "symbology": "micropdf417", "data": "MICRO-PDF417-26"}]})
check("MicroPDF417 auto-picks a mode that fits (15 chars -> mode 2)",
      "^BFN,,2" in mp, mp.split("^BF")[-1][:12])
check("…without complaining", not [i for i in mp_iss if i["severity"] == "error"], str(mp_iss))
check("short MicroPDF417 data keeps the default mode 0",
      "^BFN^" not in mp and "^BFN$" not in mp and
      not builder.build_label({"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
          {"type": "barcode", "symbology": "micropdf417", "data": "MPDF"}]})[0]
      .split("^BF")[-1].startswith("N,"))
check("an explicit mode too small for the data is an error",
      any(i["code"] == "BF_CAPACITY" and i["severity"] == "error"
          for i in builder.build_label({"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
              {"type": "barcode", "symbology": "micropdf417", "data": "MICRO-PDF417-26",
               "mode": 0}]})[1]))
check("MicroPDF417 beyond mode 33 is an error",
      any(i["code"] == "BF_CAPACITY" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
              {"type": "barcode", "symbology": "micropdf417", "data": "X" * 400}]})[1]))

tl_ok, tl_ok_iss = builder.build_label({"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
    {"type": "barcode", "symbology": "tlc39", "data": "123456,SN0012345"}]})
check("TLC39 accepts 6 digits + comma + serial", "^BT" in tl_ok and not tl_ok_iss,
      str(tl_ok_iss))
check("TLC39 rejects anything else (the printer would draw only half the symbol)",
      any(i["code"] == "BT_FORMAT" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
              {"type": "barcode", "symbology": "tlc39", "data": "TLC39-28"}]})[1]))
check("TLC39 rejects a non-numeric ECI prefix",
      any(i["code"] == "BT_FORMAT" for i in builder.build_label(
          {"dpi": 200, "width_mm": 60, "height_mm": 45, "fields": [
              {"type": "barcode", "symbology": "tlc39", "data": "AB1234,SN1"}]})[1]))

# ========================================================= 3. ~HS closed loop
print("\n-- ~HS: parse the three host-status strings --")


def hs(s1: str, s2: str, s3: str = "0000,1") -> bytes:
    return f"{STX}{s1}{ETX}\r\n{STX}{s2}{ETX}\r\n{STX}{s3}{ETX}\r\n".encode("latin-1")


ready_raw = hs("007,0,0,0632,000,0,0,0,000,0,0,0", "060,0,0,0,1,2,0,0,00000000,1,001")
st = transport.parse_host_status(ready_raw)
check("ready printer parses", st["ok"] and st["ready"] and st["idle"], json.dumps(
    {k: st[k] for k in ("ok", "ready", "idle")}))
check("label length and queue depth", st["label_length_dots"] == 632 and
      st["formats_in_buffer"] == 0, f"{st['label_length_dots']}/{st['formats_in_buffer']}")
check("print mode is named", st["print_mode"] == "tear-off", str(st["print_mode"]))
check("media type decoded from the mmm bitmap", st["media_type"] == "die-cut", st["media_type"])
check("baud decoded from aaa", st["baud"] == 19200, str(st["baud"]))
check("serial framing decoded", (st["data_bits"], st["stop_bits"], st["parity"]) == (7, 2, "odd"),
      f"{st['data_bits']}/{st['stop_bits']}/{st['parity']}")

bad = transport.parse_host_status(hs("007,1,0,0632,002,0,0,0,000,0,0,0",
                                     "060,0,1,1,0,2,0,0,00000003,1,001"))
check("paper out / head open / ribbon out are all reported",
      [e["name"] for e in bad["errors"]] == ["PAPER OUT", "HEAD OPEN", "RIBBON OUT"],
      str([e["name"] for e in bad["errors"]]))
check("a printer with errors is not ready", not bad["ready"])
check("error carries the ZBI code for cross-reference",
      next(e for e in bad["errors"] if e["flag"] == "paper_out")["zbi_code"] == "0003")

paused = transport.parse_host_status(hs("007,0,1,0632,001,0,0,0,000,0,0,0",
                                        "060,0,0,0,1,2,0,0,00000001,1,001"))
check("pause blocks 'ready' without being an error",
      not paused["ready"] and not [e for e in paused["errors"] if e["severity"] == "error"],
      str(paused["errors"]))
check("garbage parses as not-ok instead of raising",
      transport.parse_host_status(b"<STX>junk<ETX>")["ok"] is False and
      transport.parse_host_status(b"")["ok"] is False)


class FakePrinter:
    """A localhost socket that answers ~HS and records the jobs it receives."""

    def __init__(self, states: list[str] | None = None, echo: bytes | None = None):
        self.states = states or []
        self.echo = echo
        self.jobs: list[bytes] = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(0.3)
                data = b""
                try:
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                except socket.timeout:
                    pass
                if b"~HS" in data:
                    state = self.states.pop(0) if self.states else "idle"
                    conn.sendall(self._status(state))
                else:
                    self.jobs.append(data)
                    if self.echo:
                        conn.sendall(self.echo)

    @staticmethod
    def _status(state: str) -> bytes:
        if state == "paper":
            return hs("007,1,0,0632,000,0,0,0,000,0,0,0", "060,0,0,0,1,2,0,0,00000000,1,001")
        if state == "busy":
            return hs("007,0,0,0632,001,0,0,0,000,0,0,0", "060,0,0,0,1,2,0,0,00000002,1,001")
        return hs("007,0,0,0632,000,0,0,0,000,0,0,0", "060,0,0,0,1,2,0,0,00000000,1,001")

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


print("\n-- closed loop against a fake printer --")

fake = FakePrinter(states=["idle", "busy", "idle", "idle", "idle"])
res = transport.send_and_verify("127.0.0.1", "^XA^FO10,10^A0N,30^FDOK^FS^XZ",
                                port=fake.port, timeout=0.5, max_wait=5, poll=0.05)
check("send_and_verify reports 'printed'", res["ok"] and res["stage"] == "printed",
      f"{res['ok']}/{res.get('stage')}/{res.get('error')}")
check("the job reached the printer", len(fake.jobs) == 1 and b"^FDOK" in fake.jobs[0],
      str(len(fake.jobs)))
check("timeline records preflight, send and final",
      [t["at"] for t in res["timeline"]][:1] == ["preflight"] and
      any(t["at"] == "final" for t in res["timeline"]), str([t["at"] for t in res["timeline"]]))
fake.close()

fake2 = FakePrinter(states=["paper"])
res2 = transport.send_and_verify("127.0.0.1", "^XA^XZ", port=fake2.port,
                                 timeout=0.5, max_wait=2, poll=0.05)
check("a not-ready printer refuses the job before sending",
      not res2["ok"] and res2["stage"] == "preflight", f"{res2['ok']}/{res2.get('stage')}")
check("…and nothing was sent", fake2.jobs == [], str(len(fake2.jobs)))
check("the refusal names the printer state", "PAPER OUT" in (res2.get("error") or ""),
      res2.get("error"))
fake2.close()

res3 = transport.send_and_verify("127.0.0.1", "^XA^XZ", port=1, timeout=0.3,
                                 attempts=1, max_wait=1)
check("no printer at all is a preflight failure, not an exception",
      not res3["ok"] and res3["stage"] == "preflight", f"{res3['ok']}/{res3.get('stage')}")

res4 = transport.send_and_verify("127.0.0.1", "^XA^XZ", port=1, timeout=0.3,
                                 require_ready=False, attempts=1)
check("require_ready=False still reports the send failure",
      not res4["ok"] and res4["stage"] == "send", f"{res4['ok']}/{res4.get('stage')}")

print("\n-- ^HV reply parsing --")
# the fake echoes what a printer would return for ^HV1,16,CODE[,],L
fake3 = FakePrinter(echo=b"CODE[693402451212]\r\n")

hv_out = transport.send_and_read("127.0.0.1", hv_zpl, port=fake3.port, timeout=0.5,
                                 read_timeout=0.6,
                                 expect={"header": "CODE[", "terminator": "]"})
check("^HV reply is read back", hv_out["ok"] and "CODE[693402451212]" in hv_out["reply"],
      str(hv_out.get("reply"))[:60])
check("the value can be compared to what we asked for",
      hv_out.get("values") == ["693402451212"], str(hv_out.get("values")))
fake3.close()

print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED:")
    for f in FAILED:
        print("   -", f)
    raise SystemExit(1)
print("ALL EDGE CHECKS PASSED")