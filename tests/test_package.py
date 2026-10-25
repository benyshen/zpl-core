"""Package-level invariants for zpl-core.

Run after `pip install -e .[all]`:
    python tests/test_package.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FAILED = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILED.append(name)


import zpl_core  # noqa: E402
from zpl_core import builder, knowledge, transport, xlsx_batch  # noqa: E402

# ---------------------------------------------------------------- 版本与数据

check("version is 0.1.0", zpl_core.__version__ == "0.1.0", zpl_core.__version__)

data_dir = Path(zpl_core.DATA_DIR)
check("data dir sits inside the package",
      "site-packages" in str(data_dir) or "zpl_core" in str(data_dir), str(data_dir))
check("command catalog present", (data_dir / "command_catalog.txt").exists())

cmds = knowledge.known_commands()
check("catalog loads 253 commands", len(cmds) == 253, str(len(cmds)))

ocr_dir = data_dir / "ocr"
for f, size in (("ch_PP-OCRv4_det_infer.onnx", 4745517),
                ("ch_PP-OCRv4_rec_infer.onnx", 10857958),
                ("ppocr_keys_v1.txt", 26249)):
    got = ocr_dir / f
    check(f"ocr asset {f}", got.exists() and got.stat().st_size == size,
          f"{got.stat().st_size if got.exists() else 'missing'} bytes")

# ---------------------------------------------------------------- 懒加载边界

check("import zpl_core stays stdlib-only",
      "cv2" not in sys.modules and "onnxruntime" not in sys.modules and "PIL" not in sys.modules,
      ", ".join(m for m in ("cv2", "onnxruntime", "PIL") if m in sys.modules) or "clean")

try:
    ocr = zpl_core.ocr
    avail = ocr.available()
    check("ocr models resolve from the package", avail.get("ok") is True, str(avail)[:90])
    check("ocr module imported on demand", ocr.__name__ == "zpl_core.ocr")
except Exception as exc:  # pragma: no cover - dependency missing
    check("ocr models resolve from the package", False, f"{type(exc).__name__}: {exc}")

try:
    render = zpl_core.render
    check("render module imported on demand", callable(getattr(render, "render", None)))
except Exception as exc:
    check("render module imported on demand", False, f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- 引擎行为

zpl, issues = builder.build_label({
    "dpi": 203, "width_mm": 60, "height_mm": 40,
    "fields": [
        {"type": "text", "x_mm": 3, "y_mm": 3, "height_dots": 30, "data": "ZPL-CORE"},
        {"type": "barcode", "symbology": "code128", "x_mm": 3, "y_mm": 10,
         "height_dots": 60, "data": "ABC-123"},
    ],
})
check("build_label emits ^XA/^XZ", zpl.startswith("^XA") and zpl.rstrip().endswith("^XZ"))
check("build_label has no issues", not issues, str(issues)[:90])

issues_ok = builder.validate_zpl("^XA^FO10,10^A0N,30,30^FDhi^FS^XZ")
check("validate_zpl accepts a clean label", issues_ok == [], str(issues_ok)[:90])

issues_bad = builder.validate_zpl("^XA^WQ^FDx^FS^XZ")     # ^ZZ 恰好是手册命令，别拿它当反例
check("validate_zpl flags an unknown command",
      any(i.get("code") == "UNKNOWN_CMD" for i in issues_bad), str(issues_bad)[:90])

rows = [["张伟", "A001"], ["李娜", "B002"]]
job = xlsx_batch.plan_specs(rows, name_col=0, id_col=1,
                            width_mm=50, height_mm=30, skip_header=False)
check("xlsx_batch plans one label per row", len(job) == 2, str(len(job)))

# ---------------------------------------------------------------- 干净度

src = Path(zpl_core.__file__).parent
hits = [p.name for p in src.glob("*.py") if "zebra_mcp" in p.read_text(encoding="utf-8")]
check("no zebra_mcp references left in the package", not hits, ", ".join(hits) or "clean")

out = subprocess.run([sys.executable, "-c", "import zpl_core; print(zpl_core.__version__)"],
                     capture_output=True, text=True)
check("fresh interpreter imports the package", out.returncode == 0 and "0.1.0" in out.stdout,
      (out.stdout or out.stderr).strip()[:80])

print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED: {FAILED}")
    raise SystemExit(1)
print("ALL PACKAGE CHECKS PASSED")
