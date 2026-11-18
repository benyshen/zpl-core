"""ZPL II / Link-OS knowledge base.

Built from the extracted ZPL II Programming Guide text (data/zpl_manual_full.txt,
from zpl-zbi2-pg-en-202609.pdf). The command catalog is parsed from the manual's
own 'ZPL Commands' index so validate_zpl() flags only real manual commands; the
SGD list combines variables that appear in the manual with a curated set of
Link-OS SGD names (techdocs.zebra.com/link-os).
"""
from __future__ import annotations

import json
import re

from .paths import DATA_DIR, data_file

DATA = DATA_DIR
MANUAL_TXT = data_file("zpl_manual_full.txt")

# ---------------------------------------------------------------------------
# commands.json — generated from the manual: {command: {page, name, params}}
#
# It is the authority for *page numbers and Format-line parameters*. The prose
# in COMMAND_NOTES below carries defaults, ranges and gotchas, and every page
# number in it is overwritten at import by the page in commands.json — the two
# can no longer drift apart (0.1.x had ^LS p.322 vs the manual's p.296, ^LT
# p.335 vs 297, ^PM p.318 vs 319, ^PO p.308 vs 322: the notes were wrong).
# ---------------------------------------------------------------------------
COMMANDS_FILE = data_file("commands.json")


def _load_commands() -> dict:
    try:
        return json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


COMMANDS: dict = _load_commands()

# ---------------------------------------------------------------------------
# Command catalog parsed from the manual text
# ---------------------------------------------------------------------------

_CMD_RE = re.compile(r"[~^][A-Z0-9@]{1,2}")  # '@' keeps ^A@ (Scalable TrueType) in the catalog

# Commands introduced in the manual (headings like "ZPL Commands ^XY" or
# "ZPL System Commands ~XY"). Fallback: the set of all ^/~ 1-2 char tokens.
_KNOWN: set[str] | None = None
CATALOG_TXT = data_file("command_catalog.txt")  # static export; regenerate with scripts/extract_manual.py


def known_commands() -> set[str]:
    global _KNOWN
    if _KNOWN is not None:
        return _KNOWN
    _KNOWN = set()
    # preferred: commands.json, generated from the manual's own command sections
    # (page + Format line per command). It lists only real commands, unlike the
    # old token scrape, which needed "^A0", "^AB", "^2", "~0" and 25 more
    # non-commands just so that "^A0N,30" would not read as UNKNOWN_CMD.
    if COMMANDS:
        _KNOWN = set(COMMANDS)
        return _KNOWN
    try:
        _KNOWN = {t for t in CATALOG_TXT.read_text(encoding="utf-8").split() if t}
        if _KNOWN:
            return _KNOWN
    except OSError:
        pass
    # fallback: parse the extracted manual text if it happens to be on disk
    try:
        text = MANUAL_TXT.read_text(encoding="utf-8", errors="replace")
        _KNOWN = set(_CMD_RE.findall(text))
    except OSError:
        pass
    if not _KNOWN:
        _KNOWN = {f"^{c}" for c in "ABCDEFGILMNOPQRSTUVWXZ"} | {f"~{c}" for c in "DEGHILNPRYZ"}
    return _KNOWN


# ---------------------------------------------------------------------------
# Command knowledge (verified against data/zpl_params_notes.txt, manual pages)
# ---------------------------------------------------------------------------

COMMAND_NOTES: dict[str, dict] = {
    "^XA": {"page": 370, "name": "Start Format", "syntax": "^XA",
            "notes": "Begins a label format. All format commands must lie between ^XA and ^XZ."},
    "^XZ": {"page": 375, "name": "End Format", "syntax": "^XZ",
            "notes": "Ends the format begun by ^XA and starts printing."},
    "^FO": {"page": 201, "name": "Field Origin", "syntax": "^FO x, y",
            "defaults": {"x": 0, "y": 0}, "range": "0-32000 dots",
            "notes": "Absolute position on the label, in dots, from the top-left corner (or the origin set by ^LH/^OM)."},
    "^FT": {"page": 205, "name": "Field Origin, Text Position", "syntax": "^FT x, y",
            "defaults": {"x": 0, "y": 0}, "range": "0-32000 dots",
            "notes": "Position relative to the end of the previous text field — use for flowing text fields."},
    "^A": {"page": 60, "name": "Scalable/Bitmapped Font", "syntax": "^Afo,h,w",
           "defaults": {"f": "last ^CF value (power-up A)", "o": "last ^FW value",
                        "h": "last ^CF value (power-up 9)", "w": "last ^CF value (power-up 5)"},
           "range": "scalable h/w 10-32000 dots; bitmapped h/w are 1-10x multiples of the font matrix; f = A-Z and 0-9",
           "notes": "Font f is required for the field but defaults to the ^CF font. Font 0 is the "
                    "scalable font, A-Z/0-9 are resident or downloaded. Bitmapped fonts (A-H) only "
                    "accept multiples of their matrix, so an arbitrary dot size needs font 0 or ^A@."},
    "^CF": {"page": 154, "name": "Change the Alphanumeric Default Font", "syntax": "^CFf,h,w",
            "defaults": {"f": "A (power-up)", "h": 9, "w": 5},
            "range": "f A-Z/0-9; h,w 0-32000",
            "notes": "Default for every following alphanumeric field. Defining only h or w keeps the "
                     "other proportional to the font matrix."},
    "^FD": {"page": 190, "name": "Field Data", "syntax": "^FD data",
            "notes": "Prints data. ^, ~, ^FS etc. terminate the field; hex-escape them with ^FH (default indicator _) or use ^FH<indicator>."},
    "^FS": {"page": 251, "name": "Field Terminator", "syntax": "^FS",
            "notes": "Ends a field and sends it to the print buffer."},
    "^FH": {"page": 193, "name": "Hex Escape On", "syntax": "^FH [indicator]",
            "defaults": {"indicator": "_"}, "notes": "Enables hex escaping in field data: _5F=_, _5E=^, _7E=~. Indicator can be any printable char except ^ ~ and alphanumerics."},
    "^BC": {"page": 94, "name": "Code 128", "syntax": "^BC [orientation, [height, [interpret, [check digit, [mode]]]]]",
            "defaults": {"orientation": "N", "interpret": "Y", "check digit": "N", "mode": "N"},
            "range": "height 1-32000 dots; orientation N/R/I/B",
            "notes": "Mode U forces uppercase; mode A optimizes data encoding. Height default comes from ^BY h."},
    "^BQ": {"page": 128, "name": "QR Code", "syntax": "^BQ [model, [magnification size, [error correction]]]",
            "defaults": {"model": 2, "magnification": "0 (auto)", "error correction": "Q"},
            "range": "model 1/2; magnification 1-100; error correction H/Q/M/L",
            "notes": "^FW orientation does not rotate ^BQ. Data is encoded per QR standards."},
    "^BX": {"page": 144, "name": "Data Matrix", "syntax": "^BX [orientation, [quality, [columns, rows]]]",
            "defaults": {"orientation": "N", "quality": 200, "columns": 0, "rows": 1},
            "range": "quality 0/50/80/100/140/200; columns 1-44 (144 for large); rows 1-44 (144)",
            "notes": "ECC200 recommended for industrial use; quality sets minimum data size."},
    "^B7": {"page": 79, "name": "PDF417", "syntax": "^B7 [orientation, [height, [security level, [columns, [row height ratio, [truncate]]]]]]",
            "defaults": {"height": 0, "security level": 0, "columns": 1, "row height ratio": 3, "truncate": "N"},
            "range": "security level 0-8; row height ratio 0-1000",
            "notes": "columns=1 means auto-size; height 0 derives from ^BY."},
    "^B2": {"page": 68, "name": "Interleaved 2 of 5", "syntax": "^B2 [orientation, [height, [interpret, [check digit, [required count, [print count]]]]]]",
            "defaults": {"interpret": "Y", "check digit": "N", "count": "N"},
            "notes": "Data must be an even number of digits."},
    "^BY": {"page": 148, "name": "Bar Code Default Parameters", "syntax": "^BY [width, [ratio, [height]]]",
            "defaults": {"width": 2, "ratio": 3.0, "height": 10},
            "range": "width 1-10 dots; ratio 2.0-3.0 in 0.1 increments (no effect on fixed-ratio symbologies); height 1-32000 dots",
            "notes": "Global defaults for all following barcodes unless overridden on the barcode command. Power-up initial w=2, h=10."},
    "^PW": {"page": 329, "name": "Print Width", "syntax": "^PW width",
            "defaults": {"width": 406}, "range": "2-32000 dots",
            "notes": "Dots across the label (print-head width direction). 406 = 50 mm at 203 dpi; 832 = 104 mm."},
    "^LL": {"page": 294, "name": "Label Length", "syntax": "^LL length",
            "defaults": {"length": 0}, "range": "1-32000 dots",
            "notes": "Media length in dots along the feed direction."},
    "^LH": {"page": 293, "name": "Label Home", "syntax": "^LHx,y", "defaults": {"x": 0, "y": 0},
            "notes": "Sets the field-origin offset for the whole label."},
    "^PM": {"page": 319, "name": "Mirror Image", "syntax": "^PMa", "defaults": {"a": "N"},
            "notes": "Mirrors the whole label left-right; stays active until ^PMN or power-off."},
    "^PO": {"page": 322, "name": "Print Orientation", "syntax": "^POa", "defaults": {"a": "N"},
            "notes": "Inverts the label 180 degrees. Values are N (normal) and I (invert) — Y is NOT valid. "
                     "It mirrors x,y coordinates, so a different ^LH may be needed to bring the print back."},
    "^MD": {"page": 301, "name": "Set Print Darkness", "syntax": "^MD value",
            "defaults": {"value": 0}, "range": "-30 to +30 (or 0-5 depending on model)",
            "notes": "Adjusts print darkness from the printer default; positive darkens."},
    "^PR": {"page": 326, "name": "Print Rate", "syntax": "^PRp,s,b",
            "range": "1-12 (ips: 1=25.4 mm/s ... 12=304.8 mm/s) plus aliases A=2, B=3, C=4, D=6, E=8",
            "notes": "Print, slew and backfeed speed in inches per second; model dependent. Some models drop "
                     "back to their default speed at power-off."},
    "^PQ": {"page": 324, "name": "Print Quantity", "syntax": "^PQq,p,r,o,e",
            "defaults": {"q": 1, "p": 0, "r": 0, "o": "N", "e": "Y"},
            "range": "q,p 1-99999999; r 0-99999999; o = override pause N/Y; e = cut on error label N/Y",
            "notes": "Prints the whole format q times; p pauses/cuts every p labels; r replicates each serial "
                     "number; e controls cutting after a voided RFID label."},
    "^LT": {"page": 297, "name": "Label Top", "syntax": "^LTx",
            "range": "all printers -120..120 dots; 600 dpi -240..240; HC100 0..120",
            "notes": "Moves the whole format up/down relative to the top edge; negative moves it toward the top. "
                     "A value must be given or the command is ignored."},
    "^MN": {"page": 307, "name": "Media Tracking", "syntax": "^MNa,b",
            "defaults": {"b": 0},
            "range": "a = N continuous, Y web sensing, W web sensing, M mark sensing, A auto-detect, "
                     "V continuous variable length; b = -120..283 dots (-240..566 at 600 dpi)",
            "notes": "There is no 'B' media type — black mark is M. b is only used when a = M."},
    "^MM": {"page": 305, "name": "Print Mode", "syntax": "^MMa,b",
            "defaults": {"a": "model dependent", "b": "N"},
            "range": "a = T tear, P peel, R rewind, A applicator, C cutter, D delayed cutter, F RFID, "
                     "L/U reserved, K kiosk; b = prepeel select N/Y",
            "notes": "b is the prepeel select, not a media-loss flag. Values are model dependent and the "
                     "command is ignored if the printer does not support the option."},
    "^FB": {"page": 186, "name": "Field Block", "syntax": "^FB width, [lines, [line height, [alignment, [hanging indent]]]]",
            "defaults": {"b": 1, "c": 0, "d": "L", "e": 0},
            "range": "a 0-label width; b 1-9999; c -9999..9999; d L/C/R/J; e 0-9999; data <= 3K",
            "notes": "Word-wrap field data to width (dots) at the ^FO/^FT position; sits between ^A and ^FD. "
                     "c ADDS or REMOVES space per line (negative tightens), it is not a line height. "
                     "a smaller than the font width prints nothing. Escapes: \\& = CR/LF, \\(*) = soft hyphen."},
    "^FR": {"page": 203, "name": "Field Reverse Print", "syntax": "^FR",
            "notes": "Reverses one field (white over black). It applies to a single field, so it has to be "
                     "issued for each field; ^LR does it for the whole label."},
    "^CI": {"page": 155, "name": "Change International Font/Encoding",
            "syntax": "^CIa,s1,d1,s2,d2,...",
            "defaults": {"a": "0 (power-up)"},
            "range": "a = 0-13 (Zebra CP850 regional sets), 17 (deprecated UCS-2 BE), 24 (single-byte Asian), "
                     "26 (multibyte Asian with ASCII transparency), 27 (Zebra CP1252), 28/29/30 (Unicode UTF-8 / "
                     "UTF-16BE / UTF-16LE), 31 (CP1250, G-Series), 33-36 (CP1251/1253/1254/1255); "
                     "18-23 and 25 reserved. s/d pairs remap characters (0-255), up to 256 pairs.",
            "notes": "p.156-157 lists the accepted values: there is NO 936 or 950 code page in ZPL — Chinese is "
                     "^CI28 (UTF-8) with a CJK-capable font, or ^CI24/^CI26 for the Asian single/multibyte pages. "
                     "The s,d pairs let you remap glyph positions (a = 0-13 only). CJK in practice: send UTF-8 with "
                     "^CI28 and call a TrueType font by name with ^A@ — e.g. ZR668 ships E:SIMSUN.TTF and "
                     "E:HANS.TTF in flash (verified on ZR668-200dpi V86.20.21Z)."},
    "^A@": {"page": 62, "name": "Scalable/Downloadable Font by Name", "syntax": "^A@ orientation, [height, [width, [drive:font.ext]]]",
            "defaults": {"orientation": "N", "drive": "R:"},
            "range": "drive R/E/B/A; ext .FNT .TTF .TTE; h/w 10-32000 dots (scalable)",
            "notes": "Calls a font by full name, e.g. ^A@N,28,28,E:SIMSUN.TTF. The chosen font carries over to "
                     "subsequent ^A@ without a name. Resident flash fonts listed via the printer web /dir page "
                     "or ~DY directory query. Pair with ^CI28 (UTF-8) for CJK."},
    "^GB": {"page": 210, "name": "Graphic Box", "syntax": "^GBw,h,t,c,r",
           "defaults": {"t": 1, "c": "B", "r": 0}, "range": "w,h = t-32000; t 1-32000; r 0-8",
           "notes": "Same command draws boxes and lines. Omit w/h and you get a solid box the size of t "
                    "(thickness 0 fills). Colors in the manual are B (black) and W (white) only. "
                    "r is the degree of corner rounding, 0-8."},
    "^GC": {"page": 212, "name": "Graphic Circle", "syntax": "^GCd,t,c",
           "defaults": {"d": 3, "t": 1, "c": "B"}, "range": "d 3-4095 (larger becomes 4095); t 2-4095",
           "notes": "Circle border, thickness extends inward; a thickness equal to the radius fills it."},
    "^LS": {"page": 296, "name": "Label Shift", "syntax": "^LSa",
            "defaults": {"a": 0}, "range": "-9999 to 9999 dots",
            "notes": "Shifts every field position left/right; the manual's formula is Z-130 ^LHx + ^FOx = ^LSa. "
                     "Negative values are allowed; it must be issued before the first ^FS of the format."},
    "^FW": {"page": 280, "name": "Field Orientation", "syntax": "^FW N|R|I|B", "defaults": {"orientation": "N"},
            "notes": "Default field rotation for following text/barcode fields (some 2D codes ignore it)."},
    "^OM": {"page": 298, "name": "Origin Set", "syntax": "^OM value", "defaults": {"value": 0},
            "notes": "Field-origin origin mode (0=upper left, 1=lower left, 2=lower right, 3=upper right)."},
    "^XG": {"page": 372, "name": "Graphic Field (stored)", "syntax": "^XG name, [color, [magnification]]",
            "notes": "Recalls a stored .GRF image (~DG download, device E/R)."},
    "~DG": {"page": 444, "name": "Download Graphics", "syntax": "~DGname.ext, format, byte count, data",
           "notes": "Downloads a bitmap to printer memory (E=erase after print, R=store). ASCII hex encoding, row format default."},
    "~DY": {"page": 434, "name": "Download Data", "syntax": "~DYname.ext, format, device, byte count, data",
           "notes": "Downloads fonts (.FNT/.TTF), images, formats (.FMT) or ZPL II macros to E/R/B memory."},
    "^CWF": {"page": 159, "name": "Downloaded Font", "syntax": "^CWF name.ext",
            "notes": "Uses a downloaded scalable font as the default font."},
    "^SB": {"page": 249, "name": "Set Media Position", "syntax": "^SB value", "defaults": {"value": 0},
            "range": "0-1000 dots", "notes": "Media position adjustment for mis-registration."},
    "^MDF": {"page": 343, "name": "Media Feed Adjustment", "syntax": "^MDF value", "defaults": {"value": 0},
             "range": "0-32000 dots", "notes": "Distance to advance media before printing the next label."},
    "^MC": {"page": 316, "name": "Media Count", "syntax": "^MC",
            "notes": "Counts labels for media-loss tracking with ^MM media loss."},
    "^SC": {"page": 244, "name": "Scale Field", "syntax": "^SC x, y", "defaults": {"x": 1.0, "y": 1.0},
            "range": "0.1-10", "notes": "Scale the next field by multipliers."},
    "^DE": {"page": 347, "name": "Delete Element", "syntax": "^DE device", "defaults": {"device": "E"},
            "notes": "Deletes stored formats (B=buffer, E=EPROM). Run outside ^XA/^XZ."},
    "^DS": {"page": 350, "name": "Directory List", "syntax": "^DS",
            "notes": "Lists stored files in printer memory. Run outside ^XA/^XZ."},
    "^DF": {"page": 352, "name": "Delete File", "syntax": "^DF name", "notes": "Deletes one stored file."},
    "^DD": {"page": 351, "name": "Download Format", "syntax": "^DD name",
            "notes": "Begins storing a format to memory; ends with ^END. Run outside ^XA/^XZ."},
    "^CD": {"page": 346, "name": "Capture Format", "syntax": "^CD name, [device]",
            "notes": "Stores the format buffer as a named .FMT (device E/R)."},
}

BARCODE_NOTES: dict[str, dict] = {
    "code128": {"cmd": "^BC", "page": 94, "data": "ASCII; Mod 103 check digit is always present",
                "notes": "Mode m: N none, U UCC Case (data forced to 19 digits), A automatic (printer picks "
                         "the subset), D UCC/EAN mode — starts in the right subset, emits FNC1 before the AIs "
                         "and keeps the parentheses in the human-readable line"},
    "code39": {"cmd": "^B3", "page": 70, "data": "0-9 A-Z - . $ / + % space", "notes": "check digit optional"},
    "code93": {"cmd": "^BA", "page": 87, "data": "full ASCII", "notes": ""},
    "i2of5": {"cmd": "^B2", "page": 68, "data": "digits, even count", "notes": "count option for required length"},
    "planet": {"cmd": "^B5", "page": 78, "data": "digits", "notes": "USPS legacy postal"},
    "postnet": {"cmd": "^BZ", "page": 150, "data": "digits", "notes": "USPS legacy; t=0 postnet"},
    "usps": {"cmd": "^BZ", "page": 150, "data": "digits incl. check", "notes": "t=3 IM barcode"},
    "upsmaxicode": {"cmd": "^BD", "page": 106, "data": "62-char sets by mode", "notes": "optically read, not scanned"},
    "pdf417": {"cmd": "^B7", "page": 79, "data": "full ASCII", "notes": "security 0-8, auto columns"},
    "micropdf417": {"cmd": "^BF", "page": 111, "data": "full ASCII",
                    "notes": "Format ^BFo,h,m — m is the mode 0-33, not PDF417's s/c/r"},
    "codabar": {"cmd": "^BK", "page": 118, "data": "0-9 - . , $ / + A-D", "notes": "start/stop A-D"},
    "msi": {"cmd": "^BM", "page": 122, "data": "digits",
            "notes": "Format ^BMo,e,h,f,g,e2: e = check digit selection (A none, B 1 Mod 10, C 2 Mod 10, "
                     "D 1 Mod 11 + 1 Mod 10, default B); e2 = insert the check digit into the "
                     "interpretation line (N/Y, default N)"},
    "plessey": {"cmd": "^BP", "page": 126, "data": "0-9 A-F", "notes": ""},
    "logmars": {"cmd": "^BL", "page": 120, "data": "Code 39 subset, uppercased; Mod 43 check digit",
                "notes": "Format ^BLo,h,g — DoD/LOGMARS application of Code 39; g is the line ABOVE the symbol, there is no f"},
    "industrial2of5": {"cmd": "^BI", "page": 114, "data": "digits", "notes": "continuous numeric, not self-checking"},
    "std2of5": {"cmd": "^BJ", "page": 116, "data": "digits", "notes": ""},
    "ean13": {"cmd": "^BE", "page": 109, "data": "exactly 12 digits (13th/check digit is computed)",
              "notes": "JAN-13 needs the first two non-zero digits to be 49. For UCC/EAN-14 use ^B2."},
    "ean8": {"cmd": "^B8", "page": 83, "data": "exactly 7 digits (check digit is computed)",
             "notes": "JAN-8 needs the first two non-zero digits to be 49."},
    "upca": {"cmd": "^BU", "page": 142, "data": "exactly 11 digits (check digit is computed and printed)",
             "notes": "^BU, not ^B9 — ^B9 is UPC-E. Data is padded/truncated on the left with zeros; "
                      "pair with a 2/5-digit extension (^BS) for magazines and books"},
    "upce": {"cmd": "^B9", "page": 85, "data": "exactly 10 digits (5-digit manufacturer + 5-digit product)",
             "notes": "Printer zero-suppresses to the short form; enter the full 10 characters. "
                      "^B0 is Aztec, not UPC-E"},
    "upcext": {"cmd": "^BS", "page": 137, "data": "2 or 5 digits", "notes": "ISBN/ISSN add-on"},
    "gs1databar": {"cmd": "^BR", "page": 135, "data": "GTIN/AI based",
                    "notes": "Format ^BRa,b,c,d,e,f: a=orientation, b=symbology type 1-12 (default 1), c=magnification, d=separator height, e=barcode height, f=segment width"},
    "code49": {"cmd": "^B4", "page": 74, "data": "0-9 $+./- ",
               "notes": "Format ^B4o,h,f,m: f = interpretation N/A/B, m = mode"},
    "code11": {"cmd": "^B1", "page": 66, "data": "digits and -", "notes": "check digit 1 or 2 (e=Y/N)"},
    "tlc39": {"cmd": "^BT", "page": 140, "data": "6 digits (ECI), then a comma, up to 25-char serial, "
               "then optional comma-separated fields (total <= 150 bytes)",
               "notes": "Format ^BTo,w1,r1,h1,w2,h2: Code 39 (w1/r1/h1) plus a 4-column MicroPDF417 "
                        "(w2/h2). Defaults are density-derived and TCIF-compliant; a seventh "
                        "non-comma character after the ECI means only Code 39 prints"},
    "codablock": {"cmd": "^BB", "page": 90, "data": "varies by mode A/B/C", "notes": "stacked 2D"},
    "datamatrix": {"cmd": "^BX", "page": 144, "data": "full ASCII/numeric; <= 596 chars for quality 0-140, "
                   "3072 bytes for quality 200",
                   "notes": "Format ^BXo,h,s,c,r,f,g,a. s = quality/ECC: 0 (default), 50/80/100/140 "
                            "(convolution), 200 (Reed-Solomon, recommended for new work). f = format ID "
                            "1-6 (default 6, unused at quality 200). g = escape character (default ~, "
                            "_ on newer firmware). a = aspect ratio 1 square / 2 rectangular. "
                            "GS1 DataMatrix = quality 200 with FNC1 inserted by the escape sequence: "
                            "_1 (or ~1 on older firmware) immediately before the AIs; >8 is the Code 128 "
                            "FNC1 (^FD p.104), not the Data Matrix one"},
    "qrcode": {"cmd": "^BQ", "page": 128, "data": "numeric/alphanumeric/byte/Kanji",
               "notes": "^FD data must open with <EC><input mode>, e.g. ^FDQA,<data> (p.129: Mandatory); model 1/2, EC H/Q/M/L, mask 0-7"},
    "aztec": {"cmd": "^BO", "page": 124, "data": "full ASCII", "notes": "1-33 rows"},
}

# ---------------------------------------------------------------------------
# Link-OS SGD commands (from the manual's examples + the Link-OS SGD reference
# at techdocs.zebra.com/link-os; verify names against the printer with SGD getvar)
# ---------------------------------------------------------------------------

SGD_COMMANDS: dict[str, dict] = {
    "! U1 setvar \"device.ip.address\" \"192.168.1.10\"\r\n^XA": {
        "name": "device.ip.address", "kind": "setvar", "page_link": "link-os/sgd.html",
        "notes": "Static IP; also set device.ip.address.mode static/dhcp/link-local"},
    "! U1 getvar \"$device.serial_number\"": {"name": "$device.serial_number", "kind": "getvar"},
    "! U1 getvar \"$net.interface.EtherNet:port.0.status\"": {"name": "net interface status", "kind": "getvar"},
    "! U1 setvar \"device.date\" \"10/22/26\"": {"name": "device.date", "kind": "setvar"},
    "! U1 setvar \"device.time\" \"12:00:00\"": {"name": "device.time", "kind": "setvar"},
    "! U1 getvar \"device.ip.address\"": {"name": "device.ip.address", "kind": "getvar"},
    "! U1 setvar \"wlan.ip.address.mode\" \"dhcp\"": {"name": "wlan.ip.address.mode", "kind": "setvar"},
    "! U1 setvar \"wlan.ssid\" \"MyNetwork\"": {"name": "wlan.ssid", "kind": "setvar"},
    "! U1 setvar \"wlan.wpa2.psk\" \"secret\"": {"name": "wlan.wpa2.psk", "kind": "setvar",
        "notes": "WPA2 passphrase — set locally at the printer UI when possible; avoid sending secrets"},
    "! U1 setvar \"ip.rtcmode\" \"ntp\"": {"name": "ip.rtcmode", "kind": "setvar"},
    "! U1 setvar \"ip.ntp_server1.address\" \"pool.ntp.org\"": {"name": "ip.ntp_server1.address", "kind": "setvar"},
    "! U1 setvar \"printer.print.darkness\" \"10\"": {"name": "printer.print.darkness", "kind": "setvar"},
    "! U1 setvar \"printer.print.speed\" \"4\"": {"name": "printer.print.speed", "kind": "setvar",
        "notes": "inches per second, model-dependent range"},
    "! U1 setvar \"printer.calibration.media\" \"calibrate\"": {"name": "printer.calibration.media", "kind": "setvar",
        "notes": "triggers a media calibration (also 'do:calibration')"},
    "! U1 setvar \"printer.language.code.page\" \"28\"": {"name": "printer.language.code.page", "kind": "setvar"},
    "! U1 setvar \"sensor.paper.type\" \"noncontinuous\"": {"name": "sensor.paper.type", "kind": "setvar",
        "notes": "continuous | noncontinuous | mark | black mark"},
    "! U1 setvar \"device.language\" \"ZPL\"": {"name": "device.language", "kind": "setvar"},
    "! U1 setvar \"device.backup.reset\" \"on\"": {"name": "device.backup.reset", "kind": "setvar"},
    "! U1 getvar \"$~\"": {"name": "getvar $~ (all variables)", "kind": "getvar",
        "notes": "dumps every SGD variable/value — the Link-OS way to read printer config"},
    "! U1 getvar \"printer.feed.dimension.label.length\"": {"name": "printer.feed.dimension.label.length", "kind": "getvar"},
    "! U1 getvar \"printer.width.print\"": {"name": "printer.width.print", "kind": "getvar"},
    "! U1 setvar \"device.snmp\" \"enable\"": {"name": "device.snmp", "kind": "setvar"},
    "! U1 setvar \"device.web_server\" \"enable\"": {"name": "device.web_server", "kind": "setvar"},
    "! U1 setvar \"printer.status.poll_interval\" \"5\"": {"name": "printer.status.poll_interval", "kind": "setvar"},
    "! U1 setvar \"printer.status.filter\" \"64570\"": {"name": "printer.status.filter", "kind": "setvar",
        "notes": "host:port for async status notifications (ZBI II status protocol)"},
    "! U1 getvar \"$printer.status.poll_interval\"": {"name": "poll interval read", "kind": "getvar"},
    "! U1 do:calibration": {"name": "do:calibration", "kind": "do",
        "notes": "media/sensor calibration action"},
}

# Status message codes (manual 'Status Commands' / ZBI II error hex words)
STATUS_NOTES: dict[str, dict] = {
    "0000": {"name": "PRINTER READY", "level": "ok"},
    "0001": {"name": "PRINTER NOT READY", "level": "warn"},
    "0002": {"name": "HEAD OPEN", "level": "error"},
    "0003": {"name": "PAPER OUT", "level": "error"},
    "0004": {"name": "REPRINT ERROR", "level": "error"},
    "0008": {"name": "HEAD COLD", "level": "warn"},
    "0010": {"name": "PAUSED", "level": "warn"},
    "0080": {"name": "OUT OF MEMORY", "level": "error"},
    "0200": {"name": "MEDIA OUT OF SPEC", "level": "warn"},
    "1000": {"name": "STOPPED DUE TO ERROR", "level": "error"},
    "2000": {"name": "RECALL ERROR", "level": "error"},
    "4000": {"name": "MEDIA JAM", "level": "error"},
    "8000": {"name": "TOO HOT", "level": "warn"},
}


def _barcode_command_notes() -> dict[str, dict]:
    """One entry per barcode command, derived from builder.BARCODE_SPECS.

    Every symbology generate_zpl can emit therefore also resolves through
    zpl_knowledge(mode='command', query='^B9'), which previously answered
    "not found" for ^B0/^B1/^B9/^BA/^BB/^BD/^BE/^BF/^BI/^BJ/^BK/^BM/^BO/^BP/^BR/^BS.
    """
    from .builder import BARCODE_SPECS  # local import: builder has no knowledge dep
    notes: dict[str, dict] = {}
    for sym, spec in BARCODE_SPECS.items():
        cmd = spec["cmd"]
        if cmd in COMMAND_NOTES or cmd in notes:
            continue
        page = spec["page"].lstrip("p.")
        fmt = cmd + ",".join(spec["letters"])
        notes[cmd] = {
            "page": int(page),
            "name": spec["name"],
            "syntax": fmt,
            "notes": f"Format line {fmt} (manual p.{page}). Symbology '{sym}' — "
                     f"see zpl_knowledge(mode='barcodes') for data rules.",
        }
    return notes


COMMAND_NOTES.update(_barcode_command_notes())


def _sync_pages() -> None:
    """Overwrite every note's page with the page in commands.json.

    COMMAND_NOTES was written by hand and drifted: ^LS said p.322 (manual 296),
    ^LT p.335 (297), ^PM p.318 (319), ^PO p.308 (322), ^FS p.251 (204), ^XG
    p.372 (373), ~DG p.444 (175) and more. The generated table wins.
    """
    for cmd, meta in COMMAND_NOTES.items():
        ref = COMMANDS.get(cmd)
        if ref and ref.get("page"):
            meta["page"] = ref["page"]


_sync_pages()


def page_of(name: str) -> int | None:
    """Manual page of a command, or None if the manual has no such section."""
    ref = COMMANDS.get(name)
    return ref["page"] if ref else None


def get_command(name: str) -> dict | None:
    return COMMAND_NOTES.get(name)


def search(pattern: str, limit: int = 20) -> list[dict]:
    pat = re.compile(pattern, re.I)
    results = []
    for cmd, meta in COMMAND_NOTES.items():
        hay = f"{cmd} {meta.get('name','')} {meta.get('notes','')} {meta.get('syntax','')}"
        if pat.search(hay):
            results.append({"command": cmd, **meta})
            if len(results) >= limit:
                break
    return results


__all__ = ["known_commands", "COMMAND_NOTES", "BARCODE_NOTES", "SGD_COMMANDS",
           "STATUS_NOTES", "get_command", "search", "MANUAL_TXT"]
