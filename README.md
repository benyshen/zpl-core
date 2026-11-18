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
| `builder` | 标签结构体 → ZPL II；mm→dots、29 种条码、`^A@` TrueType 中文、`^GB/^GC/^FO..z` 图形、`^FB` 域块 | — |
| `builder.validate_zpl` | 拿手册命令表校验原始 ZPL，返回 `issues[]`（severity + code） | — |
| `knowledge` | 224 条手册命令（页码 + Format 参数）、71 条命令详解、28 种制式数据规则、27 条 SGD、13 个状态码 | — |
| `transport` | TCP 9100、Windows RAW 队列（winspool）、USB 队列、写 `.zpl` 预览字节 | — |
| `xlsx_batch` | 一行一条标签，纯 `zipfile`+`xml` 读 xlsx，整批一条 ZPL 流 | — |
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
```

## 边界

- 只做 ZPL II / Link-OS 打印链路：不做 RFID 编码、SNMP 监控、`^GF` 位图流、字体下载。
- `validate_zpl` 通过 **不等于** 码能扫：静区、模块宽、纠错级只有纸和扫码枪能确认。
- `render` 是版式渲染器，不是 ZPL 模拟器：它画本引擎会产生的命令子集，画不了的在 `approximated` 里明说。
- `photo` 识别出的文字一律当"未核对"，出纸前逐字念一遍。

MIT。
