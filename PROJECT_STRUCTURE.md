# 项目文件架构说明

本文档用于说明当前双目相机项目的文件组织、核心脚本作用，以及数据从采集到标定的流向。

## 目录总览

```text
双目相机/
├─ stereo_camera.py
├─ stereo_calibrate_cct14.py
├─ generate_cct14_a4_board.py
├─ cct14_layout.csv
├─ cct14_3x3_A4_60mm.pdf
├─ cct14_3x3_A4_60mm.svg
├─ targets_inkscape.pdf
├─ CCT14_STEREO_CALIBRATION.md
├─ README.md
├─ captures/
├─ calibration_debug/                 # 运行标定后生成
├─ CCTDecode/
├─ 14-Bit-Circular-Coded-Target-master/
├─ .vscode/
└─ __pycache__/
```

## 核心流程

```text
生成 14bit 标定板
  generate_cct14_a4_board.py
        |
        v
  cct14_3x3_A4_60mm.pdf + cct14_layout.csv
        |
        v
打印标定板并拍摄双目图片
  stereo_camera.py
        |
        v
  captures/left_*.png + captures/right_*.png
        |
        v
解码编码点并完成双目标定
  stereo_calibrate_cct14.py
        |
        v
  stereo_cct14.yaml + calibration_debug/
```

## 顶层文件

### `stereo_camera.py`

USB 双目相机采集程序，使用 OpenCV 打开相机，使用 PyQt6 显示窗口。

主要功能：

- 打开双目 USB 相机。
- 支持左右拼接的单设备模式：`--mode sbs`。
- 支持左右两个独立摄像头模式：`--mode dual`。
- 窗口中有“拍照”按钮。
- 按 `S` 或点击“拍照”保存左右图。
- 按 `Q`、`Esc` 或关闭窗口退出。
- 默认保存到 `captures/`。

常用命令：

```powershell
conda activate db_cam_env
python stereo_camera.py
```

列出可用相机编号：

```powershell
python stereo_camera.py --list
```

当前项目默认按左右拼接双目相机使用：

```powershell
python stereo_camera.py --mode sbs --camera 1 --width 2560 --height 720
```

其中 `2560x720` 表示整幅图像，左右各 `1280x720`。

### `generate_cct14_a4_board.py`

14bit 环形编码点标定板生成脚本。

它会调用 `14-Bit-Circular-Coded-Target-master/` 里的代码来生成标定板图案，而不是手写编码点。

主要输出：

- `cct14_3x3_A4_60mm.pdf`：用于打印的 A4 标定板。
- `cct14_3x3_A4_60mm.svg`：同一标定板的 SVG 源文件。
- `cct14_layout.csv`：每个编码点的物理坐标和解码 ID。

标定板参数：

- 纸张：A4 竖版，`210 mm x 297 mm`。
- 编码点数量：`3 x 3`。
- 编码点外径：`40 mm`。
- 圆心间距：横向 `60 mm`，纵向 `60 mm`。
- PDF 可见内容只保留 9 个编码点，不放标题、说明文字或校验线，避免文字被误识别为编码点。
- 打印时必须选择 `100%` 或“实际大小”，关闭“适合页面”。

重新生成标定板：

```powershell
python generate_cct14_a4_board.py
```

### `cct14_layout.csv`

14bit 标定板布局文件。双目标定时会用它把“解码出来的 ID”转换成“真实世界中的平面坐标”。

列含义：

```text
id,x_mm,y_mm,target_number,source_code
```

当前实际 CSV 中的关键列是：

- `id`：CCT 解码程序识别出来的编码 ID。
- `x_mm`：该点在标定板坐标系中的 X 坐标，单位 mm。
- `y_mm`：该点在标定板坐标系中的 Y 坐标，单位 mm。
- `target_number`：在 14bit 编码生成仓库里的目标编号。
- `source_code`：生成该编码点使用的原始编码值。

注意：如果打印后实际尺寸有缩放，需要根据实际测量结果修改这里的 `x_mm` 和 `y_mm`，否则标定结果会带比例误差。

### `stereo_calibrate_cct14.py`

使用 14bit 环形编码点进行双目标定的主程序。

主要功能：

- 从 `captures/` 读取左右图片对。
- 调用 `CCTDecode/CCTDecode/CCTDecodeRelease.py` 中的 `CCT_extract()` 解码编码点。
- 根据 `cct14_layout.csv` 匹配左右图中的同一个物理点。
- 分别求左右相机内参。
- 求双目外参 `R/T`。
- 输出畸变参数、基础矩阵、极线校正矩阵和 `Q` 矩阵。
- 生成调试图片到 `calibration_debug/`。

默认运行：

```powershell
python stereo_calibrate_cct14.py
```

主要输入：

- `captures/left_*.png`
- `captures/right_*.png`
- `cct14_layout.csv`

主要输出：

- `stereo_cct14.yaml`
- `calibration_debug/`

可选参数示例：

```powershell
python stereo_calibrate_cct14.py --threshold 0.85 --color white
```

当前标定板是黑底白色编码点，所以默认使用：

```text
--color white
```

### `cct14_3x3_A4_60mm.pdf`

最终打印用的 A4 标定板。

打印要求：

- 使用 A4 纸。
- 打印比例选择 `100%` 或“实际大小”。
- 关闭“适合页面”“缩小到可打印区域”等自动缩放。
- 打印后建议直接测量相邻编码点圆心距离，应为 `60 mm`。
- 建议贴到平整硬板上使用。

### `cct14_3x3_A4_60mm.svg`

标定板的 SVG 文件，便于检查或二次编辑。正常使用时优先打印 PDF。

### `targets_inkscape.pdf`

旧的或外部生成的编码点 PDF 文件。当前 3x3 A4 标定流程优先使用 `cct14_3x3_A4_60mm.pdf`。

### `CCT14_STEREO_CALIBRATION.md`

14bit CCT 双目标定的使用说明，包含：

- 标定板打印注意事项。
- 拍摄建议。
- 标定命令。
- 常见参数调整。

### `README.md`

项目入口说明，包含相机采集和标定的最短使用流程。

## 数据目录

### `captures/`

双目相机采集出来的照片目录。

文件命名方式：

```text
left_时间戳.png
right_时间戳.png
```

左右图通过相同时间戳配对。标定程序会自动寻找同名时间戳的 `left_*` 和 `right_*`。

### `calibration_debug/`

标定程序生成的调试图目录。

每张调试图会标出检测到的环形编码点和对应 ID，用来检查：

- 编码点有没有漏检。
- ID 是否识别正确。
- 左右图片中的同一 ID 是否能成功匹配。

如果标定误差偏大，应先检查这个目录里的图片。

### `__pycache__/`

Python 自动生成的缓存目录，可以忽略。它不参与项目逻辑。

### `.vscode/`

VS Code 的本地编辑器配置目录，不属于核心程序。

## 第三方代码目录

### `CCTDecode/`

环形编码点检测和解码代码仓库。

项目中主要使用：

```text
CCTDecode/CCTDecode/CCTDecodeRelease.py
```

其中的核心接口是：

```python
CCT_extract(image, bit, threshold, color)
```

在本项目中，`stereo_calibrate_cct14.py` 会调用它检测每张左右图里的 14bit 编码点。

### `14-Bit-Circular-Coded-Target-master/`

14bit 环形编码点生成代码仓库。

项目中主要使用：

```text
14-Bit-Circular-Coded-Target-master/find_codes.py
14-Bit-Circular-Coded-Target-master/create_target_sheets.py
```

本项目的 `generate_cct14_a4_board.py` 会从这个目录导入编码生成和绘制函数，用它生成 `3 x 3` A4 标定板。

## 推荐使用顺序

1. 激活环境：

```powershell
conda activate db_cam_env
```

2. 打印标定板：

```text
cct14_3x3_A4_60mm.pdf
```

3. 采集左右图：

```powershell
python stereo_camera.py
```

4. 拍摄 15 到 25 组不同角度、不同距离的双目图片。

5. 执行双目标定：

```powershell
python stereo_calibrate_cct14.py
```

6. 检查输出：

```text
stereo_cct14.yaml
calibration_debug/
```

## 标定结果文件

运行 `stereo_calibrate_cct14.py` 后会生成：

```text
stereo_cct14.yaml
```

该文件通常包含：

- 左相机内参矩阵。
- 右相机内参矩阵。
- 左右相机畸变系数。
- 双目旋转矩阵 `R`。
- 双目平移向量 `T`。
- 本质矩阵 `E`。
- 基础矩阵 `F`。
- 双目校正矩阵。
- 重投影矩阵 `Q`。

后续如果要做视差图、深度图或三维重建，就会继续使用这个 YAML 文件。
