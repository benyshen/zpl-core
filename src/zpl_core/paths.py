"""Where the data files that ship with zpl-core live.

Inside the package (``zpl_core/data``) for a normal install; override with
``ZPL_CORE_DATA`` when running from a source tree or a vendored copy.
"""
from __future__ import annotations

import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ZPL_CORE_DATA") or (PKG_DIR / "data"))


def data_file(*parts: str) -> Path:
    """Path to a bundled data file, e.g. data_file("ocr", "ppocr_keys_v1.txt")."""
    return DATA_DIR.joinpath(*parts)


def ocr_models_dir() -> Path:
    return data_file("ocr")
