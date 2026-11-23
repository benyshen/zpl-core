# zpl-core

[![PyPI](https://img.shields.io/pypi/v/zpl-core.svg)](https://pypi.org/project/zpl-core/)
[![Python](https://img.shields.io/pypi/pyversions/zpl-core.svg)](https://pypi.org/project/zpl-core/)

ZPL II 标签引擎。一份代码，三个使用者：

- **[zebra-printer-mcp](https://github.com/benyshen/zebra-printer-mcp)** —— MCP 服务器外壳（9 个工具）
- **[zebra-printer-skill](https://github.com/benyshen/zebra-printer-skill)** —— CLI / skill 外壳（10 个子命令）
- 你自己的脚本

核心（build / validate / knowledge / transport / xlsx）**零第三方依赖**；渲染和 OCR 是可选 extras，不装不会污染环境。

所有默认值、取值范围和参数字母都对着 **ZPL II / ZBI 2 / SGD Programming Guide, P1134473-11EN Rev A（2026-07-05）** 核对过，页码即手册印刷页码，并由 `tests/test_manual.py` 逐条守着——详见 [docs/manual-conformance.md](docs/manual-conformance.md)。

## 安装

```bash
pip install zpl-core            # 生成、校验、发送——纯 stdlib（PyPI，>=3.10）
pip install zpl-core[render]    # + ZPL → PNG 离线预览（Pillow / segno / python-barcode）
pip install zpl-core[ocr]       # + 照片 → ZPL（OpenCV / onnxruntime / zxing-cpp + PP-OCRv4 权重）
pip install zpl-core[all]       # 全都要
```

`[ocr]` 会让包带上约 15 MB 的 PP-OCRv4 权重（Apache-2.0），所以它不在默认安装里。

## 五分钟

```python
from zpl_core import builder, transport

zpl, issues = builder.build_label({
    "dpi": 203, "width_mm": 60, "height_mm": 40,
    "fields": [
        {"type": "text", "x_mm": 3, "y_mm": 3, "height_dots": 30, "data": "五月花矿泉水"},
        {"type": "barcode", "symbology": "code128", "x_mm": 3, "y_mm": 12,
         "height_dots": 60, "data": "6934024512123"},
    ],
})
assert not issues, issues                  # 每条 issue 都带 severity / code / 手册页码
transport.send_tcp("192.168.1.50", zpl)    # 也支持 Windows RAW 队列 / USB 队列 / 写预览字节
```

## 模块

| 模块 | 做什么 | 额外依赖 |
|---|---|---|
| `builder` | 标签结构体 → ZPL II；mm→dots、29 种条码、`^A@` TrueType 中文、`^GB/^GC/^FO..z` 图形、`^FB` 域块、`^GF` 位图、`^DF`/`^XF`/`^FN` 模板、`^HV` 回读 | — |
| `builder.validate_zpl` | 拿手册命令表校验原始 ZPL，返回 `issues[]`（severity + code） | — |
| `knowledge` | 224 条手册命令（页码 + Format 参数）、71 条命令详解、28 种制式数据规则、27 条 SGD、13 个状态码 | — |
| `transport` | TCP 9100、Windows RAW 队列（winspool）、USB 队列、写 `.zpl` 预览字节；`~HS` 解析与打印闭环（就绪检查 → 发送 → 轮询到空闲）、`^HV` 回读 | — |
| `xlsx_batch` | 一行一条标签，纯 `zipfile`+`xml` 读 xlsx，整批一条 ZPL 流 | — |
| `raster` | PNG/JPEG 或位图 → `^GFA`（阈值 / Floyd–Steinberg 抖动 / 缩放）；位图输入纯 stdlib | 文件输入要 `[render]` |
| `render` | ZPL → PNG，离线版式预览；支持 `N/R/I/B` 旋转、`^FB` 溢出与「字段出界」告警 | `[render]` |
| `photo` | 标签照片 → ZPL（透视校正、字号推断、条码重建） | `[ocr]` |
| `ocr` | PP-OCRv4 检测/识别（onnxruntime）+ zxing-cpp 条码兜底 | `[ocr]` |
| `vision` | 视觉大模型后端：整张标签图交给 OpenAI 兼容 VLM 端点，返回结构化要素 | `[ocr]`（要 cv2） |

`transport` 只保证"字节发出去了"，**打印成功的证据在打印机那边**：`~HS` 状态串、SGD 查询属于外壳层（MCP 的 `printer_status`），核心只提供 `knowledge.STATUS_NOTES` 里的状态码含义表。

## 条码一览（29 种）

`code128` `code39` `code93` `code11` `code49` `i2of5` `industrial2of5` `std2of5` `codabar`
`msi` `plessey` `logmars` `codablock` `ean13` `ean8` `upca` `upce` `upcext` `gs1databar`
`pdf417` `micropdf417` `datamatrix` `qrcode` `aztec` `upsmaxicode` `planet` `postnet` `usps` `tlc39`

命令映射严格按手册 Table 34（p.1587-1588）。两个最容易记反的：**UPC-A 是 `^BU`、UPC-E 是 `^B9`**；`^B0` 不是 UPC-E，是 Aztec。

```python
{"type": "barcode", "symbology": "qrcode", "data": "https://x", "scale": 4}          # ^BQ...^FDQA,...
{"type": "barcode", "symbology": "qrcode", "input_mode": "M", "char_mode": "N"}      # 手动输入必须带字符模式
{"type": "barcode", "symbology": "datamatrix", "quality": 200, "data": "ABC"}        # ECC200
{"type": "barcode", "symbology": "upca", "data": "01234567890"}                      # 恰好 11 位，校验位打印机算
{"type": "barcode", "symbology": "code128", "mode": "D", "data": "(02)040..."}       # UCC/EAN 模式
```

## 端侧闭环：图片、模板、验真

### 1. 把图片印上去 —— `^GF`

```python
{"type": "image", "path": "logo.png", "x_mm": 3, "y_mm": 3, "width_dots": 240}   # 需要 [render]
{"type": "image", "bitmap": ["11110000", "00001111"], "x_mm": 3, "y_mm": 20}     # 自带位图，零依赖
```

`dither` 两种：`threshold`（logo/文字，边缘干净）与 `floyd`（照片，靠抖动保层次）。输出是
`^FO…^GFA,b,c,d,<hex>^FS`，每行按字节补齐、`b = c = 每行字节数 × 行数`（`^GF` p.215，上限 99999 字节）。
超过 20000 字节会警告并算出串口传输耗时——大图应该 `~DG` 下载一次、之后用 `^XGR` 调用。

### 2. 一次下载、反复打印 —— `^DF`/`^XF`/`^FN`

```python
zpl, fields, issues = builder.build_template(spec, name="SHIP")   # 变量字段写 "var": "sku"
transport.send_tcp(host, zpl)                                      # 只在装机时发一次

recall, _ = builder.fill_template("SHIP", {"sku": "A-1", "code": "693402451212"},
                                  fields=fields, quantity=4)
transport.send_tcp(host, recall)     # ^XA^XFR:SHIP.ZPL^FN1^FDA-1^FS…^XZ，几百字节
```

`fields` 是 `{^FN 编号: 变量名}`，`template_field_map(spec)` 可以单独取出（给表单/前端用）。
存储格式里变量字段只发 `^FN`、不发 `^FD`（手册 p.200），字面字段照常。名字要注意：`^DF` 接受 1-16 字符，
但 `^XF` 只能收回 1-8 字符（p.372），超了会给警告/错误。

### 3. 打完到底出来没有 —— `~HS` + `^HV`

```python
res = transport.send_and_verify(host, zpl, max_wait=20)
res["ok"], res["stage"]      # stage: preflight / send / print / printed
res["status"]["errors"]      # [{'name': 'PAPER OUT', 'zbi_code': '0003', …}]

back = transport.send_and_read(host, zpl_with_hv,
                               expect={"header": "CODE[", "terminator": "]"})
back["values"]               # 打印机回读的字段值，拿来和你要打的值比对
```

`send_and_verify` 会先查 `~HS`：纸/碳带/头/暂停任一异常就**拒绝发送**（`stage="preflight"`），
发完再轮询到「格式队列为空、剩余张数为 0」才算 `printed`。`parse_host_status()` 是纯函数，
可以脱离打印机单测；对手册里"打印机会完全不回话"的五种状态（缺纸、缺碳带、头开、卷满、超温）也会给出提示。

## 数据在哪

`zpl_core/data/` 随包安装：

- `commands.json` —— **224 条手册命令**：页码、名称、Format 行的参数串，生成自手册正文
- `command_catalog.txt` —— 旧版命令字目录，仅在 `commands.json` 缺失时兜底
- `ocr/ch_PP-OCRv4_{det,rec}_infer.onnx` + `ppocr_keys_v1.txt`

`ZPL_CORE_DATA` 可以覆盖数据目录（源码树调试用），`ZPL_CORE_OCR_MODELS` 可以单独指定模型目录。

## 测试

```bash
pip install -e ".[all]"
python tests/test_engine.py     # 31 组 ZPL 生成断言（不需要打印机）
python tests/test_package.py    # 包级不变量：数据随包、懒加载边界、命令表与目录一致、无旧命名残留
python tests/test_manual.py     # 手册合规：Format 字母 / 页码 / 默认值逐条比对 + 30 余条回归
python tests/test_edge.py       # ^GF 位图 / 模板变量 / ~HS 闭环（假打印机，无需硬件）
python tools/android_terminal_test.py --printer <printer-ip>   # 真机闭环：终端自己发字节 + 里程计核对出纸张数
python tools/android_barcode_matrix.py --host <printer-ip> --serial <adb>   # 逐制式打印 + 拍照解码（见 docs/symbology-matrix.md）
```

## 边界

- 只做 ZPL II / Link-OS 打印链路：不做 RFID 编码、SNMP 监控、字体下载。
- `validate_zpl` 通过 **不等于** 码能扫：静区、模块宽、纠错级只有纸和扫码枪能确认。
- `render` 是版式渲染器，不是 ZPL 模拟器：它画本引擎会产生的命令子集，画不了的在 `approximated` 里明说。
- `photo` 识别出的文字一律当"未核对"，出纸前逐字念一遍。
- `send_and_verify` 的"已打印"以打印机的 `~HS` 为准；`^HV` 回读的是打印机侧的字段值。
  两者都比"字节发出去了"强，但都不等于"码能扫"——那还是得扫码枪。

## 免责声明

ZPL 是一种最初由 **Zebra Technologies Corporation** 开发的打印机控制语言，ZPL II / ZBI 2 /
SGD 的规范与手册均由 Zebra 发布。**zpl-core 是一个独立的、非官方的工具**，与 Zebra
Technologies Corporation **没有关联、未获授权、未获认可、也未获赞助**，既不是 Zebra 产品，
也不是其替代品。此处提及的任何商标、产品名与手册编号均为其各自所有者的财产，仅用于描述本
软件兼容的对象；本项目不含 Zebra 的驱动、固件、SDK 或手册正文。

**本软件用于开发与调试目的。** 它不是完整实现，也不是经过认证的实现；其输出只是对真实硬件
实际输出的近似：

- `validate_zpl` 通过 **不等于**码能扫（静区、模块宽、纠错级只有真机和扫码枪能确认）；
- `render` 是版式渲染器，不是 ZPL 模拟器，字形与字体度量与打印机不同；
- `photo` 的 OCR 结果一律视为"未核对"；
- 是否可读、可扫、合规（含行业标准与法规）只能由真机验证；量产或交付前请先用样张验证。

使用本软件产生的打印错误、耗材浪费或业务损失由使用者自行承担。完整中英文条文见
[DISCLAIMER.md](DISCLAIMER.md)，与 [LICENSE](LICENSE) 的 MIT 免责条款一致。

MIT。
