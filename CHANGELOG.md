# Changelog

按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，版本号遵循语义化。

## 0.3.0 — 2026-11-18

端侧三件事：图片能打、模板能复用、打完能验。三件都对着手册实现（`^GF` p.215、`^DF` p.174、
`^XF` p.372、`^FN` p.200、`~HS` p.233-236、`^HV` p.239），新增 `tests/test_edge.py` 守着。

### 1. `^GF` 位图 / 图片

- 新增 `zpl_core.raster`：PNG/JPEG 或 PIL 图像 → `Bitmap` → `^GFA,b,c,d,<hex>`。
  `dither="threshold"`（logo/文字）或 `"floyd"`（照片，Floyd–Steinberg），支持缩放、反相。
- **位图输入不需要任何依赖**：`raster.from_rows(["11110000", …])` 走纯 stdlib；只有读文件才要 `[render]`。
- `builder` 的 `image` 字段现在有三条路：`name`（`^XGR` 调打印机里的图）、`path`（本地文件光栅化）、
  `bitmap`（自带位图）。超过 `^GF` 上限（99999 字节）报错，超过 20000 字节警告并估算串口传输时间。

### 2. `^DF` / `^XF` / `^FN` 模板变量

- `build_template(spec, name=…)` → `(zpl, fields, issues)`：变量字段（`"var": "sku"` / `"fn": 3`）
  在存储格式里只发 `^FN`，不发 `^FD`（手册 p.200）。
- `fill_template(name, values, fields=…)` → 每次打印只发
  `^XA^XFR:NAME.ZPL^FN1^FD…^FS^XZ`，几百字节；支持按编号或变量名赋值。
- `template_field_map(spec)` 给表单用；`quantity` 归 recall 而不是模板（模板里会被剥掉并提示）。
- 名字长度按手册校验：`^DF` 1-16、`^XF` 1-8，超过 8 字符在生成模板时警告、在 recall 时报错。

### 3. 打印闭环：`~HS` + `^HV`

- `transport.parse_host_status(raw)`：纯函数解析 `~HS` 三段串（通讯参数、媒体类型、打印模式、
  队列里格式数、剩余张数、缺纸/头开/缺碳带/超温/暂停/缓冲区满/部分格式/RAM 损坏…），
  每条错误带上 `knowledge.STATUS_NOTES` 里的 ZBI 码。
- `transport.query_status(host)`：发 `~HS` 并解析；打印机会在缺纸/缺碳带/头开/卷满/超温时**完全不回话**
  （p.233），这种情况单独报 `no_response` 并提示，不当成网络错误。
- `transport.send_and_verify(host, zpl)`：就绪检查 → 发送（可重试）→ 轮询到空闲，返回
  `stage`（preflight / send / print / printed）与时间线；打印机没就绪时**一个字节都不发**。
- `transport.send_and_read(host, zpl, expect={…})`：读 `^HV` 回读的字段值，用来核对"打印机侧"的数据。
- 字段支持 `"hv": {"bytes": 16, "header": "CODE[", "terminator": "]"}`，自动给字段分配 `^FN` 并发出
  `^HV#,…`（header/terminator 走 `^FH` 转义）。

### 测试

- 新增 `tests/test_edge.py`：`^GF` 位图与上限、模板/回填/名字长度、`~HS` 解析、
  以及用**假打印机**（本地 socket，会应答 `~HS` 并回显 `^HV`）跑通闭环的四种结局：
  打印成功、打印机未就绪拒发、根本没有打印机、`require_ready=False` 时的发送失败。

## 0.2.0.post0 — 2026-11-18

**只有文档 / 元数据，代码与 0.2.0 完全一致。** PyPI 的发布元数据不可修改，所以用 PEP 440 的
post 版本补上免责声明（`pip install zpl-core` 会自动选到它）。

- 新增 `DISCLAIMER.md`（中英双语）：ZPL 由 Zebra Technologies Corporation 开发，本项目是独立、
  非官方工具，与之无关联/授权/认可/赞助；不含 Zebra 驱动、固件、SDK 或手册正文；仅用于开发调试，
  输出只是对真实硬件的近似，可扫性与合规性只能由真机验证。
- README 增加「免责声明」章节（PyPI 页面展示的就是 README）。

## 0.2.0 — 2026-11-18

对着手册原文 **P1134473-11EN Rev A（2026-07-05）** 逐条复核后，修正了一批会打出错误标签而
不报错的缺陷，并把手册事实做成可校验的数据文件。

### 会打错码的修正（务必看）

- **UPC-A / UPC-E 的命令映射是反的**：`upca` 曾发 `^B9`（= UPC-E），`upce` 曾发 `^B0`
  （= Aztec）。按 Table 34（p.1587-1588）改为 `upca → ^BU`（p.142）、`upce → ^B9`（p.85）。
  旧版打 UPC-A 出来的是 UPC-E，打 UPC-E 出来的是 Aztec 码，两者都是合法 ZPL，只有扫码枪能发现。
- **Data Matrix ECC200 被静默降级**：`^BX` 的 `s` 默认值被当成 200（手册 p.144 是 **0**），
  于是 `quality=200` 被当作"默认值"省略，实际按 ECC000 打。现在默认值 0，显式指定一定发。
- **`^BX` 参数从 5 个补到 8 个**：`o,h,s,c,r,f,g,a` —— 新增 format ID、转义字符、长宽比。
- **MSI 第二个校验位发错字母**：`E` → 手册的 `e2`（p.123）。旧的 `^BM…,E` 不是合法参数。
- **`^PO` 发 `Y`**：手册只接受 `N` / `I`（p.322），`^POY` 无效。
- **`^MM` 缺切刀等模式**：从 `T/P/R/A/K` 补到 `T/P/R/A/C/D/F/L/U/K`，第二参数是 prepeel
  select 而不是 media-loss 标志。
- **`^MN` 有 `B`、缺 `V`**：手册的模式是 `N/Y/W/M/A/V`，黑标是 `M`，没有 `B`。
- **零售码位数全部按手册收紧**：EAN-13=12、EAN-8=7、UPC-A=11、UPC-E=10、UPC 扩展=2或5。
  打印机自己算校验位并按左补零截断，多给一位 → 数字整体错位。旧的"11 位 + 校验位"提示是错的。
- **Code 128 模式 D（UCC/EAN）此前被拒**，现在可用。

### 行为修正（输出会变）

- 条码方向默认改成"当前 `^FW` 值"，不再硬编码 `N`（`^BC` p.94 等）；`^FW` 设了 R 的标签
  不会再被逐字段的 `N` 覆盖。
- `^FB` 第三参数是**每行增减的间距**（-9999~9999，p.186），不是行高；新键 `block.line_spacing`，
  `line_height` 保留为别名。`render` 的行距算法同步修正。
- `^FO` / `^FT` 支持第三个参数 `justify`（0/1/2，p.201/205）。
- `^GB` 默认厚度 2 → **1**（p.210），圆角 `r` 收敛到 0-8。
- `^GC` 直径缺省 3、超限收敛 4095（p.212）。
- `~SD` 补成两位（`~SD05`），小数仍按 `8.3` 发（p.333）。
- `^LS` 允许 -9999~9999、`^LT` 允许 -120~120（p.296/297），超范围给 error/warning。
- `^PQ` 支持 `q,p,r,o,e` 五参数（`pq_extra` 传入），不再只发数量。
- `^PR` 速度表按 p.326 重写：1-12 及别名 `A=2/B=3/C=4/D=6/E=8`（旧的 "A=fastest" 不存在）。
- 无字号文本默认字体回到手册的 `^CF` 值 `A`；给了字号仍用可缩放字体 `0`（位图字体只吃倍率）。
- 二维码手动输入（`input_mode="M"`）现在必须给 `char_mode`（N/A/Bxxxx/K，p.130），并支持
  混合模式开关；不带字符模式会报错，之前会发出非法 ZPL。
- `^FR` 改为字段级 `reverse: true`（p.203 说明它只作用于单个字段）；独立的 `reverse` 字段仍可
  用但会给出提示。
- `^FD` 长度上限 3072 字节**真的会被检查**了（`^FD` p.190），此前 `FD_MAX` 定义了从不使用。

### 预览（render）

- **方向终于生效**：`^A`/`^B` 的 `N/R/I/B` 以前被整条丢弃，旋转的条码/文字一律按水平画，
  预览看起来"旁边是空的"，实际纸上会压字。现在按字段原点旋转，尺寸随之交换（`R` 往右下长、
  `B` 往左上长、`I` 读到原点为止）。
- 旋转字段落到标签外面时会出 warning（`field at ^FO … extends outside the label`），
  这正是预览存在的意义。
- `^FB` 的 `c` 按"行距增减"重算；`^A@` 的 TrueType 字号以前被忽略（按默认 20 点画），
  现在按 `^A@N,h,w` 的 h 画。

### 校验器

- 命令分词改成"先试 2 字符、再退 1 字符"，`^A0N,30` 不再被当成 `^A0`。
- 命令表换成 `data/commands.json`（224 条，页码 + Format 参数，生成自手册正文），删掉旧目录里
  29 个非命令 token（`^A0`、`^AB`、`^2`、`~0` …）。
- 新增对 `^PO` 取值、二维码 `^FD` 开关串、`^BX` 容量、零售码位数的检查。
- `knowledge.COMMAND_NOTES` 的页码全部由 `commands.json` 覆盖同步，并修正了 10 处错页
  （`^LS` 322→296、`^LT` 335→297、`^PM` 318→319、`^PO` 308→322、`^FS` 251→204、`^XG`
  372→373、`~DG` 444→175、`^CD`/`^DF`/`~DY`、`^MC`、`^SC`）。

### 知识库

- `^CI` 的取值列表按 p.156-157 重写：**手册里没有 936 / 950 代码页**，中文是 `^CI28`（UTF-8）
  配 CJK 字体，或者 `^CI24` / `^CI26`；并补上字符映射对 `s1,d1,…`。
- `^MM` / `^MN` / `^PR` / `^PQ` / `^GB` / `^GC` / `^FB` / `^LS` / `^LT` / `^A` / `^CF` 的默认值、
  范围、说明全部按手册重写；删掉 `COMMAND_NOTES` 里 `^LH`、`^PR` 的重复键。
- 新增 `tlc39`（`^BT`）制式，条码从 28 种增到 29 种。
- 新增 `knowledge.COMMANDS`（整张命令表）和 `knowledge.page_of()`。

### 测试与文档

- 新增 `tests/test_manual.py`：Format 字母与页码逐条比对 + 30 余条针对性回归。
- `tests/test_package.py`：命令表与目录一致性、非命令 token 清零。
- `tests/test_engine.py`：原先把错误行为写进断言的用例（`^B9` 当 UPC-A、13 位 EAN）已按手册改正。
- 新增 `docs/manual-conformance.md`（手册口径、坑位、复核方法）与本 CHANGELOG。

## 0.1.1 — 2026-10-25

- 缺 extras 时给出可复制的安装命令；测试按行尾归一再比字节数。

## 0.1.0 — 2026-10-25

- 从 zebra-printer-mcp 抽出引擎独立成包：stdlib 核心 + `render` / `ocr` 可选 extras。
