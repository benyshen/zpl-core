"""ZPL II label builder.

Every default, range and parameter letter below is taken from the ZPL II /
ZBI 2 / SGD Programming Guide, P1134473-11EN Rev A (2026-07-05), and the page
numbers are its printed page numbers. `zpl_core/data/commands.json` is the
generated command table (page + Format-line parameters) that tests/test_manual
checks these constants against.

  ^BY p.148   ^CF p.154   ^CI p.155-157   ^FO p.201   ^FT p.205   ^FB p.186
  ^FS p.204   ^GB p.210   ^GC p.212       ^GS p.217   ^PW p.329    ^LL p.294
  ^MD p.301   ^MM p.305   ^MN p.307       ^LS p.296   ^LT p.297    ^PM p.319
  ^PO p.322   ^PQ p.324   ^PR p.326       ^FW p.208   ^FH p.193    ^FD p.190
  ^A  p.60    ~SD p.333   barcodes p.64-150 (mapping: Table 34, p.1587-1588)

Two mappings were wrong before 0.2.0 and are worth spelling out, because both
produced a *valid-looking* label with the wrong symbology:

  UPC-A -> ^BU (p.142)    not ^B9, which is UPC-E (p.85)
  UPC-E -> ^B9 (p.85)     ^B0 (p.64) is Aztec, not UPC-E
"""

from __future__ import annotations

import re

# ---- manual defaults (Initial Value at Power Up) --------------------------------
BY_W, BY_R, BY_H = 2, 3.0, 10          # ^BY p.148: w 1-10 (power-up 2), r 2.0-3.0
                                       # (default 3.0), h power-up 10 — the manual
                                       # gives no "Default:" for h, only the power-up
                                       # value; 10 is what a fresh printer uses.
CF_FONT, CF_H, CF_W = "A", 9, 5        # ^CF p.154: f power-up A, h 9, w 5
                                       # (builder still emits font 0 when a field
                                       # asks for a dot size: A is bitmapped and
                                       # only takes 1-10x multiples of its matrix)
CI_DEFAULT = 0                         # ^CI p.156: power-up 0 (U.S.A. 1)
CI_UNICODE = 28                        # ^CI 28 = Unicode UTF-8 (p.157)
CI_ASIAN_SINGLE, CI_ASIAN_MULTI = 24, 26  # p.157: the manual's Asian encodings
FD_MAX = 3072                          # ^FD p.190: "any data string up to 3072 bytes"
BARCODE_H_MAX = 32000                  # ^B1..^BZ: height 1-32000 dots (^BF/^BU: 9999)
BARCODE_H_MAX_9999 = 9999              # ^BF p.111 / ^BU p.142: 1 to 9999
FO_MAX = 32000                         # ^FO/^FT p.201/205: 0-32000 dots
PW_MAX, LL_MAX = 32000, 32000          # ^PW p.329 / ^LL p.294
MD_MIN, MD_MAX = -30, 30               # ^MD p.301: -30 to 30
SD_MAX = 30                            # ~SD p.333: 00 to 30, two digits
LS_MIN, LS_MAX = -9999, 9999           # ^LS p.296: -9999 to 9999
LT_MIN, LT_MAX = -120, 120             # ^LT p.297: all printers -120..120
                                       # (600 dpi -240..240, HC100 0..120)
ORIENTATIONS = ("N", "R", "I", "B")
PO_VALUES = ("N", "I")                 # ^PO p.322: N = normal, I = invert (not Y!)
PR_SPEED = {                           # ^PR p.326: p/s/b speeds
    "1": 25.4, "2": 50.8, "3": 76.2, "4": 101.6, "5": 127.0, "6": 152.4,
    "7": 177.8, "8": 203.2, "9": 220.5, "10": 245.0, "11": 269.5, "12": 304.8,
    "A": 50.8, "B": 76.2, "C": 101.6, "D": 152.4, "E": 203.2,
}
PR_VALUES = tuple(PR_SPEED)
MM_MODES = ("T", "P", "R", "A", "C", "D", "F", "L", "U", "K")  # ^MM p.305
MN_MODES = ("N", "Y", "W", "M", "A", "V")                      # ^MN p.307
MN_OFFSET = (-120, 283)                # ^MN p.307 b: -120..283 (600dpi -240..566)
GB_ROUNDING_MAX = 8                    # ^GB p.210: r 0-8
GB_THICKNESS_DEFAULT = 1               # ^GB p.210: t default 1
GC_DEFAULT = 3                         # ^GC p.212: d default 3, 3-4095
FB_SPACING = (-9999, 9999)             # ^FB p.186: c -9999..9999 (delta, not height)
FO_JUSTIFY = ("0", "1", "2")           # ^FO/^FT p.201/205: z justification
CJK_FONTS = {"0", "15", "16"}          # ^A p.60 font 15/16 = SC/TC Chinese (model limited)

# symbology -> manual Format line (P1134473-11EN Rev A). `letters` is copied
# verbatim from each command's "Format:" line; `orient` names the letter that
# carries orientation (None for ^BD MaxiCode, which has none); `d` holds the
# manual's stated Defaults. None -> omit the parameter and let the printer / ^BY
# decide (correct whenever the manual's default is "value set by ^BY" or a
# density-dependent magnification). Symbology -> command mapping follows
# Table 34 "Barcode Field Commands" (p.1587-1588).
BARCODE_SPECS = {
    # ---- numeric / alphanumeric linear (p.66-126) ----
    "code11": dict(cmd="^B1", name="Code 11", page="p.66", letters="oehfg",
                   orient="o", d=dict(o=None, e="N", h=None, f="Y", g="N")),
    "i2of5": dict(cmd="^B2", name="Interleaved 2 of 5", page="p.68", letters="ohfgej",
                  orient="o", d=dict(o=None, h=None, f="Y", g="N", e="N", j=None)),
    "code39": dict(cmd="^B3", name="Code 39", page="p.70", letters="oehfg",
                   orient="o", d=dict(o=None, e="N", h=None, f="Y", g="N")),
    "code49": dict(cmd="^B4", name="Code 49", page="p.74", letters="ohfm",
                   orient="o", d=dict(o=None, h=None, f="N", m="A")),
    "codabar": dict(cmd="^BK", name="ANSI Codabar", page="p.118", letters="oehfgkl",
                    orient="o", d=dict(o=None, e="N", h=None, f="Y", g="N", k="A", l="A")),
    "code93": dict(cmd="^BA", name="Code 93", page="p.87", letters="ohfge",
                   orient="o", d=dict(o=None, h=None, f="Y", g="N", e="N")),
    "code128": dict(cmd="^BC", name="Code 128", page="p.94", letters="ohfgem",
                    orient="o", d=dict(o=None, h=None, f="Y", g="N", e="N", m="N"),
                    extra={"m": ("N", "U", "A", "D")}),
    "codablock": dict(cmd="^BB", name="CODABLOCK", page="p.90", letters="ohscrm",
                      orient="o", d=dict(o="N", h="8", s="Y", c=None, r=None, m="F")),
    "logmars": dict(cmd="^BL", name="LOGMARS", page="p.120", letters="ohg",
                    orient="o", d=dict(o=None, h=None, g="N")),
    "msi": dict(cmd="^BM", name="MSI", page="p.122", letters="oehfge2",
                orient="o", d=dict(o=None, e="B", h=None, f="Y", g="N", e2="N")),
    "plessey": dict(cmd="^BP", name="Plessey", page="p.126", letters="oehfg",
                    orient="o", d=dict(o=None, e="N", h=None, f="Y", g="N")),
    "industrial2of5": dict(cmd="^BI", name="Industrial 2 of 5", page="p.114", letters="ohfg",
                           orient="o", d=dict(o=None, h=None, f="Y", g="N")),
    "std2of5": dict(cmd="^BJ", name="Standard 2 of 5", page="p.116", letters="ohfg",
                    orient="o", d=dict(o=None, h=None, f="Y", g="N")),

    # ---- retail / EAN-UPC (p.83-143). Field data lengths are exact: the printer
    # pads/truncates on the left with zeros, so a too-long string silently prints
    # a different code. ----
    "ean8": dict(cmd="^B8", name="EAN-8", page="p.83", letters="ohfg",
                 orient="o", d=dict(o=None, h=None, f="Y", g="N"), data_len=(7,)),
    "upce": dict(cmd="^B9", name="UPC-E", page="p.85", letters="ohfge",
                 orient="o", d=dict(o=None, h=None, f="Y", g="N", e="Y"), data_len=(10,)),
    "ean13": dict(cmd="^BE", name="EAN-13", page="p.109", letters="ohfg",
                  orient="o", d=dict(o=None, h=None, f="Y", g="N"), data_len=(12,)),
    "upca": dict(cmd="^BU", name="UPC-A", page="p.142", letters="ohfge",
                 orient="o", d=dict(o=None, h=None, f="Y", g="N", e="Y"),
                 data_len=(11,), h_max=BARCODE_H_MAX_9999),
    "upcext": dict(cmd="^BS", name="UPC/EAN Extensions", page="p.137", letters="ohfg",
                   orient="o", d=dict(o=None, h=None, f="Y", g="Y"), data_len=(2, 5)),

    # ---- postal (p.78, p.150) ----
    "planet": dict(cmd="^B5", name="Planet Code", page="p.78", letters="ohfg",
                   orient="o", d=dict(o=None, h=None, f="N", g="N")),
    "postnet": dict(cmd="^BZ", name="POSTNET", page="p.150", letters="ohfgt",
                    orient="o", d=dict(o=None, h=None, f="N", g="N", t="0")),
    "usps": dict(cmd="^BZ", name="USPS IM Barcode", page="p.150", letters="ohfgt",
                 orient="o", d=dict(o=None, h=None, f="N", g="N", t="3")),

    # ---- 2D (p.64-147) ----
    "aztec": dict(cmd="^BO", name="Aztec", page="p.124", letters="abcdefg",
                  orient="a", d=dict(a=None, b=None, c="N", d="0", e="N", f="1", g=None)),
    "pdf417": dict(cmd="^B7", name="PDF417", page="p.79", letters="ohscrt",
                   orient="o", d=dict(o=None, h=None, s="0", c="1", r="3", t="N")),
    "micropdf417": dict(cmd="^BF", name="MicroPDF417", page="p.111", letters="ohm",
                        orient="o", d=dict(o=None, h=None, m="0"), h_max=BARCODE_H_MAX_9999),
    "upsmaxicode": dict(cmd="^BD", name="UPS MaxiCode", page="p.106", letters="mnt",
                        orient=None, d=dict(m="2", n="1", t="1")),
    "datamatrix": dict(cmd="^BX", name="Data Matrix", page="p.144", letters="ohscrfga",
                       orient="o", d=dict(o=None, h=None, s="0", c=None, r=None,
                                          f="6", g="~", a="1")),
    "qrcode": dict(cmd="^BQ", name="QR Code", page="p.128", letters="abcde",
                   orient="a", d=dict(a=None, b="2", c=None, d="Q", e="7")),
    "gs1databar": dict(cmd="^BR", name="GS1 DataBar", page="p.135", letters="abcdef",
                       orient="a", d=dict(a="R", b="1", c=None, d="1", e="25", f="22")),
    "tlc39": dict(cmd="^BT", name="TLC39", page="p.140", letters="ow1r1h1w2h2",
                  orient="o", d=dict(o=None)),
}

# back-compat alias: old code imported BARCODE_CMDS for (command, name) lookups
BARCODE_CMDS = {sym: (s["cmd"], s["name"]) for sym, s in BARCODE_SPECS.items()}


def magnitude_default(dpi: int) -> str:
    """Density-derived magnification used by ^B0/^BO/^BQ (p.64/124/128) and ^BR (p.135).

    The manual states it per printhead: 1 on 150 dpi, 2 on 200/203 dpi, 3 on
    300 dpi, 6 on 600 dpi — i.e. dots-per-mm / 4. ^BR words it as "12 dot = 6,
    > 8 dot is 3, 8 dot and less is 2".
    """
    per_mm = round(dpi / 25.4)
    return str(max(1, per_mm // 4))


MULTI_LETTERS = ("e2", "w1", "r1", "h1", "w2", "h2")


def split_letters(letters: str) -> list:
    """Split a manual Format-line letter string into parameter tokens.

    Most parameters are one letter, but the manual also uses e2 (^BM p.122) and
    w1/r1/h1/w2/h2 (^BT p.140), so "oehfge2" is o,e,h,f,g,e2 and not o,e,h,f,g,e,2.
    """
    out, i = [], 0
    while i < len(letters):
        two = letters[i:i + 2]
        if two in MULTI_LETTERS:
            out.append(two)
            i += 2
        else:
            out.append(letters[i])
            i += 1
    return out


def _bool(val, default):
    if val is None:
        return default
    if isinstance(val, bool):
        return "Y" if val else "N"
    v = str(val).strip().upper()
    return v if v in ("Y", "N") else ("Y" if v in ("TRUE", "YES", "1") else "N")


def escape_data(data: str, hex_indicator: str | None) -> str:
    """Return (escaped_data, used_hex).

    ^ and ~ terminate fields inside ^FD (^FD p.190). With ^FH (^FH p.193) they
    are hex-escaped (_5F/_7E); otherwise they are stripped (unavoidable).
    """
    used_hex = False
    data = str(data)
    if any(c in data for c in "^~"):
        if hex_indicator is None:
            hex_indicator = "_"
        used_hex = True
        out = []
        for ch in data:
            if ch in ("^", "~") or ch == hex_indicator:
                out.append(f"{hex_indicator}{ord(ch):02X}")
            else:
                out.append(ch)
        data = "".join(out)
    return data, used_hex


def _render_barcode(f: dict, dpi: int, issues: list, default_orient: str = "N") -> tuple[str, bool]:
    sym = str(f.get("symbology", "code128")).lower()
    spec = BARCODE_SPECS.get(sym)
    if spec is None:
        issues.append({"severity": "error", "code": "BARCODE_UNKNOWN",
                       "field": sym, "message": f"Unknown symbology '{sym}'. "
                       f"See zpl_knowledge(mode='barcodes') for the supported list."})
        return "", False
    no_hex = bool(f.get("no_hex", False))
    d = spec["d"]
    letters = split_letters(spec["letters"])
    params: dict = {}
    # Per-field ^BY: on a label built from a photo two symbols can need different
    # module widths, but ^BY is printer state — re-emit it in front of this symbol.
    by_prefix = ""
    if any(k in f for k in ("module_width", "module_ratio", "bar_height")):
        mw = int(f.get("module_width", BY_W))
        if not (1 <= mw <= 10):
            issues.append({"severity": "warning", "code": "BY_WIDTH", "field": sym,
                           "message": f"module width {mw} outside 1-10 (^BY p.148), using {BY_W}"})
            mw = BY_W
        ratio = f.get("module_ratio", BY_R)
        ratio_s = f"{ratio:g}" if isinstance(ratio, float) else str(ratio)
        bh = int(f.get("bar_height", BY_H))
        by_prefix = f"^BY{mw},{ratio_s},{bh}"

    # Orientation: which letter carries it comes from the manual's Format line
    # (^B9/^BR/^BQ/^BO use 'a' or lead with 'o'; ^BD MaxiCode has none at all).
    # Default is "current ^FW value" for every linear symbology, so an unset
    # orientation must not be forced to N — it would override ^FW.
    orient_letter = spec.get("orient")
    resolved_orient = None
    if orient_letter:
        given = f.get("orientation")
        o = str(given).upper() if given is not None else str(default_orient).upper()
        if o not in ORIENTATIONS:
            issues.append({"severity": "warning", "code": "ORIENT", "field": sym,
                           "message": f"orientation '{o}' invalid, using N (manual: N/R/I/B)"})
            o = "N"
        # An unset orientation must be *omitted*, not written as N: the manual's
        # default is "current ^FW value" (^BC p.94, ^BQ p.128 "normal"), and
        # writing N would silently override a ^FW set earlier in the job.
        if given is not None or o != "N":
            params[orient_letter] = o
        resolved_orient = o
    elif f.get("orientation"):
        issues.append({"severity": "warning", "code": "ORIENT_NA", "field": sym,
                       "message": f"{spec['name']}: {spec['cmd']} has no orientation parameter "
                                  f"(manual Format line {spec['page']})"})

    h_max = spec.get("h_max", BARCODE_H_MAX)
    # bar height override (else ^BY h is used, manual default 10 dots)
    if "height_dots" in f or "height_mm" in f:
        h = int(f["height_dots"]) if "height_dots" in f else mm2dots(f["height_mm"], dpi)
        if not (1 <= h <= h_max):
            issues.append({"severity": "error", "code": "BC_HEIGHT", "field": sym,
                           "message": f"barcode height {h} outside 1-{h_max} dots ({spec['cmd']} {spec['page']})"})
            h = max(1, min(h_max, h))
        params["h"] = str(h)

    # ---- per-symbology parameters, keyed by the manual's letters ----
    def put(letter, value, allowed=None, what="", severity="warning"):
        if value is None:
            return
        v = str(value).upper() if isinstance(value, str) else str(value)
        if allowed is not None and v not in allowed:
            issues.append({"severity": severity, "code": f"{sym.upper()}_{letter.upper()}",
                           "field": sym, "message": f"{spec['name']}: {letter} ({what}) must be "
                           f"{'/'.join(allowed)} ({spec['cmd']} {spec['page']}); got '{v}'"})
            v = d.get(letter)
            if v is None:
                return
        params[letter] = str(v)

    if sym == "datamatrix":
        if f.get("module_size_dots") is not None:      # h = module/row height, p.144
            params["h"] = str(int(f["module_size_dots"]))
        put("s", f.get("quality"), ("0", "50", "80", "100", "140", "200"),
            "quality level", "error")
        put("c", f.get("columns"), None, "columns")
        put("r", f.get("rows"), None, "rows")
        put("f", f.get("format_id"), ("1", "2", "3", "4", "5", "6"), "format ID", "error")
        put("g", f.get("escape_char"), None, "escape sequence")
        put("a", f.get("aspect_ratio"), ("1", "2"), "aspect ratio")
    elif sym == "qrcode":
        put("c", f.get("scale"), None, "magnification")
        put("d", str(f.get("ec_level", d["d"])).upper(), ("H", "Q", "M", "L"),
            "error correction", "error")
        put("b", f.get("model"), ("1", "2"), "model")
        put("e", f.get("mask"), None, "mask")
    elif sym == "aztec":
        put("b", f.get("scale"), None, "magnification")
        if f.get("eci") is not None:
            put("c", _bool(f["eci"], "N"), ("Y", "N"), "ECI indicator")
        put("d", f.get("error_control"), None, "error control")
        if f.get("menu_symbol") is not None:
            put("e", _bool(f["menu_symbol"], "N"), ("Y", "N"), "menu symbol")
        put("f", f.get("symbols"), None, "number of symbols")
        put("g", f.get("id_field"), None, "ID field")
    elif sym == "pdf417":
        put("s", f.get("security_level"), None, "security level")
        put("c", f.get("columns"), None, "columns")
        put("r", f.get("row_ratio"), None, "row height ratio")
        if f.get("truncate") is not None:
            put("t", _bool(f["truncate"], "N"), ("Y", "N"), "truncate")
    elif sym == "micropdf417":
        put("m", f.get("mode"), None, "mode", "error")
    elif sym == "msi":
        put("e", str(f.get("check_digit", d["e"])).upper(), ("A", "B", "C", "D"),
            "check digit selection")
        # manual letter is literally e2 (p.123): inserts the check digit into the
        # interpretation line. Emitting "E" (as 0.1.x did) is not a ZPL parameter.
        put("e2", _bool(f.get("insert_check_digit"), d.get("e2", "N")), ("Y", "N"),
            "insert check digit")
    elif sym == "codabar":
        put("k", str(f.get("start_char", "")).upper() or None, ("A", "B", "C", "D"),
            "start character")
        put("l", str(f.get("stop_char", "")).upper() or None, ("A", "B", "C", "D"),
            "stop character")
    elif sym == "code49":
        put("f", str(f.get("interpret_pos", "")).upper() or None, ("N", "A", "B"),
            "interpretation position")
        put("m", str(f.get("mode", d["m"])).upper(), ("A", "0", "1", "2", "3", "4", "5"),
            "starting mode")
    elif sym == "codablock":
        if f.get("security") is not None:
            put("s", _bool(f["security"], d["s"]), ("Y", "N"), "security level")
        put("c", f.get("columns"), None, "characters per row")
        put("r", f.get("rows"), None, "rows")
        put("m", str(f.get("mode", d["m"])).upper(), ("A", "E", "F"), "mode")
    elif sym == "gs1databar":
        put("b", f.get("symbology_type"), tuple(str(i) for i in range(1, 13)), "symbology type")
        put("c", f.get("magnification"), None, "magnification")
        put("d", f.get("separator_height"), ("1", "2"), "separator height")
        if "height_dots" in f or "height_mm" in f:
            params["e"] = params.pop("h")           # ^BR e = barcode height, not h
        put("f", f.get("segment_width"), None, "segment width")
    elif sym == "code128":
        put("m", str(f.get("mode", d["m"])).upper(), ("N", "U", "A", "D"),
            "mode (D = UCC/EAN mode)", "error")
    elif sym == "upsmaxicode":
        params.update({"m": str(f.get("mode", d["m"])), "n": str(f.get("symbol_number", d["n"])),
                       "t": str(f.get("total_symbols", d["t"]))})

    # interpretation line flags: f = below, g = above, but only on symbologies
    # whose Format line really gives them that meaning (^BL has g only, ^BO/^BX/
    # ^BR use those letters for other things).
    if params.get("f") is None and "f" in letters and sym not in (
            "datamatrix", "code49", "aztec", "qrcode", "gs1databar"):
        params["f"] = _bool(f.get("interpret"), d.get("f", "N"))
    if params.get("g") is None and "g" in letters and sym not in (
            "datamatrix", "aztec", "logmars"):
        params["g"] = _bool(f.get("interpret_above"), d.get("g", "N"))
    if sym == "logmars":
        params["g"] = _bool(f.get("interpret_above", f.get("interpret")), d.get("g", "N"))

    # check digit flag: only where the manual's 'e' is a check digit
    if params.get("e") is None and sym in ("code11", "code39", "code93", "i2of5",
                                           "upca", "upce", "codabar", "plessey"):
        params["e"] = _bool(f.get("check_digit"), d.get("e", "N"))

    # If a later parameter is emitted but the orientation is not, write the
    # resolved orientation instead of an empty segment ("^BU,60" -> "^BUN,60"):
    # both are legal, but the explicit form does not depend on printer state.
    if orient_letter and resolved_orient and orient_letter not in params:
        later = [l for l in params if l in letters
                 and letters.index(l) > letters.index(orient_letter)]
        if later:
            params[orient_letter] = resolved_orient

    # emit in Format-line letter order with commas; defaults omitted at the tail,
    # skipped middle parameters left as empty segments (valid ZPL: ^BCN,,Y)
    for letter in params:
        if letter not in letters:
            letters.append(letter)
    explicit = {l for l in params if l in letters and str(params[l]) != str(d.get(l))}
    last = max((letters.index(l) for l in explicit), default=-1)
    segs = [params.get(l, "") for l in letters[: last + 1]]
    while segs and segs[-1] == "":
        segs.pop()
    cmd = spec["cmd"]
    if segs:
        cmd += ",".join(segs)

    raw_data = str(f.get("data", ""))
    if sym == "qrcode":
        # ^BQ p.129-132: the ^FD string is <switches><data>. Mandatory switches:
        # error correction + data input. Manual input additionally needs a
        # character mode; mixed mode prepends its own switch and a comma.
        ec = str(params.get("d", d["d"])).upper()
        mode = str(f.get("input_mode", "A")).upper()
        if mode not in ("A", "M"):
            issues.append({"severity": "warning", "code": "QR_INPUT", "field": sym,
                           "message": "QR input mode must be A (automatic) or M (manual); using A"})
            mode = "A"
        prefix = f"{ec}{mode},"
        if mode == "M":
            cm = str(f.get("char_mode", "")).upper()
            if cm not in ("N", "A", "K") and not re.fullmatch(r"B\d{4}", cm):
                issues.append({"severity": "error", "code": "QR_CHAR_MODE", "field": sym,
                               "message": "QR manual input (M) requires a character mode: "
                                          "N (numeric), A (alphanumeric), Bxxxx (8-bit byte, "
                                          "4-digit count) or K (Kanji) (^BQ p.130)"})
                cm = ""
            prefix += cm
        mm = f.get("mixed_mode")
        if mm:
            try:
                code_no = int(mm.get("code_no", 1))
                divisions = int(mm.get("divisions", 1))
                parity = str(mm.get("parity", "00")).upper()
                prefix = f"D{code_no:02d}{divisions:02d}{parity},{prefix}"
            except (TypeError, ValueError, AttributeError):
                issues.append({"severity": "warning", "code": "QR_MIXED", "field": sym,
                               "message": "mixed_mode needs code_no/divisions/parity; ignored"})
        raw_data = f"{prefix}{raw_data}"
    data, used_hex = escape_data(raw_data, None if no_hex else "_")
    fh = "^FH" if used_hex else ""
    # honor field coordinates (^FO before the barcode command, p.201)
    pos = ""
    if any(k in f for k in ("x_mm", "x_dots", "y_mm", "y_dots")):
        x, y = _xy(f, dpi)
        pos = f"^FO{x},{y}{_fz(f)}"
    return pos + by_prefix + cmd + fh + "^FD" + data + "^FS", used_hex


def _fz(f: dict) -> str:
    """^FO/^FT third parameter z = justification (p.201/205, firmware V60.14+).

    0 = left, 1 = right, 2 = auto (script dependent). Omitted unless asked for,
    because its printer default is "last accepted ^FW value".
    """
    z = f.get("justify")
    if z is None:
        return ""
    z = str(z)
    if z not in FO_JUSTIFY:
        return ""
    return f",{z}"


def _render_text(f: dict, dpi: int, issues: list) -> tuple[str, bool]:
    font_file = f.get("font_file")  # ^A@ (p.62): call a downloadable/resident font by full name
    if font_file:
        name = str(font_file).strip().upper()
        m = re.fullmatch(r"(R|E|B|A):([A-Z0-9_.\-]+\.(TTF|FNT|TTE))", name)
        if not m:
            issues.append({"severity": "error", "code": "FONT_FILE", "field": name,
                           "message": "font_file must be 'E:NAME.TTF' (drive R/E/B/A + name."
                                      "TTF|.FNT|.TTE) (^A@ p.62)"})
            font_file = None
    font = f.get("font")
    h = f.get("size_mm")
    if h is not None:
        h_dots = mm2dots(h, dpi)
    elif f.get("size_dots") is not None:
        h_dots = int(f["size_dots"])          # pixel/photo-derived sizes come in dots
    else:
        h_dots = None
    if font is None:
        # ^A p.60: font f "defaults to the last value of the ^CF command", and
        # ^CF's power-up value is A (p.154). Font A is bitmapped — it only takes
        # 1-10x multiples of its 9x5 matrix — so an explicit dot size has to use
        # the scalable font 0 instead.
        font = "0" if h_dots is not None else CF_FONT
    font = str(font)
    if not font_file and not re.fullmatch(r"[0-9A-Z]", font):
        issues.append({"severity": "error", "code": "FONT", "field": font,
                       "message": "font must be 0-9 or A-Z (^A p.60)"})
        font = "0"
    if h_dots is not None and not (10 <= h_dots <= 32000):
        issues.append({"severity": "error", "code": "TEXT_SIZE", "field": font,
                       "message": f"height {h_dots} dots outside scalable range 10-32000 (^A p.60)"})
        h_dots = None
    w_dots = None
    if f.get("width_mm"):
        w_dots = mm2dots(f["width_mm"], dpi)
    elif f.get("width_dots"):
        w_dots = int(f["width_dots"])
    o = str(f.get("orientation", "N")).upper()
    if o not in ORIENTATIONS:
        issues.append({"severity": "warning", "code": "ORIENT", "field": font,
                       "message": f"orientation '{o}' invalid, using N"})
        o = "N"
    origin = f.get("origin", "FO")  # ^FO absolute (p.201) vs ^FT relative text position (p.205)
    if origin not in ("FO", "FT"):
        issues.append({"severity": "error", "code": "ORIGIN", "field": font,
                       "message": "origin must be FO (absolute) or FT (after last text field)"})
        origin = "FO"
    if "x_dots" in f:
        x = int(f["x_dots"])
    elif "x_mm" in f:
        x = mm2dots(f["x_mm"], dpi)
    else:
        x = 0
    y = int(f.get("y_dots", 0)) if "y_dots" in f else (mm2dots(f.get("y_mm", 0), dpi) if "y_mm" in f else 0)
    for label, v in (("x", x), ("y", y)):
        if not (0 <= v <= FO_MAX):
            issues.append({"severity": "error", "code": "POS", "field": font,
                           "message": f"{label} {v} outside 0-{FO_MAX} dots (^FO p.201)"})
    no_hex = bool(f.get("no_hex", False))
    raw = str(f.get("data", ""))
    if len(raw.encode("utf-8", "replace")) > FD_MAX:
        issues.append({"severity": "error", "code": "FD_LENGTH", "field": font,
                       "message": f"field data is {len(raw.encode('utf-8', 'replace'))} bytes; "
                                  f"^FD takes up to {FD_MAX} bytes (^FD p.190)"})
    data, used_hex = escape_data(raw, None if no_hex else "_")
    cmd = f"^{origin}{x},{y}{_fz(f)}"
    if font_file:
        # ^A@ o,h,w,d:f.x (p.62): name carries over to later ^A@ without a name.
        # Emit the width explicitly (manual examples are ^A@N,50,50,B:CYRI_UB.FNT);
        # square glyphs are what CJK fonts want, so width defaults to height.
        w_out = w_dots if w_dots else (h_dots if h_dots is not None else "")
        a = f"^A@{o},{h_dots if h_dots is not None else ''},{w_out}"
        a += f",{str(font_file).strip().upper()}"
    else:
        a = f"^A{font}{o}"
        if h_dots is not None:
            a += f",{h_dots}"
            if w_dots:
                a += f",{w_dots}"
    parts = [cmd, a]
    block = f.get("block")
    if block:
        bw_dots = block.get("width_dots") or (mm2dots(block.get("width_mm", 0), dpi) if block.get("width_mm") else 0)
        lines = int(block.get("lines", 1))
        if not (1 <= lines <= 9999):
            issues.append({"severity": "warning", "code": "FB_LINES", "field": font,
                           "message": f"block lines {lines} outside 1-9999 (^FB p.186), using 1"})
            lines = 1
        # ^FB p.186 c = dots *added to or removed from* each line, -9999..9999 —
        # not an absolute line height. 'line_height' is the old (wrong) name.
        lh = int(block.get("line_spacing", block.get("line_height", 0)))
        if not (FB_SPACING[0] <= lh <= FB_SPACING[1]):
            issues.append({"severity": "warning", "code": "FB_SPACING", "field": font,
                           "message": f"line spacing {lh} outside -9999..9999 (^FB p.186)"})
            lh = 0
        align = str(block.get("alignment", "L")).upper()
        if align not in ("L", "C", "R", "J"):
            issues.append({"severity": "warning", "code": "FB_ALIGN", "field": font,
                           "message": f"alignment '{align}' not in L/C/R/J (^FB p.186)"})
            align = "L"
        hi = int(block.get("hanging_indent", 0))
        # ^FB sits between ^A and ^FD (manual example p.186)
        parts.append(f"^FB{bw_dots},{lines},{lh},{align},{hi}")
    if f.get("reverse"):
        # ^FR p.203: "applies to only one field and has to be specified each time"
        parts.append("^FR")
    parts.append("^FH" if used_hex else "")
    parts.append("^FD" + data)
    parts.append("^FS")
    return "".join(parts), used_hex


def _render_box(f: dict, dpi: int) -> str:
    """^GB graphic box (p.210). 'note' and 'box' are the same ZPL command."""
    x, y, w, h = _xywh(f, dpi)
    t = int(f.get("thickness", GB_THICKNESS_DEFAULT))       # ^GB p.210: t default 1
    c = str(f.get("color", "B")).upper()
    r = max(0, min(GB_ROUNDING_MAX, int(f.get("corner_rounding", 0))))  # r 0-8
    return f"^FO{x},{y}{_fz(f)}^GB{w},{h},{t},{c},{r}" + ("^FR" if f.get("reverse") else "") + "^FS"


def _render_circle(f: dict, dpi: int) -> str:
    x, y = _xy(f, dpi)
    d = f.get("diameter_dots") or (mm2dots(f.get("diameter_mm", 0), dpi) if f.get("diameter_mm") else GC_DEFAULT)
    d = max(3, min(4095, int(d)))  # ^GC p.212: 3-4095, larger values become 4095
    t = int(f.get("thickness", 1))
    c = str(f.get("color", "B")).upper()
    return f"^FO{x},{y}{_fz(f)}^GC{d},{t},{c}" + ("^FR" if f.get("reverse") else "") + "^FS"


def _xy(f: dict, dpi: int) -> tuple[int, int]:
    """Per-axis: dots win on that axis only, the other axis still honours mm.

    Mixing (x_dots with y_mm) is legitimate -- e.g. centring a barcode needs an
    exact dot offset horizontally while the vertical position is a layout number
    in mm. Treating "x_dots present" as "ignore y" silently dropped the barcode
    to y=0.
    """
    x = int(f["x_dots"]) if "x_dots" in f else mm2dots(f.get("x_mm", 0), dpi)
    y = int(f["y_dots"]) if "y_dots" in f else mm2dots(f.get("y_mm", 0), dpi)
    return x, y


def _xywh(f: dict, dpi: int) -> tuple[int, int, int, int]:
    """Same per-axis rule as _xy (dots win per dimension, mm for the rest)."""
    x, y = _xy(f, dpi)
    w = int(f["width_dots"]) if "width_dots" in f else mm2dots(f.get("width_mm", 0), dpi)
    h = int(f["height_dots"]) if "height_dots" in f else mm2dots(f.get("height_mm", 0), dpi)
    return x, y, w, h


def mm2dots(mm, dpi: int) -> int:
    """mm -> dots at the printhead dpi (1 dot = 1/25.4 mm)."""
    return int(round(float(mm) * dpi / 25.4))


def _is_cjk(s: str) -> bool:
    return any(ord(c) > 0x2E80 for c in str(s))


def build_label(spec: dict) -> tuple[str, list]:
    """Build ZPL II from a label spec. Returns (zpl, issues[]).

    Spec keys (mm for sizes, auto-converted to dots at label['dpi']):
      dpi, width_mm, height_mm, quantity, darkness (^MD), char_encoding (^CI),
      print_speed/slew_speed/backfeed_speed (^PR), mirror (^PM), invert (^PO),
      shift_left (^LS), label_top (^LT), media_tracking {mode, black_mark_offset} (^MN),
      print_mode {mode, media_loss} (^MM), fields: text/barcode/note/box/circle/image/reverse.
    """
    issues: list = []
    dpi = int(spec.get("dpi", 203))
    if dpi not in (152, 200, 203, 300, 600):
        issues.append({"severity": "warning", "code": "DPI", "field": "label",
                       "message": f"dpi {dpi} unusual — Zebra printheads are 6/8/12/24 dots/mm "
                                  f"(152/203/300/600 dpi per ^GB p.210 note)"})
    w_mm, h_mm = float(spec.get("width_mm", 0)), float(spec.get("height_mm", 0))
    pw = spec.get("print_width_dots") or (mm2dots(w_mm, dpi) if w_mm else 0)
    ll = spec.get("label_length_dots") or (mm2dots(h_mm, dpi) if h_mm else 0)
    out = ["^XA"]
    if pw:
        if not (2 <= pw <= PW_MAX):
            issues.append({"severity": "error", "code": "PW", "field": "label",
                           "message": f"print_width {pw} outside 2-{PW_MAX} dots (^PW p.329)"})
        out.append(f"^PW{pw}")
    if ll:
        if not (1 <= ll <= LL_MAX):
            issues.append({"severity": "error", "code": "LL", "field": "label",
                           "message": f"label_length {ll} outside 1-{LL_MAX} dots (^LL p.294)"})
        out.append(f"^LL{ll}")
    ci = spec.get("char_encoding", None)
    text_fields = [f for f in spec.get("fields", []) if str(f.get("type", "text")).lower() in ("text", "barcode")]
    cjk_present = any(_is_cjk(f.get("data", "")) for f in text_fields)
    if cjk_present and ci is None:
        ci = CI_UNICODE  # ^CI28 recommended for Kanji/Unicode (^CI p.157)
        issues.append({"severity": "warning", "code": "CI_CJK", "field": "label",
                       "message": "non-Latin text found -> ^CI28 (Unicode) emitted; make sure a CJK-capable "
                                  "font is active: a resident TrueType via font_file '^A@' (e.g. "
                                  "E:SIMSUN.TTF / E:HANS.TTF on ZR668), font 15/16 on ZT230/ZE500/Xi4/"
                                  "ZM400/RZ600, or a .TTF downloaded via ~DY"})
    if ci is not None:
        out.append(f"^CI{ci}")
    if spec.get("barcode_defaults"):
        b = spec["barcode_defaults"]
        r = b.get("ratio", BY_R)
        ratio = f"{r:g}" if isinstance(r, float) else str(r)
        out.append(f"^BY{int(b.get('module_width', BY_W))},{ratio},{int(b.get('bar_height', BY_H))}")
    if spec.get("default_font"):
        d = spec["default_font"]
        out.append(f"^CF{str(d.get('font', CF_FONT))},{int(d.get('height', CF_H))},{int(d.get('width', CF_W))}")
    default_orient = "N"
    if spec.get("default_orientation"):
        o = str(spec["default_orientation"]).upper()
        if o in ORIENTATIONS:
            default_orient = o
            out.append(f"^FW{o}")
    if spec.get("mirror"):
        out.append("^PM" + _bool(spec["mirror"], "N"))
    if spec.get("invert"):
        # ^PO p.322: the parameter is N or I (invert) — "Y" is not a valid value.
        inv = spec["invert"]
        v = "I" if (inv is True or str(inv).strip().upper() in ("I", "Y", "TRUE", "1", "YES")) else "N"
        out.append("^PO" + v)
    if spec.get("darkness") is not None:
        d = float(spec["darkness"])
        # ~SD sets ABSOLUTE darkness (p.333, "##", 00-30); ^MD is a relative delta
        # (p.301) that accumulates across jobs — use ~SD for a deterministic value.
        if 0.0 <= d <= SD_MAX:
            # ~SD## is a two-digit value (p.333); the Xi4/XiIIIPlus family also
            # takes 0.1 increments, e.g. ~SD8.3
            out.append(f"~SD{int(d):02d}" if d == int(d) else f"~SD{d:g}")
        else:
            if not (MD_MIN <= d <= MD_MAX):
                issues.append({"severity": "error", "code": "MD", "field": "label",
                               "message": f"darkness {d} outside {MD_MIN}..{MD_MAX} (^MD p.301)"})
            out.append(f"^MD{d:g}")
    if spec.get("print_speed") or spec.get("slew_speed") or spec.get("backfeed_speed"):
        vals = []
        for key in ("print_speed", "slew_speed", "backfeed_speed"):
            v = spec.get(key)
            if v is None:
                vals.append("")
                continue
            v = str(v).upper()
            if v not in PR_VALUES:
                issues.append({"severity": "error", "code": "PR_SPEED", "field": "label",
                               "message": f"^PR speed '{v}' not in 1-12 or A-E "
                                          f"(A=2, B=3, C=4, D=6, E=8 ips) (^PR p.326)"})
                v = "2"
            vals.append(v)
        while vals and vals[-1] == "":
            vals.pop()
        out.append("^PR" + ",".join(vals))
    if spec.get("shift_left") is not None:
        ls = int(spec["shift_left"])
        if not (LS_MIN <= ls <= LS_MAX):
            issues.append({"severity": "error", "code": "LS", "field": "label",
                           "message": f"shift_left {ls} outside {LS_MIN}..{LS_MAX} dots (^LS p.296)"})
        out.append(f"^LS{ls}")
    if spec.get("label_top") is not None:
        lt = int(spec["label_top"])
        if not (LT_MIN <= lt <= LT_MAX):
            issues.append({"severity": "warning", "code": "LT", "field": "label",
                           "message": f"label_top {lt}: all printers accept {LT_MIN}..{LT_MAX} dots "
                                      f"(600 dpi -240..240, HC100 0..120) (^LT p.297)"})
        out.append(f"^LT{lt}")
    mt = spec.get("media_tracking")
    if mt:
        mode = str(mt.get("mode", "N")).upper()
        if mode not in MN_MODES:
            issues.append({"severity": "error", "code": "MN", "field": "label",
                           "message": f"media_tracking mode '{mode}' not in N/Y/W/M/A/V (^MN p.307); "
                                      f"N continuous, Y/W web, M mark, A auto, V variable length"})
            mode = "N"
        off = int(mt.get("black_mark_offset", 0))
        if off and not (MN_OFFSET[0] <= off <= MN_OFFSET[1]):
            issues.append({"severity": "warning", "code": "MN_OFFSET", "field": "label",
                           "message": f"black mark offset {off} outside {MN_OFFSET[0]}..{MN_OFFSET[1]} "
                                      f"dots for most printers (^MN p.307)"})
        out.append(f"^MN{mode},{off}")
    pm = spec.get("print_mode")
    if pm:
        mode = str(pm.get("mode", "T")).upper()
        if mode not in MM_MODES:
            issues.append({"severity": "error", "code": "MM", "field": "label",
                           "message": f"print_mode '{mode}' not in T/P/R/A/C/D/F/L/U/K "
                                      f"(T tear, P peel, R rewind, A applicator, C cutter, "
                                      f"F RFID, K kiosk) (^MM p.305)"})
            mode = "T"
        # ^MM b is the prepeel select (p.305), not a media-loss flag
        out.append(f"^MM{mode},{_bool(pm.get('prepeel', pm.get('media_loss')), 'N')}")

    used_hex = False
    for f in spec.get("fields", []):
        t = str(f.get("type", "text")).lower()
        if t == "text":
            chunk, uh = _render_text(f, dpi, issues)
        elif t == "barcode":
            chunk, uh = _render_barcode(f, dpi, issues, default_orient)
        elif t in ("note", "box"):
            chunk, uh = _render_box(f, dpi), False
        elif t == "circle":
            chunk, uh = _render_circle(f, dpi), False
        elif t == "reverse":
            # legacy: a bare ^FR is not a field (p.203 applies it to one field).
            # Prefer {"reverse": true} on the field it should affect.
            chunk, uh = "^FR", False
            issues.append({"severity": "warning", "code": "FR_STANDALONE", "field": "reverse",
                           "message": "^FR applies to a single field (^FR p.203); put "
                                      "\"reverse\": true on the field instead of a separate field"})
        elif t == "image":
            name = f.get("name", "")
            chunk, uh = (f"^FO{_xy(f, dpi)[0]},{_xy(f, dpi)[1]}^XGR:{name},1,1^FS" if name else ""), False
            if not name:
                issues.append({"severity": "error", "code": "IMG_NAME", "field": "image",
                               "message": "image field needs 'name' (download first via printer_graphics)"})
        else:
            issues.append({"severity": "error", "code": "FIELD_TYPE", "field": t,
                           "message": f"unknown field type '{t}' (text/barcode/note/box/circle/image/reverse)"})
            continue
        used_hex |= uh
        out.append(chunk)

    q = int(spec.get("quantity", 1))
    if not (1 <= q <= 99999999):
        issues.append({"severity": "error", "code": "PQ", "field": "label",
                       "message": f"quantity {q} outside 1-99999999 (^PQ p.324)"})
        q = 1
    # ^PQ q,p,r,o,e (p.324): pause/cut count, replicates per serial, override pause,
    # cut on error label. Only emit the extra parameters when they are asked for.
    pq_tail = spec.get("pq_extra") or {}
    if q != 1 or pq_tail:
        segs = [str(q),
                str(int(pq_tail.get("pause", 0))),
                str(int(pq_tail.get("replicates", 0)))]
        if pq_tail.get("override_pause") is not None:
            segs.append(_bool(pq_tail["override_pause"], "N"))
        if pq_tail.get("cut_on_error") is not None:
            if len(segs) < 4:
                segs.append("N")
            segs.append(_bool(pq_tail["cut_on_error"], "Y"))
        while segs and segs[-1] == "":
            segs.pop()
        out.append("^PQ" + ",".join(segs))
    out.append("^XZ")
    zpl = "".join(out)

    # symbology-specific data rules (manual comments + common practice)
    for f in spec.get("fields", []):
        if str(f.get("type", "text")).lower() != "barcode":
            continue
        sym = str(f.get("symbology", "")).lower()
        data = str(f.get("data", ""))
        spec = BARCODE_SPECS.get(sym, {})
        # ---- retail lengths are EXACT: the printer pads/truncates on the left
        # with zeros (^B8 p.83, ^B9 p.85, ^BE p.109, ^BU p.142, ^BS p.137), so an
        # extra check digit silently shifts every digit. ----
        if spec.get("data_len") and not (data.isdigit() and len(data) in spec["data_len"]):
            want = " or ".join(str(n) for n in spec["data_len"])
            issues.append({"severity": "error", "code": "BC_LENGTH", "field": sym,
                           "message": f"{spec['name']} takes exactly {want} digits "
                                      f"({spec['cmd']} {spec['page']}); got {len(data)!r}. "
                                      f"The printer computes the check digit itself and pads "
                                      f"/truncates on the left, so '11 digits + check' is wrong."})
        if sym == "i2of5" and not (data.isdigit() and len(data) % 2 == 0):
            issues.append({"severity": "warning", "code": "I2OF5_DATA", "field": sym,
                           "message": "Interleaved 2 of 5 needs an even digit count; the printer "
                                      "adds a leading 0 if it gets an odd one (^B2 p.69)"})
        if sym in ("planet", "postnet", "usps") and not data.isdigit():
            issues.append({"severity": "warning", "code": "POSTAL_DATA", "field": sym,
                           "message": "postal barcodes take digits only (^B5 p.78 / ^BZ p.150)"})
        if sym == "msi" and not data.isdigit():
            issues.append({"severity": "warning", "code": "MSI_DATA", "field": sym,
                           "message": "MSI barcode takes digits only (^BM p.122)"})
        if sym in ("upcext",):
            issues.append({"severity": "warning", "code": "UPCEXT_PAIR", "field": sym,
                           "message": "an extension only makes sense next to its main symbol — "
                                      "place it at the same height as the ^BU/^B9 barcode (^BS p.137)"})
        if sym not in ("qrcode", "datamatrix", "aztec", "pdf417", "micropdf417", "upsmaxicode") and _is_cjk(data):
            issues.append({"severity": "warning", "code": "BC_CJK", "field": sym,
                           "message": f"{sym}: CJK in linear barcode data is not supported; use qrcode/datamatrix"})
        # ^BX p.146: quality 200 truncates at 3072 bytes and uses _1/_2 for FNC,
        # quality 0-140 caps at 596 characters.
        if sym == "datamatrix":
            q = str(f.get("quality", "0"))
            limit = 3072 if q == "200" else 596
            if len(data.encode("utf-8", "replace")) > limit:
                issues.append({"severity": "error", "code": "DM_LENGTH", "field": sym,
                               "message": f"Data Matrix quality {q} takes at most {limit} bytes "
                                          f"(^BX p.146); longer data is truncated or nothing prints"})
        if not used_hex and any(c in data for c in "^~"):
            issues.append({"severity": "warning", "code": "HEX_NEEDED", "field": sym,
                           "message": "field data contains ^ or ~ — hex escaping was disabled "
                                      "(no_hex); those characters terminate the field and were stripped"})
    return zpl, issues


def validate_label(spec: dict) -> list:
    _, issues = build_label(spec)
    return issues


# ^ works as a 1-char command prefix (^A0N, ^FO) or a 2-char one (^BC, ^BY).
# Matching greedily takes the 2-char token, which turned ^A0N into "^A0" (not a
# command at all) and needed 29 junk entries in the catalog to stay quiet.
_CMD_TOKEN_RE = re.compile(r"([\^~])([A-Z@][A-Z0-9]?|[0-9])")


def _scan_commands(zpl: str, catalog: set) -> tuple[set, list]:
    """Return (found tokens, unknown tokens), preferring 2-char commands."""
    found, unknown = set(), []
    for m in _CMD_TOKEN_RE.finditer(zpl):
        sig, body = m.group(1), m.group(2)
        two = sig + body[:2]
        one = sig + body[:1]
        if two in catalog:
            found.add(two)
        elif one in catalog:
            found.add(one)
        else:
            unknown.append(two if re.fullmatch(r"[A-Z@][A-Z0-9]", body) else two[:2])
    return found, unknown


def validate_zpl(zpl: str) -> list:
    """Light validation of raw ZPL against the manual's command set.

    Field data (^FD…) is blanked before the command scan: a label whose data
    contains '^' or '~' (escaped with ^FH, or a customer string) must not be
    reported as "unknown command".
    """
    issues = []
    scan = re.sub(r"\^FD[^\^]*", "^FD", zpl)
    catalog = KNOWN_COMMANDS
    if not catalog:
        # Library users may call validate_zpl without ever importing .catalog
        # (the MCP server does it via side effect). Install on first use rather
        # than reporting every legitimate command as UNKNOWN_CMD.
        from . import catalog as _catalog
        catalog = _catalog.install()
    _found, unknown = _scan_commands(scan, catalog)
    for tok in sorted(set(unknown)):
        issues.append({"severity": "warning", "code": "UNKNOWN_CMD", "field": tok,
                       "message": f"{tok} not found in the ZPL II manual's command catalog"})
    # ^BQ p.129-132: field data must open with <error correction><input mode>,
    # optionally preceded by the mixed-mode switch and followed by a character
    # mode (mandatory when the input mode is M).
    for m in re.finditer(r"\^BQ[^\^]*\^FD([^\^]*)", zpl):
        data = m.group(1)
        if not re.match(r"^(D\d{6},)?[HQML][AM],", data):
            issues.append({"severity": "error", "code": "QR_FD_PREFIX", "field": "^BQ",
                           "message": "QR field data must open with <error correction>"
                                      "<input mode>, e.g. ^FDQA,<data> (^BQ p.129) — got "
                                      f"'^FD{data[:12]}'"})
        elif re.match(r"^(D\d{6},)?[HQML]M,", data) and not re.match(
                r"^(D\d{6},)?[HQML]M,(N|A|K|B\d{4})", data):
            issues.append({"severity": "error", "code": "QR_CHAR_MODE", "field": "^BQ",
                           "message": "QR manual input (M) needs a character mode: N, A, "
                                      "Bxxxx or K (^BQ p.130)"})
    if zpl.count("^XA") != zpl.count("^XZ"):
        issues.append({"severity": "error", "code": "BRACKETS", "field": "format",
                       "message": "^XA/^XZ unbalanced — every format needs both (^XA p.370 / ^XZ p.375)"})
    # ^PT / ^PO checks that cost one regex and catch real typos
    for m in re.finditer(r"\^PO([A-Z0-9])", zpl):
        if m.group(1) not in PO_VALUES:
            issues.append({"severity": "error", "code": "PO_VALUE", "field": "^PO",
                           "message": f"^PO takes N or I (invert) — '{m.group(1)}' is not a "
                                      f"valid value (^PO p.322)"})
    if not re.search(r"[\^~][A-Z0-9]", zpl):
        issues.append({"severity": "warning", "code": "NO_CMD", "field": "format",
                       "message": "no ZPL commands found in payload"})
    return issues


# Filled by knowledge.py at import of server; keep a conservative default here.
KNOWN_COMMANDS: set = set()
