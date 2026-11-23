"""Raster images -> ZPL ``^GFA`` graphic fields.

Why this module exists
----------------------
``^GF`` is the only way to print a bitmap that is *not* already sitting in the
printer's memory: ``^FO100,100^GFA,8000,8000,80,<ASCII hex>`` (^GF p.215). Until
0.3 that was out of scope here, so "print this PNG logo" had no path except
``~DG`` download + ``^XGR`` recall.

Two input paths, on purpose:

* ``from_rows()`` takes packed rows of bits and needs **nothing but the stdlib**;
  a camera pipeline or a label renderer can hand over its own bitmap.
* ``from_image()`` / ``from_path()`` take a PIL image or a file (PNG/JPEG/…), so
  the ``[render]`` extra is required. The import happens inside the call and the
  error names the extra, the same way ``zpl_core.render`` does.

What the printer expects
------------------------
``^GFA,b,c,d,data`` — b = total bytes transmitted, c = total bytes of the graphic
(``bytes_per_row * rows``), d = bytes per row. The manual requires b and c to
match for ASCII downloads (p.215), and both are capped at 99999. Bits are
MSB-first inside each byte, 1 = black, and every row is padded to a byte
boundary — that padding is what makes c ``bpr * h`` and not ``ceil(w*h/8)``.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["Bitmap", "from_rows", "from_image", "from_path", "GFA_MAX_BYTES"]

GFA_MAX_BYTES = 99999       # ^GF p.215: b and c are 1 to 99999


class Bitmap:
    """A 1-bit raster: ``rows`` is a list of ``bytes``, each already byte-padded."""

    __slots__ = ("width", "height", "rows")

    def __init__(self, width: int, height: int, rows: list[bytes]):
        if width <= 0 or height <= 0:
            raise ValueError(f"bitmap must be at least 1x1 dots, got {width}x{height}")
        if len(rows) != height:
            raise ValueError(f"expected {height} rows, got {len(rows)}")
        bpr = (width + 7) // 8
        for i, row in enumerate(rows):
            if len(row) != bpr:
                raise ValueError(f"row {i} is {len(row)} bytes, expected {bpr} "
                                 f"({width} dots, byte-padded)")
        self.width, self.height, self.rows = width, height, rows

    @property
    def bytes_per_row(self) -> int:
        return (self.width + 7) // 8

    @property
    def nbytes(self) -> int:
        return self.bytes_per_row * self.height

    def hex_data(self) -> str:
        return "".join(f"{b:02X}" for row in self.rows for b in row)

    def to_gfa(self, x: int | None = None, y: int | None = None) -> str:
        """``[^FOx,y]^GFA,b,c,d,<hex>`` — the graphic field, optionally positioned."""
        total = self.nbytes
        if total > GFA_MAX_BYTES:
            raise ValueError(
                f"^GF takes at most {GFA_MAX_BYTES} bytes ({self.bytes_per_row} bytes/row "
                f"x {self.height} rows = {total}); scale the image down or split it")
        pos = "" if x is None or y is None else f"^FO{int(x)},{int(y)}"
        return f"{pos}^GFA,{total},{total},{self.bytes_per_row},{self.hex_data()}"

    def ascii_art(self, max_width: int = 78, on: str = "#", off: str = ".") -> str:
        """A terminal preview — 1 dot = 1 char, downsampled if wider than max_width."""
        step = max(1, -(-self.width // max_width))
        out = []
        for r, row in enumerate(self.rows):
            if r % step:
                continue
            line = []
            for c in range(0, self.width, step):
                byte = row[c // 8]
                bit = (byte >> (7 - (c % 8))) & 1
                line.append(on if bit else off)
            out.append("".join(line))
        return "\n".join(out)

    def __repr__(self) -> str:
        return f"<Bitmap {self.width}x{self.height} dots, {self.nbytes} bytes>"


def from_rows(rows, width: int | None = None) -> Bitmap:
    """Build a bitmap from rows of bits (1 = black). Stdlib only.

    ``rows`` may be a list of 0/1 sequences (lists, tuples, str of "01") or a list
    of already-packed ``bytes``. When rows are unpacked, ``width`` defaults to the
    length of the first row; every row is padded to a byte boundary.
    """
    rows = list(rows)
    if not rows:
        raise ValueError("no rows given")
    first = rows[0]
    if isinstance(first, (bytes, bytearray)):
        if width is not None and len(first) != (width + 7) // 8:
            raise ValueError("packed rows do not match width")
        return Bitmap(width or len(first) * 8, len(rows), [bytes(r) for r in rows])

    bits = [[1 if (ch in ("1", 1, True, "#", "*")) else 0
             for ch in (r if isinstance(r, str) else r)] for r in rows]
    w = width or len(bits[0])
    if any(len(r) != w for r in bits):
        raise ValueError("all rows must be the same width")
    bpr = (w + 7) // 8
    packed = []
    for r in bits:
        buf = bytearray(bpr)
        for i, bit in enumerate(r):
            if bit:
                buf[i // 8] |= 0x80 >> (i % 8)
        packed.append(bytes(buf))
    return Bitmap(w, len(packed), packed)


def _pil():
    try:
        from PIL import Image       # noqa: F401
    except ModuleNotFoundError as exc:      # pragma: no cover - depends on extras
        raise ImportError(
            "zpl_core.raster needs the [render] extra, but PIL is not installed.\n"
            '  fix: pip install "zpl-core[render]"'
        ) from exc
    return Image


def from_image(img, *, width_dots: int | None = None, height_dots: int | None = None,
               mode: str = "threshold", threshold: int = 128,
               invert: bool = False) -> Bitmap:
    """PIL image -> Bitmap.

    ``mode``:
      * ``threshold`` — everything darker than ``threshold`` becomes black. Best
        for logos, line art and text (crisp edges, no noise).
      * ``floyd`` — Floyd–Steinberg error diffusion. Best for photos and
        gradients: thermal printers are 1-bit, so dithering is the only way to
        keep tones.
      * ``halftone`` — PIL's ordered dither.

    ``width_dots`` / ``height_dots`` scale the image (aspect ratio is kept when
    only one of them is given). ``invert`` swaps black and white, which is what
    you want for white-on-black artwork.
    """
    Image = _pil()
    if not hasattr(img, "convert"):
        raise TypeError("from_image expects a PIL.Image; use from_rows() for raw bits")

    alpha_white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    alpha_white.paste(img.convert("RGBA"), (0, 0), img.convert("RGBA"))
    gray = alpha_white.convert("L")      # transparent areas become white paper

    w, h = gray.size
    if width_dots or height_dots:
        if width_dots and height_dots:
            size = (int(width_dots), int(height_dots))
        elif width_dots:
            size = (int(width_dots), max(1, round(h * width_dots / w)))
        else:
            size = (max(1, round(w * height_dots / h)), int(height_dots))
        gray = gray.resize(size, Image.LANCZOS)

    if invert:
        gray = gray.point(lambda p: 255 - p)

    m = str(mode).lower()
    if m == "threshold":
        bw = gray.point(lambda p: 0 if p < int(threshold) else 255).convert("1", dither=Image.NONE)
    elif m in ("floyd", "dither", "fs"):
        bw = gray.convert("1", dither=Image.FLOYDSTEINBERG)
    elif m == "halftone":
        bw = gray.convert("1", dither=Image.DITHERED1) if hasattr(Image, "DITHERED1") else \
            gray.convert("1", dither=Image.FLOYDSTEINBERG)
    else:
        raise ValueError(f"unknown mode {mode!r} (threshold / floyd / halftone)")

    return _bitmap_from_pil(bw)


def _bitmap_from_pil(bw) -> Bitmap:
    """PIL 1-bit image -> Bitmap without relying on PIL's buffer byte order."""
    w, h = bw.size
    bpr = (w + 7) // 8
    px = bw.load()
    rows = []
    for y in range(h):
        buf = bytearray(bpr)
        for x in range(w):
            if px[x, y] == 0:            # 0 = black in mode "1"
                buf[x // 8] |= 0x80 >> (x % 8)
        rows.append(bytes(buf))
    return Bitmap(w, h, rows)


def from_path(path: str | Path, **kw) -> Bitmap:
    """Load an image file (PNG/JPEG/BMP/GIF/TIFF) and convert it."""
    Image = _pil()
    with Image.open(str(path)) as img:
        return from_image(img, **kw)