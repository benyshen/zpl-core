# 免责声明 / Disclaimer

## 中文

ZPL 是一种最初由 **Zebra Technologies Corporation** 开发的打印机控制语言。ZPL II、ZBI 2、
Set-Get-Do（SGD）、Mirror、WML 的规范与其官方手册（本项目依据的是 P1134473-11EN Rev A）
均由 Zebra Technologies Corporation 发布。

**zpl-core 是一个独立的、非官方的开源项目**，与 Zebra Technologies Corporation
**没有关联、未获授权、未获认可、也未获赞助**。它既不是 Zebra 产品，也不是 Zebra 产品的替代品。
本项目中提到的所有商标、产品名称与手册编号均属于其各自的所有者，仅用于说明本软件试图兼容的对象。

- 本项目**不含** Zebra 的驱动、固件、SDK 或手册正文；`data/commands.json` 只是从公开手册中
  摘出的命令名、页码与参数位序，用于校验，不含手册原文。
- **用途是开发与调试**。它不是完整实现，也不是经过认证的实现；README 的「边界」章节列了
  明确不做的部分（RFID 编码、SNMP 监控、`^GF` 位图流、字体下载）。
- **输出只是对真实硬件的近似**：
  - `validate_zpl` / `validate_label` 通过，**不代表**码能扫——静区、模块宽、纠错级只有纸和
    扫码枪能确认；
  - `render` 是版式渲染器，不是 ZPL 模拟器：字形、字体度量与模块取整都与打印机不同；
  - `photo` 的 OCR 结果一律视为"未核对"，出纸前必须逐字念一遍。
- 最终是否可读、可扫、合规（含行业标准与法规要求），只能由**真机和扫码枪**验证。
- 使用本软件产生的打印错误、耗材浪费、返工或任何业务损失，由使用者自行承担。
  **量产或对外交付前，请先用样张验证。**

## English

ZPL is a printer control language originally developed by **Zebra Technologies Corporation**.
The ZPL II / ZBI 2 / Set-Get-Do / Mirror / WML specifications and their official manuals
(this project was written against P1134473-11EN Rev A) are published by Zebra Technologies
Corporation.

**zpl-core is an independent, unofficial open-source project.** It is **not affiliated with,
authorized by, endorsed by, or sponsored by** Zebra Technologies Corporation, and it is
neither a Zebra product nor a replacement for one. All trademarks, product names and manual
part numbers mentioned here are the property of their respective owners and are used only to
describe what this software aims to be compatible with.

- No Zebra drivers, firmware, SDKs or manual text are included. `data/commands.json` holds only
  command names, page numbers and Format-line parameter letters extracted from the public manual
  for validation purposes — not the manual's text.
- It is a **development and debugging aid**, not a complete or certified implementation. The
  "边界 / Limits" section of the README lists what is deliberately out of scope (RFID encoding,
  SNMP monitoring, `^GF` bitmaps, font downloads).
- **Output is an approximation of real hardware.** `validate_zpl` passing does not mean a code
  will scan; `render` is a layout renderer, not a ZPL emulator (glyphs, font metrics and module
  rounding differ from the printer); `photo` OCR output is unverified until a human reads it.
- Whether a label is readable, scannable or compliant (including industry standards and
  regulations) can only be confirmed on real hardware with a real scanner.
- You use this software at your own risk; misprints, wasted media or business losses are your
  responsibility. **Validate a sample on the actual printer before production use.**

## 许可

代码以 MIT 许可发布（见 [LICENSE](LICENSE)）。MIT 许可里的免责条款与本页一致：
软件按"现状"提供，不附带任何明示或暗示的担保。
