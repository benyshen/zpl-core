# zpl-core

[![PyPI](https://img.shields.io/pypi/v/zpl-core.svg)](https://pypi.org/project/zpl-core/)
[![Python](https://img.shields.io/pypi/pyversions/zpl-core.svg)](https://pypi.org/project/zpl-core/)

ZPL II 标签引擎。一份代码，三个使用者：

- **[zebra-printer-mcp](https://github.com/benyshen/zebra-printer-mcp)** —— MCP 服务器外壳（9 个工具）
- **[zebra-printer-skill](https://github.com/benyshen/zebra-printer-skill)** —— CLI / skill 外壳（10 个子命令）
- 你自己的脚本

核心（build / validate / knowledge / transport / xlsx）**零第三方依赖**；渲染和 OCR 是可选 extras，不装不会污染环境。

## 安装

```bash
pip install zpl-core            # 生成、校验、发送、查状态——纯 stdlib（PyPI，>=3.10）
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
assert not issues, issues
transport.send(zpl, host="192.168.1.50")      # TCP 9100；也支持 Windows 队列 / USB / 预览文件
```

## 模块

| 模块 | 做什么 | 额外依赖 |
|---|---|---|
| `builder` | 标签结构体 → ZPL II；mm→dots、28 种条码、`^A@` TrueType 中文、`^GB/^GC/^FR` 图形、`^FB` 域块 | — |
| `builder.validate_zpl` | 拿手册命令目录校验原始 ZPL，返回 `{ok, issues}` | — |
| `knowledge` | 253 条命令、默认值/范围、28 种制式、27 条 SGD、13 个状态码 | — |
| `transport` | TCP 9100、Windows RAW 队列、USB、写预览文件；`~HS` 状态解析 | — |
| `xlsx_batch` | 一行一条标签，纯 `zipfile`+`xml` 读 xlsx，整批一条 ZPL 流 | — |
| `render` | ZPL → PNG，离线，用于让 agent "看一眼"版式 | `[render]` |
| `photo` | 标签照片 → ZPL（透视校正、字号推断、条码重建） | `[ocr]` |
| `ocr` | PP-OCRv4 检测/识别（onnxruntime）+ zxing-cpp 条码兜底 | `[ocr]` |
| `vision` | 纯 stdlib 的图像预处理辅助 | — |

## 数据在哪

`zpl_core/data/` 随包安装：

- `command_catalog.txt` —— 253 条命令字，从 ZPL II Programming Guide（zpl-zbi2-pg-en-202609）的索引解析而来
- `ocr/ch_PP-OCRv4_{det,rec}_infer.onnx` + `ppocr_keys_v1.txt`

`ZPL_CORE_DATA` 可以覆盖数据目录（源码树调试用），`ZPL_CORE_OCR_MODELS` 可以单独指定模型目录。

## 测试

```bash
pip install -e ".[all]"
python tests/test_engine.py     # 31 组 ZPL 生成断言（不需要打印机）
python tests/test_package.py    # 包级不变量：数据随包、懒加载边界、253 条目录、无旧命名残留
```

## 边界

- 只做 ZPL II / Link-OS 打印链路：不做 RFID 编码、SNMP 监控、`^GF` 位图流、字体下载。
- `validate_zpl` 通过 **不等于** 码能扫：静区、模块宽、纠错级只有纸和扫码枪能确认。
- `photo` 识别出的文字一律当"未核对"，出纸前逐字念一遍。

MIT。
