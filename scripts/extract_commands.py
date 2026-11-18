"""Generate src/zpl_core/data/commands.json from the ZPL II Programming Guide.

    pip install pymupdf
    python scripts/extract_commands.py "zpl-zbi2-pg-en-202609.pdf"

The manual is copyrighted and is not part of this repository; what lands in the
repo is only the *structure* the code needs: for every command, its printed page
number, its section name, and the parameter letters from its "Format:" line.

Why this is a script and not hand-written JSON: page numbers drift between
manual revisions, and a wrong page number in a tooltip is the kind of bug nobody
notices. Regenerate, then `git diff` — the diff *is* the review.

Rules the extractor follows (see docs/manual-conformance.md):

* A command's own section starts a page whose first line is "ZPL Commands" and
  whose next line is exactly the command token. That page wins over any other
  place the token appears — e.g. "Format: ^FD <hpm><lpm>" appears at p.107
  inside the ^BD MaxiCode section, while ^FD itself is at p.190.
* Commands the manual documents without a "Format:" line (~DY, ~HS, ^HT, ...)
  and the "~" aliases printed inside ^CC/^CD/^CT/^PH/^PP sections are listed in
  EXTRA below.
* Multi-character parameter letters (e2, w1, r1, h1, w2, h2) are kept as-is;
  builder.split_letters() splits them back out at runtime.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "zpl_core" / "data" / "commands.json"

# Commands with a section but no "Format:" line, plus the ~ aliases the manual
# prints inside a ^ section ("Format: ^CC or ~CCx").
EXTRA = {
    "^CC": {"page": 152, "name": "Change Caret", "params": "x"},
    "^CD": {"page": 153, "name": "Change Delimiter", "params": "a"},
    "^CT": {"page": 166, "name": "Change Tilde", "params": "a"},
    "^HL": {"page": 413, "name": "Return RFID Data Log to Host", "params": ""},
    "^PH": {"page": 317, "name": "Slew to Home Position", "params": ""},
    "^PL": {"page": 318, "name": "Present Length Addition", "params": "a"},
    "^PP": {"page": 323, "name": "Programmable Pause", "params": ""},
    "^WL": {"page": 396, "name": "Set LEAP Parameters", "params": "a,b,c"},
    "^WR": {"page": 400, "name": "Set Transmit Rate", "params": "a,b,c,d,e"},
    "~DV": {"page": 181, "name": "Download Objects", "params": "d:f,b,x,t,w,data"},
    "~WL": {"page": 397, "name": "Print Network Configuration Label", "params": ""},
    "~WR": {"page": 401, "name": "Reset Wireless Radio Card and Print Server", "params": ""},
    "^HT": {"page": 237, "name": "Host Linked Fonts List", "params": ""},
    "^LF": {"page": 292, "name": "List Font Links", "params": ""},
    "^SE": {"page": 334, "name": "Select Encoding Table", "params": "a,s1,d1,..."},
    "~DY": {"page": 181, "name": "Download Graphics / Fonts", "params": "d:o.x,t,w,data"},
    "~EG": {"page": 185, "name": "Erase Download Graphics", "params": ""},
    "~HS": {"page": 233, "name": "Host Status", "params": ""},
    "~PL": {"page": 318, "name": "Present Length Addition", "params": "a"},
    "~PS": {"page": 328, "name": "Resume Printing", "params": ""},
    "~PH": {"page": 317, "name": "Slew to Home Position (alias of ^PH)", "params": ""},
    "~PP": {"page": 323, "name": "Programmable Pause (alias of ^PP)", "params": ""},
    "~CC": {"page": 152, "name": "Change Caret (alias of ^CC)", "params": "x"},
    "~CD": {"page": 153, "name": "Change Delimiter (alias of ^CD)", "params": "a"},
    "~CT": {"page": 166, "name": "Change Tilde (alias of ^CT)", "params": "a"},
}

# Names the "last short line before Format:" heuristic gets wrong (bullet lists,
# page numbers, NOTE/IMPORTANT paragraphs).
NAME_FIX = {
    "^FD": "Field Data", "^FS": "Field Separator", "^XA": "Start Format",
    "^XZ": "End Format", "^PR": "Print Rate", "^PW": "Print Width",
    "^PO": "Print Orientation", "^PM": "Mirror Image", "^LS": "Label Shift",
    "^LT": "Label Top", "^MD": "Media Darkness", "^FR": "Field Reverse Print",
    "^LH": "Label Home", "^B9": "UPC-E Barcode", "^BU": "UPC-A Barcode",
    "^B0": "Aztec Barcode Parameters", "^BO": "Aztec Bar Code Parameters",
    "^B1": "Code 11 Barcode", "^B2": "Interleaved 2 of 5 Bar Code",
    "^B3": "Code 39 Barcode", "^B4": "Code 49 Barcode", "^B5": "Planet Code Barcode",
    "^B7": "PDF417 Bar Code", "^B8": "EAN-8 Barcode", "^BA": "Code 93 Barcode",
    "^BB": "CODABLOCK Barcode", "^BC": "Code 128 Barcode", "^BD": "UPS MaxiCode Bar Code",
    "^BE": "EAN-13 Barcode", "^BF": "MicroPDF417 Barcode", "^BI": "Industrial 2 of 5 Bar Code",
    "^BJ": "Standard 2 of 5 Bar Code", "^BK": "ANSI Codabar Bar Code", "^BL": "LOGMARS Barcode",
    "^BM": "MSI Bar Code", "^BP": "Plessey Barcode", "^BQ": "QR Code Barcode",
    "^BR": "GS1 Databar", "^BS": "UPC/EAN Extensions", "^BT": "TLC39 Barcode",
    "^BX": "Data Matrix Barcode", "^BY": "Bar Code Field Default", "^BZ": "POSTNET Bar Code",
    "^CI": "Change International Font/Encoding", "^CW": "Font Identifier",
    "^FX": "Comment", "^HH": "Host Graphic (legacy)", "^HV": "Host Verification",
    "^JH": "Enable/Disable Slew During Backfeed", "^KC": "Set Client Identifier",
    "^KP": "Define Kiosk Password", "^MA": "Maintenance Alert Setup",
    "^NB": "Set Wired Network Authentication", "^NC": "Set Wired Network Mode",
    "^RB": "Define EPC Data Structure", "^RL": "RFID Lock (permanent)",
    "^WX": "Configure Wireless Securities", "^X": "Z64 / ZB64 decompression",
    "~HS": "Host Status", "~WC": "Print Configuration Label",
    "~HI": "Host Identification", "~HU": "Return ZebraNet Alert Configuration",
    "~KL": "Kiosk Lock", "^KN": "Set Kiosk Values (legacy)", "^SF": "Set Serialization Format",
    "~DY": "Download Graphics / Fonts", "~DV": "Download Objects",
}

# Manual typos in the "Format:" line itself. ^B9 prints "Format: ^B9,h,f,g,e"
# while its own parameter table starts with "o = orientation" (p.85).
FORMAT_FIX = {"^B9": "o,h,f,g,e"}

TOKEN = re.compile(r"^(\^[A-Z0-9@]{1,2}|~[A-Z0-9]{2})$")

# Tokens that only ever appear inside example code, never as a command.
DENY = {"^X", "^2", "^5", "^12", "^16", "^A0", "^AB", "^AD", "^AE", "^AF", "^C",
        "^F1", "^F8", "~0", "~1", "~3", "~22", "~50", "~@", "~G"}


TITLE_RE = re.compile(r"^[A-Z][A-Za-z0-9 /&()\-.,']{3,54}$")


def title(page_text: str, cmd: str) -> str:
    """The section title: the last title-looking line before the Format line.

    Zebra repeats the command name as a heading right after the intro paragraph
    ("Code 128 Barcode (Subsets A, B, and C)"), but table cells and bullet lists
    also live on those pages ("Ctrl +", "366 4-bit numeric charac"), so only
    capitalised, punctuation-free, multi-word lines qualify.
    """
    body = page_text[: page_text.find("Format:")] if "Format:" in page_text else page_text[:1400]
    cands = []
    for line in re.split(r"\n+", body):
        s = line.strip()
        if not TITLE_RE.match(s) or s in ("ZPL Commands", cmd):
            continue
        if re.match(r"^(NOTE|IMPORTANT|Comments|Example|Figure|Table|Format|Parameters|Details)\b", s):
            continue
        if len(s.split()) < 2 or len(s.split()) > 9:
            continue
        cands.append(s)
    return cands[-1] if cands else ""


def main(pdf_path: str) -> int:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("需要 PyMuPDF：pip install pymupdf", file=sys.stderr)
        return 2

    doc = fitz.open(pdf_path)
    # printed page number == pdf index + 1 (page 0 is the cover)
    pages = {str(i + 1): doc[i].get_text() for i in range(doc.page_count)}
    print(f"{pdf_path}: {doc.page_count} pages")

    # Two passes so an example page can never beat the command's own section:
    # "^XA" and "^FS" appear in dozens of examples before their real sections.
    #   (a) a page that opens with "ZPL Commands" and then the token
    #   (b) RFID / network chapters use other running headers — accept a page
    #       that prints "Format: <cmd>" and names the command near the top
    # Some example pages also open with "ZPL Commands" and show "^XA"/"^FS" on
    # their own line, which used to place ^XA at p.54 and ^FS at p.132. A real
    # section page prints "Format: <cmd>" for that command, so require it; keep
    # the loose match only for commands that have no Format line at all.
    sections: dict[str, int] = {}
    loose: dict[str, int] = {}
    for pg, text in pages.items():
        p = int(pg)
        if p < 47 or p > 1000:
            continue
        lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
        if not lines or lines[0] != "ZPL Commands":
            continue
        token = next((ln for ln in lines[:4] if TOKEN.match(ln)), "")
        if not token or token in DENY:
            continue
        loose.setdefault(token, p)
        if re.search(r"Format:\s*" + re.escape(token), text):
            sections.setdefault(token, p)
    for token, p in loose.items():
        sections.setdefault(token, p)

    for pg, text in pages.items():
        p = int(pg)
        if p < 47 or p > 1000:
            continue
        lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
        if not lines:
            continue
        for ln in lines[:6]:
            if ln in sections or not TOKEN.match(ln):
                continue
            if re.search(r"Format:\s*" + re.escape(ln), text):
                sections[ln] = p
                break


    table = {}
    for cmd, page in sections.items():
        text = pages[str(page)]
        letters = ""
        m = re.search(r"Format:\s*" + re.escape(cmd) + r"([^\n]*)", text)
        if m:
            letters = m.group(1).strip()
        table[cmd] = {"page": page, "name": NAME_FIX.get(cmd) or title(text, cmd),
                      "params": FORMAT_FIX.get(cmd, letters)}

    for cmd, row in EXTRA.items():
        table[cmd] = dict(row)      # hand-checked rows win
    for cmd, name in NAME_FIX.items():
        if cmd in table:
            table[cmd]["name"] = name

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=0, sort_keys=True),
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(table)} commands)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
