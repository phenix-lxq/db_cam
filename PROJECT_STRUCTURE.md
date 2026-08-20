# 项目文件架构说明

## 顶层结构

```text
双目相机/
├─ stereo_camera.py
├─ stereo_calibrate_cct14.py
├─ generate_cct14_a4_board.py
├─ cct14_3x3_A4_60mm.pdf
├─ cct14_3x3_A4_60mm.svg
├─ cct14_layout.csv
├─ README.md
├─ CCT14_STEREO_CALIBRATION.md
├─ PROJECT_STRUCTURE.md
├─ CCTDecode/
└─ 14-Bit-Circular-Coded-Target-master/
```

运行后生成但不提交到 Git 的目录：

```text
captures/
calibration_debug/
stereo_cct14.yaml
```

## 核心流程

```text
generate_cct14_a4_board.py
    -> cct14_3x3_A4_60mm.pdf
    -> cct14_layout.csv

stereo_camera.py
    -> captures/left_*.png
    -> captures/right_*.png

stereo_calibrate_cct14.py
    -> stereo_cct14.yaml
    -> calibration_debug/
```

## 顶层脚本

### `stereo_camera.py`

USB 双目相机采集程序。

功能：

- 打开左右拼接双目相机，默认 `--mode sbs --camera 1`
- 支持两个独立相机模式 `--mode dual`
- 使用 PyQt6 显示实时预览窗口
- 点击“拍照”或按 `S` 保存左右图片
- 按 `Q`、`Esc` 或关闭窗口退出

默认输出目录是 `captures/`。

### `generate_cct14_a4_board.py`

生成 A4 版 14-bit 环形编码点标定板。

输出：

- `cct14_3x3_A4_60mm.pdf`：打印用 PDF
- `cct14_3x3_A4_60mm.svg`：同版 SVG
- `cct14_layout.csv`：编码点 ID 与物理坐标

当前标定板只保留 9 个编码点，不放标题、说明文字和编号，减少解码误识别。

### `stereo_calibrate_cct14.py`

双目标定主程序。

功能：

- 读取 `captures/` 中成对的左右图片
- 调用 `CCTDecode/CCTDecode/CCTDecodeRelease.py` 解码 14-bit 编码点
- 根据 `cct14_layout.csv` 匹配真实物理点
- 使用 OpenCV 完成左右相机单目标定和双目标定
- 输出 `stereo_cct14.yaml`
- 输出 `calibration_debug/` 检查图

## 标定板文件

### `cct14_3x3_A4_60mm.pdf`

最终打印文件。打印时选择 `100%` 或“实际大小”，关闭“适合页面”。

### `cct14_3x3_A4_60mm.svg`

PDF 的 SVG 源文件，方便检查图案内容。

### `cct14_layout.csv`

标定板物理布局文件。

字段：

```text
id,x_mm,y_mm,target_number,source_code
```

含义：

- `id`：解码程序识别出来的 ID
- `x_mm`、`y_mm`：标定板平面坐标，单位 mm
- `target_number`：14bit 生成代码中的目标编号
- `source_code`：原始编码值

## 解码代码

### `CCTDecode/CCTDecode/CCTDecodeRelease.py`

环形编码点检测和解码主文件。

保留的能力：

- 二值化图像并提取轮廓
- 圆度检测
- 轮廓与拟合椭圆的 IoU 检测
- 最小中心圆尺寸检测
- 仿射归一化候选区域
- 判断是否符合 CCT 中心圆和编码环结构
- 输出编码 ID 和图像中心坐标

### `CCTDecode/CCTDecode/DrawCCT.py`

只保留 bit 列表和整数编码的转换函数。

### `CCTDecode/CCTDecode/Support.py`

只保留解码归一化需要的最小二乘仿射变换函数。

## 14bit 编码生成代码

### `14-Bit-Circular-Coded-Target-master/find_codes.py`

生成 14bit 环形编码序列。

### `14-Bit-Circular-Coded-Target-master/create_target_sheets.py`

根据编码值生成单个 SVG 环形编码点。

这个目录里原来的 Inkscape/PDFtk 批量导出逻辑已经删除，因为本项目使用 `generate_cct14_a4_board.py` 和 PyMuPDF 直接生成 PDF。

## 已删除的无用内容

清理掉的内容包括：

- CCTDecode 原仓库的视频演示脚本
- CCTDecode 原仓库的 data/result 示例图片
- Python `__pycache__` 缓存
- 旧的 `targets_inkscape.pdf`
- 与当前裁剪后代码不一致的第三方 README
