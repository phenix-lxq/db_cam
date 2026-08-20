# 14-bit 环形编码点双目标定

## 1. 准备标定板布局

项目已使用 `14-Bit-Circular-Coded-Target-master` 的 `generate_codes()` 和
`add_target()` 生成 `cct14_3x3_A4_60mm.pdf`。它采用该仓库原生的黑底白码样式，
其中包含 3×3 个 14-bit 编码点：

- 编码点外径：40 mm。
- 水平圆心间距：60 mm。
- 垂直圆心间距：60 mm。
- 九点圆心区域：120×120 mm。
- 物理坐标已写入 `cct14_layout.csv`。

打印时必须选择“实际大小”或“100%”，关闭“适合页面/缩放页面”。打印后用尺子
测量相邻编码点圆心间距，它应为 60 mm。建议将纸张平整粘贴在玻璃、亚克力板
或其他不会弯曲的平板上。若打印机造成尺寸变化，应测量实际圆心距离并修改
`cct14_layout.csv`，不能继续使用名义尺寸。

需要重新生成 PDF 时运行：

```powershell
python generate_cct14_a4_board.py
```

## 2. 拍摄照片

运行双目采集界面：

```powershell
conda activate db_cam_env
python stereo_camera.py
```

点击“拍照”保存图片。建议拍摄 15–25 对，标定板应覆盖画面中央、四角、近处、
远处，并有不同方向的倾斜。左右图中至少要共同看到 6 个编码点，避免运动模糊、
反光和过曝。标定期间不要改变焦距、分辨率或左右相机位置。

## 3. 执行标定

当前生成的黑底白色编码点直接使用：

```powershell
python stereo_calibrate_cct14.py
```

如果以后改用白底黑色编码点，则使用：

```powershell
python stereo_calibrate_cct14.py --color black
```

默认读取 `captures` 下由采集程序生成的配对图片，输出：

- `stereo_cct14.yaml`：相机内参、畸变、双目 R/T、E/F、校正矩阵和 Q 矩阵。
- `calibration_debug`：标有解码 ID 和检测圆的检查图片。

若漏检较多，可尝试 `--threshold 0.75` 或 `--threshold 0.9`。应逐张查看
`calibration_debug`，确保解码 ID 与标定板真实 ID 一致。
