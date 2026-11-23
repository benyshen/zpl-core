"""Conformance tests against the ZPL II / ZBI 2 / SGD Programming Guide.

The manual is P1134473-11EN Rev A (2026-07-05). Every page number, Format line
and Default cited in the code is checked here against `data/commands.json`,
which is generated from the manual's own command sections. The point is that a
wrong letter or page can no longer hide: it used to be possible to emit
"^BU..." for a UPC-A and get a UPC-E, or to cite p.322 for a command that lives
on p.296, and nothing failed.

Run from the repo root:
    python tests/test_manual.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zpl_core import builder, knowledge  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name)


MANUAL = json.loads((ROOT / "src/zpl_core/data/commands.json").read_text(encoding="utf-8"))

# ^B9 prints "Format: ^B9,h,f,g,e" in the manual but its parameter table starts
# with "o = orientation" — a manual typo, recorded here instead of guessed at.
MANUAL_TYPOS = {"^B9": "Format line omits the leading o (the table lists o = orientation)"}


def tok(letters: str) -> list[str]:
    return builder.split_letters(letters.replace(",", "").replace(" ", ""))


# ---------------------------------------------------------------- Format lines
print("\n-- Format lines (letters + page) --")
for sym, spec in sorted(builder.BARCODE_SPECS.items()):
    cmd = spec["cmd"]
    ref = MANUAL.get(cmd)
    if ref is None:
        check(f"{sym}: {cmd} exists in the manual", False)
        continue
    if cmd in MANUAL_TYPOS:
        want, got = tok(spec["letters"]), tok(ref["params"])
        check(f"{sym}: {cmd} letters match the manual (typo allowed)",
              got == want or sorted(got) == sorted(want), f"manual={got} code={want}")
    else:
        check(f"{sym}: {cmd} letters match the manual",
              tok(spec["letters"]) == tok(ref["params"]),
              f"manual={tok(ref['params'])} code={tok(spec['letters'])}")
    check(f"{sym}: page matches the manual",
          spec["page"] == f"p.{ref['page']}", f"manual p.{ref['page']} code {spec['page']}")

# ------------------------------------------------------- knowledge page drift
print("\n-- COMMAND_NOTES pages --")
for cmd, meta in sorted(knowledge.COMMAND_NOTES.items()):
    ref = MANUAL.get(cmd)
    if ref is None:
        continue
    check(f"{cmd} page == manual p.{ref['page']}", meta.get("page") == ref["page"],
          f"note {meta.get('page')}")

# ------------------------------------------------------- emitted ZPL is known
print("\n-- every symbology emits commands the manual documents --")
SAMPLE = {
    "code11": "12345", "i2of5": "12345670", "code39": "ABC123", "code49": "ABC123",
    "codabar": "A12345B", "code93": "ABC123", "code128": "ABC123", "codablock": "ABC123",
    "logmars": "ABC123", "msi": "12345", "plessey": "1234ABCD", "industrial2of5": "1234",
    "std2of5": "1234", "ean8": "1234567", "upce": "0123456789", "ean13": "590123412345",
    "upca": "01234567890", "upcext": "12345", "planet": "12345678901", "postnet": "123456789",
    "usps": "01234567094987654321", "aztec": "ABC", "pdf417": "ABC", "micropdf417": "ABC",
    "upsmaxicode": "ABC123", "datamatrix": "ABC", "qrcode": "ABC", "gs1databar": "0123456",
    # ^BT p.141: 6-digit ECI + comma + serial, otherwise only the Code 39 half prints
    "tlc39": "123456,SN12345", "by": "1",
}
built_ok = True
for sym, data in SAMPLE.items():
    if sym == "by":
        continue
    zpl, issues = builder.build_label({"dpi": 203, "width_mm": 60, "height_mm": 40, "fields": [
        {"type": "barcode", "symbology": sym, "data": data, "x_mm": 2, "y_mm": 2, "height_mm": 8}]})
    errs = [i for i in issues if i["severity"] == "error"]
    unknown = [i for i in builder.validate_zpl(zpl) if i["code"] == "UNKNOWN_CMD"]
    if errs or unknown:
        built_ok = False
        print(f"   {sym}: {errs} {unknown}")
check("all symbologies build and validate clean", built_ok)

# ------------------------------------------------------------- regressions
print("\n-- manual-fidelity regressions --")


def build(fields, **label):
    spec = {"dpi": 203, "width_mm": 60, "height_mm": 40, "fields": fields}
    spec.update(label)
    return builder.build_label(spec)


def one(sym, data, **extra):
    f = {"type": "barcode", "symbology": sym, "data": data, "x_mm": 2, "y_mm": 2}
    f.update(extra)
    return build([f])


# Table 34: ^BU = UPC-A, ^B9 = UPC-E, ^B0/^BO = Aztec. 0.1.x had UPC-A on ^B9
# and UPC-E on ^B0, so asking for UPC-A printed a UPC-E and asking for UPC-E
# printed an Aztec symbol — both perfectly valid ZPL, both the wrong barcode.
z, i = one("upca", "01234567890")
check("UPC-A maps to ^BU (Table 34 p.1588)", "^BU" in z and "^B9" not in z, z)
check("UPC-A takes 11 digits, check digit auto", not i, str(i)[:80])
z, i = one("upca", "012345678905")            # 12 = with a check digit we must not send
check("UPC-A rejects 12 digits", any(x["code"] == "BC_LENGTH" for x in i), str(i)[:60])
z, i = one("upce", "0123456789")
check("UPC-E maps to ^B9", "^B9" in z, z)
check("UPC-E takes 10 digits", not i, str(i)[:80])
z, i = one("upce", "0123456789", orientation="R")
check("^B9 orientation is the o parameter", z.startswith("^XA") and "^B9R" in z, z)

z, _ = one("ean13", "590123412345")
check("EAN-13 takes 12 digits", "^BE" in z and "^FD590123412345" in z, z)
z, i = one("ean13", "5901234123457")
check("EAN-13 rejects 13 digits", any(x["code"] == "BC_LENGTH" for x in i), str(i)[:60])
z, i = one("ean8", "123456")
check("EAN-8 rejects 6 digits", any(x["code"] == "BC_LENGTH" for x in i), str(i)[:60])
z, i = one("upcext", "1234")
check("UPC/EAN extension takes 2 or 5 digits", any(x["code"] == "BC_LENGTH" for x in i), str(i)[:60])

# ^BX p.144: s (quality) defaults to 0 — treating 200 as "the default" made the
# builder drop it, so a caller who asked for ECC200 silently got ECC000.
z, i = one("datamatrix", "ABC", quality=200)
check("^BX quality=200 is emitted", "^BXN,,200" in z, z)
z, i = one("datamatrix", "ABC", quality=200, format_id=2, escape_char="_", aspect_ratio=2)
check("^BX f/g/a are reachable", re.search(r"\^BXN,,200,,,2,_,2", z), z)
z, i = one("datamatrix", "ABC" * 300, quality=0)
check("^BX quality 0-140 caps at 596 chars", any(x["code"] == "DM_LENGTH" for x in i), str(i)[:60])

# ^BM p.122: the second check-digit parameter is literally "e2".
z, i = one("msi", "1234", insert_check_digit=True)
check("MSI insert-check-digit uses e2", "^BMN,B,,Y,N,Y" in z, z)

# ^BC p.95: mode D (UCC/EAN) exists
z, i = one("code128", "0204017773003486100008535", mode="D")
check("Code 128 mode D (UCC/EAN) accepted", any(x["code"].startswith("CODE128_M") for x in i) is False, str(i)[:80])
check("Code 128 mode D is emitted", z.split("^FD")[0].endswith("D"), z)

# ^PO p.322: values are N and I
z, i = build([{"type": "text", "data": "X", "x_mm": 1, "y_mm": 1}], invert=True)
check("^PO invert emits I, not Y", "^POI" in z and "^POY" not in z, z)
check("validate_zpl rejects ^POY", any(x["code"] == "PO_VALUE"
                                       for x in builder.validate_zpl("^XA^POY^XZ")))

# ^MM p.305: C (cutter) is a valid mode; b is the prepeel select
z, i = build([], print_mode={"mode": "C"})
check("^MM cutter accepted", "^MMC," in z, z)
check("^MM rejects an invented mode", any(x["code"] == "MM"
                                          for x in build([], print_mode={"mode": "Z"})[1]))

# ^MN p.307: there is no B media mode; V (variable length) exists
z, _ = build([], media_tracking={"mode": "V"})
check("^MN V accepted", "^MNV," in z, z)
check("^MN B rejected", any(x["code"] == "MN" for x in build([], media_tracking={"mode": "B"})[1]))

# ^PR p.326: 1-12 plus A-E (A=2 ips ... E=8 ips)
z, _ = build([], print_speed="E")
check("^PR speed E accepted", "^PRE" in z, z)
check("^PR rejects speed 13", any(x["code"] == "PR_SPEED" for x in build([], print_speed="13")[1]))

# ^LS p.296 (-9999..9999) and ^LT p.297 (-120..120)
z, i = build([], shift_left=-40)
check("^LS negative shift allowed", "^LS-40" in z and not i, f"{z} {i}")
check("^LS out of range flagged", any(x["code"] == "LS" for x in build([], shift_left=20000)[1]))
z, i = build([], label_top=-120)
check("^LT -120 allowed", "^LT-120" in z, z)
check("^LT -200 warns", any(x["code"] == "LT" for x in build([], label_top=-200)[1]))

# ~SD p.333 is "##": two digits
z, _ = build([], darkness=5)
check("~SD pads to two digits", "~SD05" in z, z)
z, _ = build([], darkness=8.3)
check("~SD keeps the 0.1 increment", "~SD8.3" in z, z)

# ^GB p.210: thickness defaults to 1, rounding 0-8, colours B/W
z, _ = build([{"type": "box", "x_mm": 1, "y_mm": 1, "width_mm": 20, "height_mm": 10}])
check("^GB thickness default is 1", "^GB160,80,1," in z, z)
z, _ = build([{"type": "box", "x_mm": 1, "y_mm": 1, "width_mm": 20, "height_mm": 10,
               "corner_rounding": 99}])
check("^GB rounding clamped to 8", z.split("^GB")[1].split(",")[4].startswith("8"), z)

# ^GC p.212: diameter default 3, clamp 4095
z, _ = build([{"type": "circle", "x_mm": 1, "y_mm": 1}])
check("^GC diameter defaults to 3", "^GC3," in z, z)
z, _ = build([{"type": "circle", "x_mm": 1, "y_mm": 1, "diameter_dots": 9999}])
check("^GC diameter clamps to 4095", "^GC4095," in z, z)

# ^FB p.186: c is a signed delta, so -9999..9999 must pass; ^FO/^FT p.201/205 z
z, i = build([{"type": "text", "data": "A", "x_mm": 1, "y_mm": 1, "size_mm": 3,
               "block": {"width_mm": 30, "lines": 2, "line_spacing": -3}}])
check("^FB negative line spacing allowed", "^FB240,2,-3," in z, z)
z, _ = build([{"type": "text", "data": "A", "x_mm": 1, "y_mm": 1, "size_mm": 3, "justify": 1}])
check("^FO justification parameter reachable", "^FO8,8,1^A" in z, z)

# ^FR p.203: applies to one field
z, i = build([{"type": "text", "data": "REV", "x_mm": 1, "y_mm": 1, "size_mm": 3, "reverse": True}])
check("^FR lands inside the field it reverses", "^A0N,24^FR^FDREV" in z, z)
z, i = build([{"type": "reverse"}])
check("standalone ^FR field is flagged", any(x["code"] == "FR_STANDALONE" for x in i), str(i)[:60])

# ^BQ p.130: manual data input needs a character mode
z, i = build([{"type": "barcode", "symbology": "qrcode", "data": "12345", "x_mm": 1, "y_mm": 1,
               "input_mode": "M"}])
check("QR manual input without char mode errors", any(x["code"] == "QR_CHAR_MODE" for x in i), str(i)[:60])
z, i = build([{"type": "barcode", "symbology": "qrcode", "data": "12345", "x_mm": 1, "y_mm": 1,
               "input_mode": "M", "char_mode": "N"}])
check("QR manual numeric input emits QM,N", "^FDQM,N12345" in z, z)
z, i = build([{"type": "barcode", "symbology": "qrcode", "data": "ABC", "x_mm": 1, "y_mm": 1,
               "ec_level": "H", "mixed_mode": {"code_no": 3, "divisions": 7, "parity": "A1"}}])
check("QR mixed-mode switch precedes the EC switch", "^FDD0307A1,HA,ABC" in z, z)

# ^FD p.190: 3072 bytes
z, i = build([{"type": "text", "data": "A" * 3100, "x_mm": 1, "y_mm": 1, "size_mm": 3}])
check("^FD length limit enforced", any(x["code"] == "FD_LENGTH" for x in i), str(i)[:60])

# ^A p.60 / ^CF p.154: the default font is the ^CF value (power-up A), and a
# bitmapped font cannot take an arbitrary dot height, so a sized field uses 0.
z, _ = build([{"type": "text", "data": "A", "x_mm": 1, "y_mm": 1}])
check("unsized text uses the ^CF default font A", "^AAN" in z, z)
z, _ = build([{"type": "text", "data": "A", "x_mm": 1, "y_mm": 1, "size_mm": 3}])
check("sized text uses the scalable font 0", "^A0N,24" in z, z)

# orientation defaults to the ^FW value instead of a hardcoded N
z, _ = build([{"type": "barcode", "symbology": "code128", "data": "ABC", "x_mm": 1, "y_mm": 1,
               "height_mm": 8}], default_orientation="R")
check("barcode orientation follows ^FW", "^BCR," in z, z)

# ------------------------------------------------------- manual page pitfalls
print("\n-- manual pitfalls (must stay fixed across regenerations) --")
# p.107 prints "Format: ^FD <hpm><lpm>" inside the ^BD MaxiCode section, so a
# naive "first Format: line wins" extractor puts ^FD on the wrong page and every
# tooltip afterwards lies. ^FD itself is p.190.
check("^FD page is 190, not the p.107 MaxiCode mention", MANUAL["^FD"]["page"] == 190,
      str(MANUAL["^FD"]["page"]))
# ^B9 prints "Format: ^B9,h,f,g,e" while its parameter table starts with
# "o = orientation" — a typo in the manual, not a missing parameter.
check("^B9 keeps the o (orientation) parameter", "o" in tok(MANUAL["^B9"]["params"]),
      MANUAL["^B9"]["params"])
# Example pages open with "ZPL Commands" too, so ^XA/^FS must come from their
# own sections (370 / 204) and not from the first example that shows them.
for cmd, page in (("^XA", 370), ("^XZ", 375), ("^FS", 204)):
    check(f"{cmd} page is its own section", MANUAL[cmd]["page"] == page, str(MANUAL[cmd]["page"]))
# ^B0 and ^BO are both Aztec; UPC-E is ^B9 and UPC-A is ^BU (Table 34).
check("^B0 and ^BO are Aztec, not UPC-E",
      "Aztec" in MANUAL["^B0"]["name"] and "Aztec" in MANUAL["^BO"]["name"],
      f'{MANUAL["^B0"]["name"]} / {MANUAL["^BO"]["name"]}')
check("no UPC-E on ^B0 in the barcode table", builder.BARCODE_SPECS["upce"]["cmd"] == "^B9")
check("no UPC-A on ^B9 in the barcode table", builder.BARCODE_SPECS["upca"]["cmd"] == "^BU")

# ------------------------------------------------------------------- summary
print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED:")
    for f in FAILED:
        print("   -", f)
    raise SystemExit(1)
print("ALL MANUAL CONFORMANCE CHECKS PASSED")
