# 手册口径（manual conformance）

zpl-core 的每一个默认值、取值范围、参数字母和页码，都以这份文档为准：

> **ZPL II, ZBI 2, Set-Get-Do, Mirror, WML Programming Guide**
> P1134473-11EN Rev A · 2026-07-05 · 1769 页
> 文件：`zpl-zbi2-pg-en-202609.pdf`（不在仓库里，版权归 Zebra）

文中的 `p.N` 一律指手册**印刷页码**。PDF 的物理页索引比印刷页码小 1（封面算第 0 页），
脚本里已经换算过。

## 三份东西，一个来源

| 产物 | 谁在用 | 怎么来的 |
|---|---|---|
| `src/zpl_core/data/commands.json` | `knowledge.known_commands()`、`validate_zpl`、`knowledge.page_of()` | `scripts/extract_commands.py` 从 PDF 的命令小节生成（224 条：页码 / 名称 / Format 行参数串） |
| `builder.BARCODE_SPECS` | 条码参数发射 | 手写，`letters` 逐字抄 Format 行，`d` 是手册的 `Default:` |
| `knowledge.COMMAND_NOTES` | 文字说明 | 手写散文；**页码在 import 时被 commands.json 覆盖**，不会再飘 |

`tests/test_manual.py` 把这三者对齐：每个制式的字母串、页码必须与 commands.json 相等；每条
`COMMAND_NOTES` 的页码必须等于手册页码。

## 怎么重新生成 commands.json

```bash
pip install pymupdf
python scripts/extract_commands.py "zpl-zbi2-pg-en-202609.pdf"
# -> src/zpl_core/data/commands.json
```

脚本只挑选"页首是 `ZPL Commands`、紧跟一行恰好是命令 token"的小节，所以抽出来的是**命令自己的
那一页**。抽不到的（手册不给 `Format:` 行的 `~DY`、`~HS`、`^HT` 等）在脚本的 `EXTRA` 表里手工登记。

## 手册自身的坑（不是我们的 bug，但会误导）

1. **`^B9`（UPC-E, p.85）的 Format 行漏了 `o`** —— 印的是 `Format: ^B9,h,f,g,e`，但同一页的
   参数表第一项就是 `o = orientation`。代码按 `o,h,f,g,e` 处理，`split_letters` 有这个背景注释。

2. **`^FD` 的 `Format:` 行在 p.107 也出现过一次** —— 那是 `^BD` MaxiCode 小节里的
   `Format: ^FD <hpm><lpm>`（MaxiCode 的字段数据格式），不是 `^FD` 本身。正文在 p.190。
   第一版生成器就抓错了页，现在 `commands.json` 里是 190。

3. **同一份手册里 `^B0` 和 `^BO` 都是 Aztec**（p.64 / p.124），参数完全一样。旧的 zpl-core 把
   `^B0` 当成 UPC-E 用，这是错的 —— UPC-E 是 `^B9`，UPC-A 是 `^BU`。见 Table 34（p.1587-1588）。

4. **`^CI` 没有 936 / 950** —— p.156-157 的取值表里 0-13 是 Zebra CP850 各区域集，24/26 是
   Asian 单/多字节，27 是 Zebra CP1252，28-30 是 Unicode，31/33-36 是 CP1250/1251/1253/1254/1255。
   网上的 `^CI936` 说法对这台打印机不成立；中文用 `^CI28` + CJK 字体（`^A@` 调驻留 TTF）。

5. **零售码给多了会被"左补零截断"** —— `^B8`/`^B9`/`^BE`/`^BU`/`^BS` 的字段数据长度是固定的，
   打印机自己算校验位。多给一位校验位等于把最高位挤掉，码就错了。所以校验器把"长度不等于手册值"
   报 error，而不是 warning。

6. **`^FB` 的 `c` 不是行高** —— p.186 原文是"增加或删除行间的点"，范围 -9999~9999。当成绝对
   行高会让多行文本挤到一起或散开。

7. **`^PO` 只有 `N` / `I`** —— p.322。`^POY` 不是"D""也不是"是"，是非法值；想反转整张标签用
   `I`，想整版镜像用 `^PM`（p.319）。

8. **`^MN` 没有 `B`** —— 黑标是 `M`（p.307），另有 `V`（连续纸变长）。旧知识库把 `B` 当黑标
   是错的。

## 代码里有意的偏离

| 地方 | 手册怎么说 | 代码怎么做 | 为什么 |
|---|---|---|---|
| 无字号文本的字体 | `^CF` 的出厂值是 `A` | 无字号 → `A`；**给了字号 → `0`** | `A` 是位图字体，只接受矩阵的 1-10 倍高度；用户传 `size_mm` 时必须用可缩放字体 0 |
| `^BY h` | 只写"Initial Value at Power Up: 10"，没有 `Default:` | `BY_H = 10` | 出厂值即实际默认 |
| `^BR c` / `^BQ c` / `^BO b` | 按打印头密度给默认（150dpi=1、200/203=2、300=3、600=6） | `magnitude_default(dpi)` 现算，未显式指定就不发 | 不写死，203 和 300 的标签各自对 |
| 条码方向 | 默认"当前 `^FW` 值" | 未指定 → 不发方向参数；若后面还有参数，则补 `^FW` 解析出的值 | 无条件发 `N` 会覆盖 `^FW` |

## 核对一份新手册时怎么做

1. 换 `PI134473-…` 版本后先跑 `scripts/extract_commands.py`，`git diff data/commands.json` 看
   哪些页码/Format 行变了。
2. `python tests/test_manual.py` —— 字母串或页码对不上会直接点名。
3. 手册新增了制式时，在 `BARCODE_SPECS` 里照 Format 行加一条，再在 `test_manual.SAMPLE` 里加
   一行样例数据（否则"全部制式可构建"那条测不到它）。
4. 页码变了但说明没变时，`COMMAND_NOTES` 不用动 —— import 时会自动同步。
