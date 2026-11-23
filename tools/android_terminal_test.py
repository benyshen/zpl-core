#!/usr/bin/env python
"""终端直打测试：让 Android 终端自己把 zpl-core 生成的标签打出来并回读验证。

为什么不是 PC 直连打印：zpl-core 三件事（^GF 图片 / ^DF 模板 / ~HS 闭环）真正的
落地场景是「端侧终端自己发字节」。所以 PC 只当构建器 + 裁判，Android 终端当发送方：

    终端 --(nc, TCP 9100)--> 条码打印机 --(^HV / ~HS 回包)--> 终端 --> 裁判

三种模式：
    --mode features  ^GF 图片页 / ^DF 装模板(不出纸) / ^XF 回填页
    --mode samples   QR 页 + PDF417 页（不同码制，各带 ^HV 回读）
    --mode both      先 features 再 samples

用法：
    python tools/android_terminal_test.py --printer 192.168.28.90 --mode samples
    python tools/android_terminal_test.py --mode both --dry-run      # 只构建，不打

注意：**会真的出纸**（每套 2 张）。连续纸靠 ^LL 定长。
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
DPI = 200                      # ZR668-200dpi（~HI 里会再核对一次）
LABEL_CODE = "ZCTEST-0001"
LOGO_W, LOGO_H = 96, 32

QR_PAYLOAD = "https://github.com/benyshen/zpl-core"
PDF_PAYLOAD = "ZPL-CORE|0.3.0|ZR668|TC201L|2026-11-23|PDF417"


# --------------------------------------------------------------------------- adb
def adb(*args: str, serial: str | None = None, check: bool = True) -> str:
    cmd = [ADB] + ([f"-s{serial}"] if serial else []) + list(args)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {res.stderr.strip()}")
    return (res.stdout or "") + (res.stderr or "")


# ----------------------------------------------------------------------- payloads
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


def build_feature_payloads(no_image: bool = False) -> tuple[dict[str, str], list]:
    """^GF / ^DF+^XF / ^HV —— 三件能力各一条。"""
    files: dict[str, str] = {}
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
    l1, i1 = builder.build_label({"dpi": DPI, "width_mm": 60, "height_mm": 30, "fields": fields})
    files["l1_image.zpl"] = l1

    tpl_spec = {"dpi": DPI, "width_mm": 60, "height_mm": 30, "fields": [
        {"type": "text", "data": "ZPL-CORE TEMPLATE", "x_mm": 3, "y_mm": 3, "size_mm": 3},
        {"type": "text", "var": "name", "x_mm": 3, "y_mm": 10, "size_mm": 3.5},
        {"type": "barcode", "symbology": "code128", "var": "code", "x_mm": 3, "y_mm": 17,
         "height_mm": 8, "hv": {"bytes": 24, "header": "L2[", "terminator": "]"}},
    ]}
    tpl, tpl_fields, ti = builder.build_template(tpl_spec, name="ZCTEST")
    files["l2_template.zpl"] = tpl
    recall, ri = builder.fill_template("ZCTEST", {"name": "TERMINAL 192.168.28.176",
                                                 "code": LABEL_CODE}, fields=tpl_fields)
    files["l3_recall.zpl"] = recall
    issues = [("l1", i) for i in i1] + [("l2", i) for i in ti] + [("l3", i) for i in ri]
    return files, issues


def build_sample_payloads() -> tuple[dict[str, str], list]:
    """QR 与 PDF417 各一条：不同码制、不同数据形态，都带 ^HV 回读。"""
    files: dict[str, str] = {}

    # --- QR：放一个真 URL，手机一扫就能验证 ---
    qr, qi = builder.build_label({"dpi": DPI, "width_mm": 60, "height_mm": 40, "fields": [
        {"type": "text", "data": "QR CODE  ^BQ", "x_mm": 3, "y_mm": 2, "size_mm": 3},
        {"type": "barcode", "symbology": "qrcode", "data": QR_PAYLOAD,
         "x_mm": 3, "y_mm": 8, "scale": 6,
         "hv": {"bytes": 64, "header": "Q[", "terminator": "]"}},
        {"type": "text", "data": "github.com/benyshen/zpl-core", "x_mm": 3, "y_mm": 31,
         "size_mm": 2.4},
    ]})
    files["l4_qr.zpl"] = qr

    # --- PDF417：一条标签放两版，扫不动时能直接对比是参数问题还是纸/碳带问题 ---
    # 手册 p.79：h 是"一行"的高度，不是整条码高度；模块宽度来自 ^BY（不发就继承打印机状态）。
    #   A: ^BY2，6 列 x 6 行，行高 12 点 -> 274 x 72 dots（34.8 x 9.1 mm）
    #   B: ^BY3，6 列 x 6 行，行高 15 点 -> 411 x 90 dots（52.2 x 11.4 mm）
    pdf, pi = builder.build_label({"dpi": DPI, "width_mm": 60, "height_mm": 50, "fields": [
        {"type": "text", "data": "PDF417  A:^BY2  B:^BY3", "x_mm": 3, "y_mm": 1.5,
         "size_mm": 2.6},
        {"type": "barcode", "symbology": "pdf417", "data": PDF_PAYLOAD, "x_mm": 3, "y_mm": 6,
         "module_width": 2, "columns": 6, "rows": 6, "row_height_dots": 12,
         "security_level": 2, "hv": {"bytes": 96, "header": "P[", "terminator": "]"}},
        {"type": "text", "data": "A  module 2  6x6  row 12", "x_mm": 3, "y_mm": 15.6,
         "size_mm": 2.4},
        {"type": "barcode", "symbology": "pdf417", "data": PDF_PAYLOAD, "x_mm": 3, "y_mm": 22,
         "module_width": 3, "columns": 6, "rows": 6, "row_height_dots": 15,
         "security_level": 2},
        {"type": "text", "data": "B  module 3  6x6  row 15", "x_mm": 3, "y_mm": 34.2,
         "size_mm": 2.4},
    ]})
    files["l5_pdf417.zpl"] = pdf
    return files, [("l4", i) for i in qi] + [("l5", i) for i in pi]


# ------------------------------------------------------------------ device script
def device_runner(plan: list[tuple[str, str, str]]) -> str:
    """按 plan 生成 sh 脚本。三个坑都在这里，别改坏：

    1. mksh 不接受 `f() {   # 注释`（注释跟在 `{` 后报 unmatched '{'）；
    2. 必须是 LF：Windows 的 CRLF 会让 mksh 把 \\r 当命令的一部分；
    3. nc 之后必须 sleep：stdin 一关 socket 就半关，打印机回包收不到。
    """
    lines = []
    for kind, src, out in plan:
        if kind == "send":
            lines.append(f"send {src} {out}")
        elif kind == "ask":
            lines.append(f"ask {out}")
        elif kind == "odo":
            lines.append(f"odo {out}")
    body = "\n".join(lines)
    return f"""#!/system/bin/sh
P=${{1:-192.168.28.90}}
D={DEVICE_DIR}
send()
{{
  (cat "$D/$1"; sleep 1) | nc -w 3 "$P" 9100 > "$D/$2" 2>&1
}}
ask()
{{
  i=0
  while [ $i -lt 3 ]; do
    (printf '~HS'; sleep 1) | nc -w 2 "$P" 9100 > "$D/$1" 2>&1
    [ -s "$D/$1" ] && return 0
    i=$((i+1)); sleep 1
  done
}}
odo()
{{
  i=0
  while [ $i -lt 3 ]; do
    (printf '! U1 getvar "odometer.total_label_count"\\r\\n'; sleep 1) | nc -w 2 "$P" 9100 > "$D/$1" 2>&1
    [ -s "$D/$1" ] && return 0
    i=$((i+1)); sleep 1
  done
}}
{body}
echo done > "$D/99_done.txt"
"""


# ------------------------------------------------------------------ push / pull
def write_lf(path: Path, text: str) -> None:
    """newline="\\n" 是硬要求：Windows 默认 CRLF，mksh 会把 \\r 当命令的一部分。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def push_and_run(files: dict[str, str], plan, printer: str, serial: str) -> Path:
    adb("shell", f"mkdir -p {DEVICE_DIR}", serial=serial)
    script = ROOT / "scratch" / "run.sh"
    write_lf(script, device_runner(plan))
    adb("push", str(script).replace("\\", "/"), f"{DEVICE_DIR}/run.sh", serial=serial)
    for name, body in files.items():
        p = ROOT / "scratch" / name
        write_lf(p, body)
        adb("push", str(p).replace("\\", "/"), f"{DEVICE_DIR}/{name}", serial=serial)
    print("  推送完成，终端开始发送…")
    res = adb("shell", f"sh {DEVICE_DIR}/run.sh {printer}", serial=serial, check=False)
    if res.strip():
        print("  " + res.strip().replace("\n", "\n  "))

    local = ROOT / "scratch" / "device"
    local.mkdir(parents=True, exist_ok=True)
    for _, _, out in plan:
        adb("pull", f"{DEVICE_DIR}/{out}", str(local / out).replace("\\", "/"),
            serial=serial, check=False)
    adb("pull", f"{DEVICE_DIR}/99_done.txt", str(local / "99_done.txt").replace("\\", "/"),
        serial=serial, check=False)
    return local


def reader(local: Path):
    def read(name: str) -> bytes:
        p = local / name
        return p.read_bytes() if p.exists() else b""
    return read


def hv_of(raw: bytes, tag: str) -> str | None:
    m = re.search(rf"{re.escape(tag)}\[(.*?)\]", raw.decode("latin-1", "replace"), re.S)
    return m.group(1) if m else None


def odo_of(raw: bytes) -> int | None:
    m = re.search(rb"(\d+)", raw)
    return int(m.group(1)) if m else None


def common_checks(read, f0: str, f1: str, expect_labels: int, fails: list) -> None:
    st0 = transport.parse_host_status(read(f0))
    print(f"  打印前 ~HS: ready={st0.get('ready')} mode={st0.get('print_mode')} "
          f"ll={st0.get('label_length_dots')} 错误={[e['name'] for e in st0.get('errors', [])]}")
    if not st0.get("ok"):
        fails.append("打印机没有回应 ~HS（检查 IP / 是否被占用 / 面板报警）")
    elif not st0.get("ready"):
        fails.append(f"打印前不就绪：{[e['name'] for e in st0.get('errors', [])]}")

    st1 = transport.parse_host_status(read(f1))
    print(f"  打印后 ~HS: ready={st1.get('ready')} idle={st1.get('idle')} "
          f"队列={st1.get('formats_in_buffer')} 剩余={st1.get('labels_remaining')} "
          f"错误={[e['name'] for e in st1.get('errors', [])]}")
    if st1.get("ok") and not st1.get("idle"):
        fails.append("打印后队列没清空（卡纸 / 暂停 / 数据没发完）")
    if st1.get("errors"):
        fails.append(f"打印后打印机报错：{[e['name'] for e in st1['errors']]}")

    o0, o1 = odo_of(read("00_odo.txt")), odo_of(read("06_odo.txt"))
    if o0 is None or o1 is None:
        print(f"  里程计: 读不到（{o0}/{o1}）——跳过出纸张数核对")
    else:
        delta = o1 - o0
        print(f"  里程计: {o0} -> {o1}，实际出纸 {delta} 张（期望 {expect_labels}）")
        if delta != expect_labels:
            fails.append(f"出纸张数不符：{delta} != {expect_labels}"
                         f"（纸没走 / ^LL 与连续纸不匹配 / 打印被暂停）")


# ------------------------------------------------------------------------- modes
def run_features(files, args) -> list:
    plan = [("ask", "", "00_status.txt"), ("odo", "", "00_odo.txt"),
            ("send", "l1_image.zpl", "01_l1.out"),
            ("ask", "", "02_status.txt"),
            ("send", "l2_template.zpl", "03_l2.out"),
            ("send", "l3_recall.zpl", "04_l3.out"),
            ("ask", "", "05_status.txt"), ("odo", "", "06_odo.txt")]
    local = push_and_run(files, plan, args.printer, args.serial)
    read = reader(local)
    fails: list[str] = []
    common_checks(read, "00_status.txt", "05_status.txt", 2, fails)

    l1 = hv_of(read("01_l1.out"), "L1")
    print(f"  L1 ^GF+^HV 回读: {l1!r}（期望 {LABEL_CODE!r}）")
    if l1 != LABEL_CODE:
        fails.append(f"L1 ^HV 回读不符：{l1!r} != {LABEL_CODE!r}")

    l2 = hv_of(read("03_l2.out"), "L2")
    print(f"  L2 ^DF 安装回包: {read('03_l2.out')[:60]!r}（模板只存不印）")
    if l2:
        fails.append(f"^DF 安装时居然打印了：{l2!r}")

    l3 = hv_of(read("04_l3.out"), "L2")
    print(f"  L3 ^XF+^HV 回读: {l3!r}（期望 {LABEL_CODE!r}）")
    if l3 != LABEL_CODE:
        fails.append(f"L3 ^HV 回读不符：{l3!r} != {LABEL_CODE!r}")
    return fails


def run_status(files, args) -> list:
    """不出纸：只验证 终端→打印机 通路、~HS 解析、里程计可读。"""
    plan = [("ask", "", "00_status.txt"), ("odo", "", "00_odo.txt")]
    local = push_and_run({}, plan, args.printer, args.serial)
    read = reader(local)
    fails: list[str] = []
    st = transport.parse_host_status(read("00_status.txt"))
    print(f"  ~HS: ok={st.get('ok')} ready={st.get('ready')} idle={st.get('idle')} "
          f"mode={st.get('print_mode')} 媒体={st.get('media_type')} "
          f"ll={st.get('label_length_dots')} 队列={st.get('formats_in_buffer')} "
          f"错误={[e['name'] for e in st.get('errors', [])]}")
    if not st.get("ok"):
        fails.append("打印机没有回应 ~HS（IP 变了 / 被别的机器占用 / 面板报警）")
    o = odo_of(read("00_odo.txt"))
    print(f"  里程计: {o}")
    if o is None:
        fails.append("读不到 odometer.total_label_count（SGD 被禁用？）")
    return fails


def run_samples(files, args) -> list:
    plan = [("ask", "", "00_status.txt"), ("odo", "", "00_odo.txt"),
            ("send", "l4_qr.zpl", "01_qr.out"),
            ("send", "l5_pdf417.zpl", "02_pdf.out"),
            ("ask", "", "05_status.txt"), ("odo", "", "06_odo.txt")]
    local = push_and_run(files, plan, args.printer, args.serial)
    read = reader(local)
    fails: list[str] = []
    common_checks(read, "00_status.txt", "05_status.txt", 2, fails)

    q = hv_of(read("01_qr.out"), "Q")
    print(f"  QR ^HV 回读: {q!r}")
    if not q:
        fails.append("QR 没有 ^HV 回包（码没生成或被拒绝）")
    elif QR_PAYLOAD not in q:
        fails.append(f"QR 回读里没有原始数据：{q!r}")

    p = hv_of(read("02_pdf.out"), "P")
    print(f"  PDF417 ^HV 回读: {p!r}")
    if not p:
        fails.append("PDF417 没有 ^HV 回包")
    elif PDF_PAYLOAD not in p:
        fails.append(f"PDF417 回读里没有原始数据：{p!r}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--printer", default="192.168.28.90")
    ap.add_argument("--serial", default=None, help="adb 序列号（多设备时需要）")
    ap.add_argument("--mode", choices=("status", "features", "samples", "both"),
                    default="features")
    ap.add_argument("--dry-run", action="store_true", help="只构建并自检，不碰设备")
    ap.add_argument("--no-image", action="store_true", help="features 模式跳过 ^GF 图片字段")
    args = ap.parse_args()

    runs = []
    if args.mode == "status":
        runs.append(("status", {}, [], run_status))
    if args.mode in ("features", "both"):
        f, iss = build_feature_payloads(no_image=args.no_image)
        runs.append(("features", f, iss, run_features))
    if args.mode in ("samples", "both"):
        f, iss = build_sample_payloads()
        runs.append(("samples", f, iss, run_samples))

    print(f"== 构建（{DPI} dpi）==")
    bad = 0
    for name, files, issues, _ in runs:
        print(f"  [{name}]")
        for fn, body in files.items():
            v = builder.validate_zpl(body)
            print(f"    {fn:18s} {len(body.encode()):5d} B  validate={'OK' if v else v}")
        for tag, i in issues:
            if i["severity"] in ("error", "warning"):
                print(f"    ! {tag}: {i['severity']} {i['code']} {i['message'][:70]}")
                bad += i["severity"] == "error"
    if bad:
        print(f"\n构建有 {bad} 个 error，先修再打")
        return 2

    if args.dry_run:
        print("\n--dry-run：不出纸、不碰设备--")
        for name, files, _, _ in runs:
            for fn, body in files.items():
                print(f"\n[{fn}]\n{body}")
        return 0

    print("\n== 检查终端 ==")
    devs = adb("devices")
    if args.serial is None:
        cands = [ln.split()[0] for ln in devs.splitlines()[1:] if "device" in ln and
                 not ln.startswith("List")]
        if not cands:
            print("没有已连接的设备"); return 3
        args.serial = cands[0]
    print(f"  设备: {args.serial}")
    print("  " + adb("shell", "ip -4 addr show wlan0 | grep inet", serial=args.serial).strip())

    total_fails: list[str] = []
    for name, files, issues, runner in runs:
        paper = "不出纸" if name == "status" else "会出纸 2 张"
        print(f"\n== {name}（{paper}）==")
        fails = runner(files, args)
        total_fails.extend(fails)
        print(f"  -> {name}: {'PASS' if not fails else 'FAIL'}")

    print()
    if total_fails:
        print(f"FAILED ({len(total_fails)})")
        for f in total_fails:
            print("   -", f)
        return 1
    print("TERMINAL PRINT TEST PASSED —— 终端自己发字节，打印机回读一致，里程计对得上")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())