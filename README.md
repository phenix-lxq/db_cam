# USB 双目相机采集

激活环境：

```powershell
conda activate db_cam_env
```

先探测可用相机编号：

```powershell
python stereo_camera.py --list
```

本机已探测到编号 `1` 是左右拼接双目相机。下面的命令会使用相机原始分辨率显示：

```powershell
python stereo_camera.py --mode sbs --camera 1
```

如果需要指定分辨率，可再追加例如 `--width 2560 --height 720`。

如果左右镜头在系统中显示为两个独立摄像头：

```powershell
python stereo_camera.py --mode dual --left 0 --right 1 --width 1280 --height 720
```

窗口中点击“拍照”按钮或按 `S`，可同时保存左右原始图片到 `captures`；
按 `Q`、`Esc` 或关闭窗口退出。
若相机无法打开，可追加 `--backend msmf`。实际支持的分辨率取决于相机型号。

## 14-bit CCT 双目标定板

直接打印 `cct14_3x3_A4_60mm.pdf`。该文件使用
`14-Bit-Circular-Coded-Target-master/create_target_sheets.py` 的黑底白码定义。
打印设置必须选择“实际大小”或 `100%`，
关闭“适合页面”；打印后确认相邻编码点圆心间距为 60 mm。

标定板包含 3×3 个编码点，编码外径 40 mm，水平和垂直圆心间距均为 60 mm。
拍摄标定照片后运行：

```powershell
python stereo_calibrate_cct14.py
```

详细说明见 `CCT14_STEREO_CALIBRATION.md`。
