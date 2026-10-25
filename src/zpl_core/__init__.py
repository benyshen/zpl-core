"""zpl-core — the ZPL label engine behind zebra-printer-mcp and zebra-printer-skill.

One package, three consumers:

    zpl_core.builder    label spec -> ZPL II (mm->dots, 28 symbologies, ^A@ TrueType)
    zpl_core.knowledge  command catalog, defaults, barcode/status/SGD tables
    zpl_core.render     ZPL -> PNG preview            (extra: render)
    zpl_core.photo      photo of a label -> ZPL       (extra: ocr)
    zpl_core.transport  TCP 9100 / Windows RAW / USB / preview
    zpl_core.xlsx_batch one label per spreadsheet row  (pure stdlib)

The core (build/validate/knowledge/transport/xlsx) is stdlib-only. Heavier paths
are optional extras so a caller that just wants ZPL does not pull 15 MB of OCR
models into a build::

    pip install zpl-core            # build, validate, send, status
    pip install zpl-core[render]    # + offline PNG preview
    pip install zpl-core[ocr]       # + photo -> ZPL (ships PP-OCRv4 weights)
    pip install zpl-core[all]
"""
from __future__ import annotations

import importlib

__version__ = "0.1.1"

from . import builder, catalog, knowledge, transport, xlsx_batch  # noqa: E402,F401
from .paths import DATA_DIR, data_file  # noqa: E402,F401

__all__ = [
    "__version__", "builder", "catalog", "knowledge", "transport", "xlsx_batch",
    "render", "photo", "ocr", "vision", "DATA_DIR", "data_file",
]

# 重模块（Pillow / cv2 / onnxruntime）按需加载，import zpl_core 不拖时间
_LAZY = {"render", "photo", "ocr", "vision"}

# 每个懒加载模块依赖哪个 extra（缺依赖时据此给出可复制的安装命令）
_EXTRA_FOR = {"render": "render", "photo": "ocr", "ocr": "ocr", "vision": "ocr"}


def __getattr__(name: str):
    if name in _LAZY:
        try:
            module = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as exc:
            extra = _EXTRA_FOR[name]
            missing = exc.name or "a dependency"
            raise ImportError(
                f"zpl_core.{name} needs the [{extra}] extra, but {missing} is not installed.\n"
                f'  fix: pip install "zpl-core[{extra}]"'
            ) from exc
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
