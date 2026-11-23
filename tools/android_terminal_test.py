#!/usr/bin/env python
"""终端直打测试：让 Android 终端自己把 zpl-core 生成的三类标签打出来并回读验证。

为什么不是 PC 直连打印：这一版 zpl-core 的三件事（^GF 图片 / ^DF 模板 / ~HS 闭环）
真正的落地场景是「端侧终端自己发字节」。所以这个脚本把 PC 当构建器 + 裁判，
把 Android 终端当发送方，验证的是：

    终端 --(nc, TCP 9100)--> 条码打印机 --(^HV / ~HS 回包)--> 终端 --> 裁判

用法：
    python tools/android_terminal_test.py --printer 192.168.28.90
    python tools/android_terminal_test.py --printer 192.168.28.90 --dry-run   # 只构建，不打
    python tools/android_terminal_test.py --serial 26141525100772 --no-image   # 跳过 ^GF 一页

注意：**会真的出纸**（两条标签）。连续纸（continuous）下每条标签靠 ^LL 定长。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zpl_core import builder, transport  # noqa: E402

ADB = "C:/Users/shenyf/AppData/Local/Android/Sdk/platform-tools/adb.exe"
DEVICE_DIR = "/data/local/tmp/zpltest"
LABEL_CODE = "ZCTEST-0001"
DPI = 200                      # ZR668-200dpi（~HI 里会再核对一次）
LOGO_W, LOGO_H = 96, 32


def adb(*args: str, serial: str | None = None, check: bool = True) -> str:
    cmd = [ADB] + ([f"-s{serial}"] if serial else []) + list(args)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {res.stderr.strip()}")
    return (res.stdout or "") + (res.stderr or "")


def make_logo() -> list[str]:
    """96x32 的边框 + 对角线，肉眼一看就知道是这张图，纯 stdlib 生成。"""
    rows = []
    for y in range(LOGO_H):
        row = ["0"] * LOGO_W
        for x in range(LOGO_W):
            edge = y in (0, 1, LOGO_H - 2, LOGO_H - 1) or x in (0, 1, LOGO_W - 2, LOGO_W - 1)
            diag = abs((x * LOGO_H // LOGO_W) - y) <= 1
            if edge or diag:
                row[x] = "1"
        rows.append("".join(row))
    return rows


def build_payloads(no_image: bool = False) -> dict[str, str]:
    """生成要发给打印机的字节。每个文件对应一件被测能力。"""
    files: dict[str, str] = {}

    # --- 1) ^GF 图片 + 文本 + 带 ^HV 的条码：一条标签验两件事 ---
    fields = []
    if not no_image:
        fields.append({"type": "image", "bitmap": make_logo(), "x_mm": 3, "y_mm": 3})
        fields.append({"type": "text", "data": "ZPL-CORE 0.3.0", "x_mm": 18, "y_mm": 5,
                       "size_mm": 3.5})
    else:
        fields.append({"type": "text", "data": "ZPL-CORE 0.3.0", "x_mm": 3, "y_mm": 5,
                       "size_mm": 4})
    fields += [
        {"type": "text", "data": f"GFA direct  {LABEL_CODE}", "x_mm": 3, "y_mm": 13,
         "size_mm": 2.6},
        {"type": "barcode", "symbology": "code128", "data": LABEL_CODE,
         "x_mm": 3, "y_mm": 18, "height_mm": 7,
         "hv": {"bytes": 24, "header": "L1[", "terminator": "]"}},
    ]
    l1, i1 = builder.build_label({"dpi": DPI, "width_mm": 60, "height_mm": 30,
                                  "fields": fields})
    files["l1_image.zpl"] = l1
    files["_l1_issues.txt"] = "\n".join(f'{i["severity"]}: {i["code"]} {i["message"]}'
                                        for i in i1) or "none"

    # --- 2) ^DF 存模板（装机一次，不出纸）---
    tpl_spec = {"dpi": DPI, "width_mm": 60, "height_mm": 30, "fields": [
        {"type": "text", "data": "ZPL-CORE TEMPLATE", "x_mm": 3, "y_mm": 3, "size_mm": 3},
        {"type": "text", "var": "name", "x_mm": 3, "y_mm": 10, "size_mm": 3.5},
        {"type": "barcode", "symbology": "code128", "var": "code", "x_mm": 3, "y_mm": 17,
         "height_mm": 8, "hv": {"bytes": 24, "header": "L2[", "terminator": "]"}},
    ]}
    tpl, tpl_fields, ti = builder.build_template(tpl_spec, name="ZCTEST")
    files["l2_template.zpl"] = tpl
    files["_l2_fields.txt"] = repr(tpl_fields)
    files["_l2_issues.txt"] = "\n".join(f'{i["severity"]}: {i["code"]} {i["message"]}'
                                        for i in ti) or "none"

    # --- 3) ^XF 回填（只发几百字节）---
    recall, ri = builder.fill_template("ZCTEST", {"name": "TERMINAL 192.168.28.176",
                                                 "code": LABEL_CODE}, fields=tpl_fields)
    files["l3_recall.zpl"] = recall
    files["_l3_issues.txt"] = "\n".join(f'{i["severity"]}: {i["code"]} {i["message"]}'
                                        for i in ri) or "none"
    return files


def device_runner() -> str:
    """手机上跑的 sh 脚本。两个坑都写在这儿：

    1. mksh 不接受 `f() {   # 注释`（注释跟在 `{` 后面报 unmatched '{'）；
    2. nc 之后必须 sleep：stdin 一关 socket 就半关，打印机回包收不到。
    """
    return f"""#!/system/bin/sh
P=${{1:-192.168.28.90}}
D={DEVICE_DIR}
send()
{{
  (cat "$D/$1"; sleep 1) | nc -w 3 "$P" 9100 > "$D/$2" 2>&1
}}
ask()
{{
  (printf '~HS'; sleep 1) | nc -w 2 "$P" 9100 > "$D/$1" 2>&1
}}
odo()
{{
  (printf '! U1 getvar "odometer.total_label_count"\r\n'; sleep 1) | nc -w 2 "$P" 9100 > "$D/$1" 2>&1
}}
odo 00_odo.txt
ask 00_status.txt
send l1_image.zpl    01_l1.out
ask  02_status.txt
send l2_template.zpl 03_l2.out
send l3_recall.zpl   04_l3.out
ask  05_status.txt
odo  06_odo.txt
echo done > "$D/99_done.txt"
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--printer", default="192.168.28.90")
    ap.add_argument("--serial", default=None, help="adb 序列号（多设备时需要）")
    ap.add_argument("--dry-run", action="store_true", help="只构建并自检，不碰设备")
    ap.add_argument("--no-image", action="store_true", help="跳过 ^GF 图片字段")
    ap.add_argument("--expect-labels", type=int, default=2,
                    help="期望实际出纸张数（默认 2：L1 图片页 + L3 回填页）")
    args = ap.parse_args()

    print(f"== 构建标签（{DPI} dpi）==")
    files = build_payloads(no_image=args.no_image)
    for name, body in files.items():
        if name.startswith("_"):
            continue
        issues = builder.validate_zpl(body)
        print(f"  {name:18s} {len(body.encode()):5d} B  validate={'OK' if not issues else issues}")
    for name in ("_l1_issues.txt", "_l2_issues.txt", "_l3_issues.txt"):
        print(f"  {name[1:]:18s} {files[name]}")
    print(f"  template vars: {files['_l2_fields.txt']}")

    if args.dry_run:
        print("\n--dry-run：不出纸、不碰设备--")
        for name in ("l1_image.zpl", "l2_template.zpl", "l3_recall.zpl"):
            print(f"\n[{name}]\n{files[name]}")
        return 0

    print("\n== 检查终端 ==")
    devs = adb("devices")
    if args.serial is None:
        cands = [ln.split()[0] for ln in devs.splitlines()[1:] if "device" in ln and
                 not ln.startswith("List")]
        if not cands:
            print("没有已连接的设备"); return 2
        args.serial = cands[0]
    print(f"  设备: {args.serial}")
    print("  " + adb("shell", "ip -4 addr show wlan0 | grep inet", serial=args.serial).strip())

    print("\n== 推送 ==")
    adb("shell", f"mkdir -p {DEVICE_DIR}", serial=args.serial)
    script = ROOT / "scratch" / "run.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" 是硬要求：Windows 默认写成 CRLF，mksh 会把 \r 当命令的一部分
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(device_runner())
    adb("push", str(script).replace("\\", "/"), f"{DEVICE_DIR}/run.sh", serial=args.serial)
    out = ""
    for name in files:
        p = ROOT / "scratch" / name
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(files[name])
        out += adb("push", str(p).replace("\\", "/"), f"{DEVICE_DIR}/{name}",
                   serial=args.serial)
    print("  ok")

    print("\n== 终端执行（会出纸：约 2 条标签）==")
    res = adb("shell", f"sh {DEVICE_DIR}/run.sh {args.printer}", serial=args.serial,
              check=False)
    if "not found" in res or "Permission denied" in res:
        print(res); return 3
    print("  " + res.strip().replace("\n", "\n  "))

    print("\n== 取回结果 ==")
    local = ROOT / "scratch" / "device"
    local.mkdir(parents=True, exist_ok=True)
    for name in ("00_odo.txt", "00_status.txt", "01_l1.out", "02_status.txt", "03_l2.out",
                 "04_l3.out", "05_status.txt", "06_odo.txt", "99_done.txt"):
        adb("pull", f"{DEVICE_DIR}/{name}", str(local / name).replace("\\", "/"),
            serial=args.serial, check=False)

    def read(name: str) -> bytes:
        p = local / name
        return p.read_bytes() if p.exists() else b""

    def hv(text: bytes, tag: str) -> str | None:
        m = re.search(rf"{tag}\[(.*?)\]", text.decode("latin-1", "replace"), re.S)
        return m.group(1) if m else None

    fails: list[str] = []
    print()
    st0 = transport.parse_host_status(read("00_status.txt"))
    print(f"  打印前 ~HS: ready={st0.get('ready')} mode={st0.get('print_mode')} "
          f"ll={st0.get('label_length_dots')} 错误={[e['name'] for e in st0.get('errors', [])]}")
    if not st0.get("ok"):
        fails.append("打印机没有回应 ~HS（检查 IP / 是否被别人占用 / 面板报警）")
    if st0.get("ok") and not st0.get("ready"):
        fails.append(f"打印前打印机不就绪：{[e['name'] for e in st0.get('errors', [])]}")

    l1 = hv(read("01_l1.out"), "L1")
    print(f"  L1 ^GF+^HV 回读: {l1!r}  （期望 {LABEL_CODE!r}）")
    if l1 != LABEL_CODE:
        fails.append(f"L1 ^HV 回读不符：{l1!r} != {LABEL_CODE!r}")

    st2 = transport.parse_host_status(read("02_status.txt"))
    print(f"  L1 后 ~HS: idle={st2.get('idle')} 队列={st2.get('formats_in_buffer')} "
          f"剩余={st2.get('labels_remaining')}")

    l2 = hv(read("03_l2.out"), "L2")
    print(f"  L2 ^DF 安装回包: {read('03_l2.out')[:60]!r}（模板只存不印，不该有 L2[] 值）")
    if l2:
        fails.append(f"^DF 安装时居然打印了：{l2!r}")

    l3 = hv(read("04_l3.out"), "L2")
    print(f"  L3 ^XF+^HV 回读: {l3!r}  （期望 {LABEL_CODE!r}）")
    if l3 != LABEL_CODE:
        fails.append(f"L3 ^HV 回读不符：{l3!r} != {LABEL_CODE!r}")

    st5 = transport.parse_host_status(read("05_status.txt"))
    print(f"  打印后 ~HS: ready={st5.get('ready')} idle={st5.get('idle')} "
          f"队列={st5.get('formats_in_buffer')} 剩余={st5.get('labels_remaining')} "
          f"错误={[e['name'] for e in st5.get('errors', [])]}")
    if st5.get("ok") and not st5.get("idle"):
        fails.append("打印后队列未清空（打印机可能卡纸/暂停）")
    if st5.get("errors"):
        fails.append(f"打印后打印机报错：{[e['name'] for e in st5['errors']]}")

    def odo(name: str) -> int | None:
        m = re.search(rb"(\d+)", read(name))
        return int(m.group(1)) if m else None

    o0, o1 = odo("00_odo.txt"), odo("06_odo.txt")
    if o0 is None or o1 is None:
        print(f"  里程计: 读不到（{o0}/{o1}）——跳过出纸张数核对")
    else:
        delta = o1 - o0
        print(f"  里程计: {o0} -> {o1}，实际出纸 {delta} 张（期望 {args.expect_labels}）")
        if delta != args.expect_labels:
            fails.append(f"出纸张数不符：{delta} != {args.expect_labels}"
                         f"（纸没走 / ^LL 与连续纸不匹配 / 打印被暂停）")

    print()
    if fails:
        print(f"FAILED ({len(fails)})")
        for f in fails:
            print("   -", f)
        return 1
    print("TERMINAL PRINT TEST PASSED —— 终端自己发字节、打印机回读一致")
    print(f"   模板 {len(files['l2_template.zpl'].encode())} B 装一次，"
          f"回填一次 {len(files['l3_recall.zpl'].encode())} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())