# db_cam 双目相机标定项目

这个项目用于 USB 双目相机采集、14-bit 环形编码点标定板生成，以及基于编码点的双目标定。

## 环境

```powershell
conda activate db_cam_env
```

## 采集双目图片

先查看相机编号：

```powershell
python stereo_camera.py --list
```

当前项目默认使用左右拼接双目相机：

```powershell
python stereo_camera.py --mode sbs --camera 1 --width 2560 --height 720
```

其中整幅画面是 `2560 x 720`，左右相机各 `1280 x 720`。

打开窗口后：

- 点击“拍照”或按 `S` 保存左右图。
- 按 `Q`、`Esc` 或关闭窗口退出。
- 图片保存到 `captures/`。

## 标定板

打印文件：

```text
cct14_3x3_A4_60mm.pdf
```

参数：

- A4 竖版，`210 mm x 297 mm`
- 3 x 3 个 14-bit 环形编码点
- 编码点外径 `40 mm`
- 相邻编码点圆心间距 `60 mm`
- 黑色背景区域为 `200 mm x 200 mm` 正方形
- 黑底白色编码点

打印时请选择 `100%` 或“实际大小”，关闭“适合页面”。打印后直接测量相邻编码点圆心间距，应为 `60 mm`。

重新生成标定板：

```powershell
python generate_cct14_a4_board.py
```

## 双目标定

拍摄 15 到 25 对标定图片后运行：

```powershell
python stereo_calibrate_cct14.py
```

输出：

- `stereo_cct14.yaml`：双目标定结果
- `calibration_debug/`：带解码 ID 标注的检查图

如果现场误检较多，可以调高候选约束：

```powershell
python stereo_calibrate_cct14.py --threshold 0.9 --min-iou 0.75 --min-ring-transitions 6
```

更详细的流程见 `CCT14_STEREO_CALIBRATION.md`，项目结构见 `PROJECT_STRUCTURE.md`。
