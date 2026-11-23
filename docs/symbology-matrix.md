# 制式实机验证矩阵（ZR668-200dpi + TC201L，2026-11-23）

29 种制式全部**出纸正常**，并用现场扫码枪**全部识读通过**。通用解码器 zxing-cpp 能读回 18 种；
剩下 11 种是开源库没有对应解码器，不是打印问题。

环境：ZR668-200dpi / fw `V86.20.21Z` / `LINK-OS 6.2` / 200 dpi / 连续纸 60mm / 终端 TC201L `192.168.28.176`
工具：`zpl-core/tools/android_barcode_matrix.py`（分页打印 → 摄像头拍照 → 多尺度 zxing 解码）

## 结果

| # | 制式 | 命令 | zxing 能读 | 扫码枪 | 备注 |
|---|---|---|---|---|---|
| 1 | code128 | `^BC` | ✅ | ✅ | |
| 2 | code39 | `^B3` | ✅ | ✅ | |
| 3 | code93 | `^BA` | ✅ | ✅ | |
| 4 | code11 | `^B1` | — | ✅ | zxing-cpp 无此制式 |
| 5 | i2of5 | `^B2` | ✅ | ✅ | 读出为 `ITF` |
| 6 | industrial2of5 | `^BI` | ✅ | ✅ | 读出为 `ITF` |
| 7 | std2of5 | `^BJ` | ✅ | ✅ | 读出为 `ITF` |
| 8 | codabar | `^BK` | ✅ | ✅ | 带 `A…A` 起止符 |
| 9 | msi | `^BM` | — | ✅ | zxing-cpp 无此制式 |
| 10 | plessey | `^BP` | — | ✅ | zxing-cpp 无此制式 |
| 11 | ean13 | `^BE` | ✅ | ✅ | 输入 12 位，校验位自动 |
| 12 | ean8 | `^B8` | ✅ | ✅ | 输入 7 位 |
| 13 | upca | `^BU` | ✅ | ✅ | 常被读成 EAN-13（前导 0） |
| 14 | upce | `^B9` | ✅ | ✅ | 输入 10 位，压缩形式 |
| 15 | upcext | `^BS` | — | ✅ | 附加码，须挨着主码才能读 |
| 16 | gs1databar | `^BR` | ✅ | ✅ | 读出带 `(01)` 前缀 |
| 17 | postnet | `^BZ` | — | ✅ | zxing-cpp 无此制式 |
| 18 | planet | `^B5` | — | ✅ | zxing-cpp 无此制式 |
| 19 | codablock | `^BB` | 部分 | ✅ | zxing 按 Code 128 读出内容 |
| 20 | code49 | `^B4` | — | ✅ | **自动增行，必须单独留白** |
| 21 | logmars | `^BL` | ✅ | ✅ | 本质是 Code 39 |
| 22 | qrcode | `^BQ` | ✅ | ✅ | 数据须带 `QA,` 开关 |
| 23 | datamatrix | `^BX` | ✅ | ✅ | |
| 24 | pdf417 | `^B7` | ✅ | ✅ | 见 `stacked-2d-barcodes.md` |
| 25 | aztec | `^BO` | ✅ | ✅ | |
| 26 | micropdf417 | `^BF` | ✅ | ✅ | **mode 决定容量**，见下 |
| 27 | upsmaxicode | `^BD` | — | ✅ | 实拍可见同心圆靶心 |
| 28 | tlc39 | `^BT` | 部分 | ✅ | 数据须"6 位数字+逗号"；zxing 只读 Code39 半边 |
| 29 | usps-im | `^BZ` | — | ✅ | |

## 四种"打了但等于没打"的静默失败（全部已在 zpl-core 里加校验）

| 症状 | 原因 | zpl-core 的错误码 |
|---|---|---|
| 条码区整片空白 | `^B7` 的 `c×r` 容量不够 | `BC_CAPACITY` |
| 条码区整片空白 | `^BF` 的 `mode` 容量不够（默认 mode 0 只装 6 字母） | `BF_CAPACITY` |
| 只印出 Code39 半边 | `^BT` 数据不是"6 位数字+逗号+序列号" | `BT_FORMAT` |
| 符号被纸边裁掉 | 模块宽度按纸宽算超限 | `ROW_TOO_TALL` / 手工核算 |

以上四种打印机都不报错（`~HQES` 依旧 `ERRORS: 0 WARNINGS: 0`），只能靠版式核对和打印后验收发现。

## 复现

```bash
cd E:/workspace/zpl-core
.venv/Scripts/python.exe tools/android_barcode_matrix.py \
    --host 192.168.28.90 --serial <adb序列号> --shots 3 --delay 2.5
# 结果: scratch/barcode_matrix.json
```

拍照解码的三个前提（都踩过）：图块要开得比一维码宽（1000px 会把 Code128 切断）、
照片里会同框多张标签所以要**唯一载荷**、出纸口前方不能压着上一轮的旧纸带。
