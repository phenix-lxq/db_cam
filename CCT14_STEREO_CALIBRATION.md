# 14-bit 环形编码点双目标定流程

## 1. 打印标定板

使用当前目录下的：

```text
cct14_3x3_A4_60mm.pdf
```

标定板参数：

- A4 竖版：`210 mm x 297 mm`
- 编码点数量：`3 x 3`
- 编码点外径：`40 mm`
- 相邻圆心间距：横向 `60 mm`，纵向 `60 mm`
- 黑色背景区域：`200 mm x 200 mm` 正方形
- 编码点样式：黑底白码
- 物理坐标文件：`cct14_layout.csv`

打印时必须选择“实际大小”或 `100%`，关闭“适合页面/缩放页面”。打印后测量相邻编码点圆心间距，应为 `60 mm`。如果实际尺寸有偏差，请按实测值修改 `cct14_layout.csv` 中的 `x_mm` 和 `y_mm`。

建议把纸张平整粘贴在玻璃、亚克力板或其他不易弯曲的平板上。

重新生成 PDF：

```powershell
python generate_cct14_a4_board.py
```

## 2. 拍摄标定图片

运行采集程序：

```powershell
conda activate db_cam_env
python stereo_camera.py
```

拍摄建议：

- 拍 15 到 25 对左右图片。
- 标定板覆盖画面中心、四角、近处和远处。
- 每张图里左右相机共同看到至少 6 个编码点。
- 避免运动模糊、反光和过曝。
- 标定期间不要改变焦距、分辨率或左右相机位置。

采集图片会保存为：

```text
captures/left_时间戳.png
captures/right_时间戳.png
```

## 3. 执行标定

默认命令：

```powershell
python stereo_calibrate_cct14.py
```

当前标定板是黑底白码，所以默认参数是：

```text
--color white
```

如果漏检或误检明显，可以调整：

```powershell
python stereo_calibrate_cct14.py --threshold 0.9 --min-iou 0.75 --min-ring-transitions 6
```

输出文件：

- `stereo_cct14.yaml`：左右相机内参、畸变、双目 R/T、E/F、校正矩阵和 Q 矩阵
- `calibration_debug/`：带解码 ID 标注的检查图

标定完成后，先查看 `calibration_debug/`，确认每张图中识别到的 ID 和标定板上的真实点一致。
