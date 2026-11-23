#!/usr/bin/env python
"""逐制式实机矩阵：每一种条码都打印、拍照、解码，给出能/不能的结论。

为什么按"页"而不是"条"：一次打一条，纸带很快涨到一米，摄像头就看不到最新那张了，
测到第 22 项开始全部落空（第一版就这么翻车的）。现在一页打 2-3 种，页页拍照，
所有识别结果累积到一个集合里，最后按**唯一载荷**回填每一项的结论——不受出纸滞后影响。

载荷必须每条唯一，否则照片里同框的上一张会冒充这一张（第一版用 1234567890，
MSI 被判成 Codabar 读过）。

    python tools/android_barcode_matrix.py --host 192.168.28.90 --serial <sn>
    python tools/android_barcode_matrix.py --only qrcode,pdf417 --no-photo
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zpl_core import builder, transport  # noqa: E402

ADB = "C:/Users/shenyf/AppData/Local/Android/Sdk/platform-tools/adb.exe"
DPI = 200
OUT = ROOT / "scratch" / "barcode_matrix.json"


def _num(idx: int, n: int) -> str:
    """定长数字载荷，前两位是序号，保证跨条不重复。"""
    return (f"{idx:02d}" + "1234567890" * 3)[:n]


# 制式 -> (唯一载荷, 额外参数, 能识别它的 zxing 格式)
CASES: dict[str, tuple[str, dict, set]] = {
    "code128":    ("ZPL-CORE-128-01", {}, {"Code 128"}),
    "code39":     ("CODE39-TEST-02", {}, {"Code 39"}),
    "code93":     ("CODE93-TEST-03", {}, {"Code 93"}),
    "code11":     (_num(4, 10), {}, {"Code 11"}),
    "i2of5":      (_num(5, 12), {}, {"ITF", "Code 128"}),
    "industrial2of5": (_num(6, 12), {}, {"ITF", "Code 128"}),
    "std2of5":    (_num(7, 12), {}, {"ITF", "Code 128"}),
    "codabar":    (_num(8, 10), {}, {"Codabar"}),
    "msi":        (_num(9, 10), {}, {"MSI"}),
    "plessey":    (_num(10, 10), {}, {"Plessey", "MSI"}),
    "ean13":      (_num(11, 12), {}, {"EAN-13"}),
    "ean8":       (_num(12, 7), {}, {"EAN-8"}),
    "upca":       (_num(13, 11), {}, {"UPC-A", "EAN-13"}),
    "upce":       (_num(14, 10), {}, {"UPC-E", "UPC-A"}),
    "upcext":     (_num(15, 5), {}, {"UPC-EAN extension"}),
    "gs1databar": (_num(16, 13), {}, {"DataBar Omni", "DataBar"}),
    "postnet":    (_num(17, 5), {}, {"POSTNET"}),
    "planet":     (_num(18, 11), {}, {"PLANET", "POSTNET"}),
    "codablock":  ("CODABLOCK-19", {}, {"CODABLOCK"}),
    "code49":     ("CODE49-20", {}, {"Code 49"}),
    "logmars":    ("LOGMARS-21", {}, {"Code 39"}),
    "qrcode":     ("QR-MATRIX-22", {"scale": 6}, {"QR Code"}),
    "datamatrix": ("DM-MATRIX-23", {"quality": 200, "module_size_dots": 4}, {"Data Matrix"}),
    "pdf417":     ("PDF417-MATRIX-24", {"module_width": 2, "row_height_dots": 12,
                                        "security_level": 4}, {"PDF417"}),
    "aztec":      ("AZTEC-MATRIX-25", {"scale": 4}, {"Aztec"}),
    "micropdf417": ("MICRO-PDF417-26", {"module_width": 2}, {"MicroPDF417"}),
    "upsmaxicode": (_num(27, 12), {}, {"MaxiCode"}),
    # ^BT p.141: 6 digits + comma + serial, otherwise only the Code 39 half prints
    "tlc39":      ("123456,TLC39-28", {}, {"TLC39"}),
    "usps":       (_num(29, 20), {}, {"Intelligent Mail"}),
}

LINEAR_ORDER = ["code128", "code39", "code93", "code11", "i2of5", "industrial2of5",
                "std2of5", "codabar", "msi", "plessey", "ean13", "ean8", "upca",
                "upce", "upcext", "gs1databar", "postnet", "planet", "codablock",
                "code49", "logmars"]
STACKED_ORDER = ["qrcode", "datamatrix", "pdf417", "aztec", "micropdf417",
                 "upsmaxicode", "tlc39", "usps"]


def adb(*args: str, serial: str, check: bool = False) -> str:
    r = subprocess.run([ADB, f"-s{serial}"] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def page_zpl(syms: list[str], page_no: int) -> tuple[str, dict[str, list]]:
    """一页放 1-3 个制式，每个带自己的标题和原文。"""
    slots = {1: 42, 2: 24, 3: 15}[len(syms)]
    fields = [{"type": "text", "data": f"page {page_no:02d}", "x_mm": 2, "y_mm": 1,
               "size_mm": 2.2}]
    issues: dict[str, list] = {}
    y = 5.0
    for sym in syms:
        data, extra, _ = CASES[sym]
        # 堆叠码的 h 是"每行高度"（^B7 p.79 / ^BF p.111），传总高会让符号长过整页
        if sym == "pdf417":
            geom = {"row_height_dots": 12, "module_width": 2}
        elif sym == "micropdf417":
            geom = {"row_height_dots": 8, "module_width": 2}
        elif len(syms) == 1 and sym in STACKED_ORDER:
            geom = {"height_mm": 16}
        else:
            geom = {"height_mm": 7}
        fields.append({"type": "text", "data": f"{sym}  {data[:22]}", "x_mm": 2,
                       "y_mm": y, "size_mm": 2.0})
        fields.append({"type": "barcode", "symbology": sym, "data": data, "x_mm": 3,
                       "y_mm": y + 4.5, **geom, **(extra or {})})
        y += slots
    height = max(35, y + 4)
    zpl, iss = builder.build_label({"dpi": DPI, "width_mm": 60, "height_mm": height,
                                    "fields": fields})
    for i in iss:
        issues.setdefault(i.get("field", "?"), []).append(i)
    return zpl, issues


def photograph(serial: str, wait: float = 1.5) -> Path | None:
    adb("shell", "am start -a android.media.action.STILL_IMAGE_CAMERA", serial=serial)
    time.sleep(wait)
    size = adb("shell", "wm size", serial=serial).strip()
    try:
        w, h = (int(x) for x in size.split(":")[-1].split("x"))
    except ValueError:
        w, h = 1080, 2160
    adb("shell", f"input tap {w // 2} {int(h * 0.838)}", serial=serial)
    time.sleep(1.5)
    newest = adb("shell", "ls -t /sdcard/DCIM/Camera | head -1", serial=serial).strip()
    if not newest:
        return None
    local = ROOT / "scratch" / f"matrix_{newest}"
    adb("pull", f"/sdcard/DCIM/Camera/{newest}", str(local).replace("\\", "/"), serial=serial)
    return local if local.exists() else None


def decode(path: Path) -> list[dict]:
    """多尺度解码。块要开得比一维码宽，否则会把码切断（吃过这个亏）。"""
    import zxingcpp
    from PIL import Image

    img = Image.open(path)
    W, H = img.size
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def take(im):
        try:
            rs = zxingcpp.read_barcodes(im, try_rotate=True, try_downscale=True,
                                        try_invert=True)
        except TypeError:
            rs = zxingcpp.read_barcodes(im)
        for r in rs:
            if not r.text:
                continue
            key = (str(r.format).replace("BarcodeFormat.", ""), r.text)
            if key in seen:
                continue
            seen.add(key)
            hits.append({"format": key[0], "text": r.text})

    take(img)
    for s in (2, 3):
        take(img.resize((W // s, H // s), Image.LANCZOS))
    for y0 in range(0, H, 1100):
        for x0 in range(0, W, 1100):
            take(img.crop((x0, y0, min(x0 + 1800, W), min(y0 + 1800, H))))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.28.90")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--only", default="", help="只测这些制式（逗号分隔）")
    ap.add_argument("--no-photo", action="store_true", help="只打印，不拍照解码")
    ap.add_argument("--shots", type=int, default=3, help="每页拍几张")
    ap.add_argument("--delay", type=float, default=2.0, help="出纸后等多久开始拍")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    linear = [s for s in LINEAR_ORDER if not only or s in only]
    stacked = [s for s in STACKED_ORDER if not only or s in only]

    pages: list[list[str]] = [linear[i:i + 3] for i in range(0, len(linear), 3)]
    pages += [stacked[i:i + 2] for i in range(0, len(stacked), 2)]

    print(f"共 {len(pages)} 页：一维 {len(linear)} 种（每页 3 个），二维 {len(stacked)} 种（每页 2 个）")
    all_hits: list[dict] = []
    page_log: list[dict] = []

    for n, syms in enumerate(pages, 1):
        zpl, issues = page_zpl(syms, n)
        errs = [f"{i['code']}: {i['message'][:70]}" for i in issues.get("?", [])]
        print(f"\n[page {n:02d}] {' '.join(syms)}  {len(zpl.encode())}B", flush=True)
        if errs:
            print("   构建错误:", errs)
        res = transport.send_tcp(args.host, zpl, timeout=5)
        if not res.get("ok"):
            print("   发送失败:", res.get("error"))
            page_log.append({"page": n, "syms": syms, "send_error": res.get("error")})
            continue
        if args.no_photo:
            page_log.append({"page": n, "syms": syms, "printed": True})
            continue
        time.sleep(args.delay)
        hits: list[dict] = []
        for _ in range(args.shots):
            p = photograph(args.serial)
            if p is not None:
                for h in decode(p):
                    if h not in hits:
                        hits.append(h)
        all_hits.extend(h for h in hits if h not in all_hits)
        print(f"   本次解出: {[(h['format'], h['text'][:26]) for h in hits]}", flush=True)
        page_log.append({"page": n, "syms": syms, "hits": len(hits)})

    # ---- 汇总：按唯一载荷回填每一制式 ----
    import re
    norm = lambda s: re.sub(r"[^A-Za-z0-9]", "", s).upper()
    print("\n" + "=" * 78)
    print(f"{'制式':16s} {'载荷':22s} 结论")
    print("-" * 78)
    rows = []
    for sym in linear + stacked:
        data, extra, formats = CASES[sym]
        want = norm(data)

        def matches(h):
            if h["format"] not in formats:
                return False
            g = norm(h["text"])
            if want in g or g in want:
                return True
            # UPC-E 是压缩形式、UPC/EAN 扩展是附加码：条码内容与输入本就不同
            return sym in ("upce", "upcext")

        got = [h for h in all_hits if matches(h)]
        other = [h for h in all_hits if norm(h["text"]).startswith(want) and h not in got]
        if args.no_photo:
            verdict = "printed-only"
        elif got:
            verdict = "READ"
        elif other:
            verdict = f"READ-AS-{other[0]['format']}"
        else:
            verdict = "NOT-READ"
        rows.append({"sym": sym, "data": data, "verdict": verdict,
                     "hits": [f"{h['format']}={h['text']}" for h in got or other][:3]})
        print(f"{sym:16s} {data[:22]:22s} {verdict}")
    OUT.write_text(json.dumps({"rows": rows, "pages": page_log, "hits": all_hits},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n明细: {OUT}")
    read = sum(1 for r in rows if r["verdict"] == "READ")
    print(f"解码读回 {read}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())