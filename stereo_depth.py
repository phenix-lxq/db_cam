import argparse
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from stereo_camera import open_camera, read_dual, read_side_by_side


def parse_args():
    parser = argparse.ArgumentParser(description="USB 双目相机深度查看器")
    parser.add_argument("--calibration", type=Path, default=Path("stereo_cct14.yaml"), help="双目标定 YAML")
    parser.add_argument("--mode", choices=("sbs", "dual"), default="sbs", help="sbs: 左右拼接相机；dual: 两个独立摄像头")
    parser.add_argument("--camera", type=int, default=1, help="sbs 模式的相机编号")
    parser.add_argument("--left", type=int, default=0, help="dual 模式的左相机编号")
    parser.add_argument("--right", type=int, default=1, help="dual 模式的右相机编号")
    parser.add_argument("--width", type=int, default=2560, help="sbs 模式整幅宽度")
    parser.add_argument("--height", type=int, default=720, help="相机图像高度")
    parser.add_argument("--fps", type=float, default=30.0, help="目标帧率")
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf"), default="dshow", help="Windows 视频后端")
    parser.add_argument("--left-image", type=Path, help="用已有左图测试")
    parser.add_argument("--right-image", type=Path, help="用已有右图测试")
    parser.add_argument("--min-disparity", type=int, default=0, help="最小视差")
    parser.add_argument("--num-disparities", type=int, default=128, help="视差搜索范围，必须是 16 的倍数")
    parser.add_argument("--block-size", type=int, default=5, help="SGBM 匹配块大小")
    parser.add_argument("--max-depth", type=float, default=2000.0, help="深度显示上限，单位 mm")
    parser.add_argument("--save-prefix", type=Path, help="保存结果文件名前缀")
    parser.add_argument("--no-display", action="store_true", help="只计算不显示")
    return parser.parse_args()


def read_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取图片: {path}")
    return image


def write_image(path, image):
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise RuntimeError(f"无法编码图片: {path}")
    encoded.tofile(path)


def load_calibration(path):
    storage = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    if not storage.isOpened():
        raise RuntimeError(f"无法读取标定文件: {path}")
    try:
        calibration = {
            "image_width": int(storage.getNode("image_width").real()),
            "image_height": int(storage.getNode("image_height").real()),
            "left_camera_matrix": storage.getNode("left_camera_matrix").mat(),
            "left_distortion": storage.getNode("left_distortion").mat(),
            "right_camera_matrix": storage.getNode("right_camera_matrix").mat(),
            "right_distortion": storage.getNode("right_distortion").mat(),
            "left_rectification": storage.getNode("left_rectification").mat(),
            "right_rectification": storage.getNode("right_rectification").mat(),
            "left_projection": storage.getNode("left_projection").mat(),
            "right_projection": storage.getNode("right_projection").mat(),
            "disparity_to_depth": storage.getNode("disparity_to_depth").mat(),
        }
    finally:
        storage.release()

    missing = [key for key, value in calibration.items() if value is None]
    if missing:
        raise RuntimeError(f"标定文件缺少字段: {missing}")
    return calibration


def build_rectify_maps(calibration):
    image_size = (calibration["image_width"], calibration["image_height"])
    left_map_x, left_map_y = cv2.initUndistortRectifyMap(
        calibration["left_camera_matrix"],
        calibration["left_distortion"],
        calibration["left_rectification"],
        calibration["left_projection"],
        image_size,
        cv2.CV_32FC1,
    )
    right_map_x, right_map_y = cv2.initUndistortRectifyMap(
        calibration["right_camera_matrix"],
        calibration["right_distortion"],
        calibration["right_rectification"],
        calibration["right_projection"],
        image_size,
        cv2.CV_32FC1,
    )
    return (left_map_x, left_map_y), (right_map_x, right_map_y)


def create_matcher(args):
    num_disparities = max(16, int(np.ceil(args.num_disparities / 16)) * 16)
    block_size = args.block_size if args.block_size % 2 else args.block_size + 1
    block_size = max(3, block_size)
    return cv2.StereoSGBM_create(
        minDisparity=args.min_disparity,
        numDisparities=num_disparities,
        blockSize=block_size,
        P1=8 * block_size * block_size,
        P2=32 * block_size * block_size,
        disp12MaxDiff=1,
        uniquenessRatio=8,
        speckleWindowSize=80,
        speckleRange=2,
        preFilterCap=31,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )


def rectify_pair(left_frame, right_frame, left_maps, right_maps):
    left_rectified = cv2.remap(left_frame, left_maps[0], left_maps[1], cv2.INTER_LINEAR)
    right_rectified = cv2.remap(right_frame, right_maps[0], right_maps[1], cv2.INTER_LINEAR)
    return left_rectified, right_rectified


def ensure_image_size(left_frame, right_frame, calibration):
    expected_size = (calibration["image_height"], calibration["image_width"])
    if left_frame.shape[:2] != expected_size or right_frame.shape[:2] != expected_size:
        raise RuntimeError(
            f"输入图像尺寸必须和标定一致：{expected_size[1]}x{expected_size[0]}"
        )


def compute_depth(left_rectified, right_rectified, matcher, q_matrix, max_depth):
    left_gray = cv2.cvtColor(left_rectified, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_rectified, cv2.COLOR_BGR2GRAY)
    left_gray = cv2.equalizeHist(left_gray)
    right_gray = cv2.equalizeHist(right_gray)

    disparity = matcher.compute(left_gray, right_gray).astype(np.float32) / 16.0
    points_3d = cv2.reprojectImageTo3D(disparity, q_matrix)
    depth = points_3d[:, :, 2]
    valid = np.isfinite(depth) & (disparity > 0) & (depth > 0) & (depth < max_depth)

    depth_for_display = np.zeros(depth.shape, dtype=np.uint8)
    depth_for_display[valid] = np.clip(255.0 * (1.0 - depth[valid] / max_depth), 0, 255).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_for_display, cv2.COLORMAP_JET)
    depth_color[~valid] = 0
    return disparity, depth, depth_color, valid, points_3d


def make_gray_bgr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def render_point_cloud(points_3d, rgb_image, valid, step=4):
    height, width = rgb_image.shape[:2]
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    sample = np.zeros_like(valid, dtype=bool)
    sample[::step, ::step] = valid[::step, ::step]
    ys, xs = np.where(sample)
    if xs.size == 0:
        cv2.putText(canvas, "POINT CLOUD: no valid points", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
        return canvas

    pts = points_3d[ys, xs].astype(np.float32)
    colors = rgb_image[ys, xs]
    finite = np.isfinite(pts).all(axis=1)
    pts = pts[finite]
    colors = colors[finite]
    if pts.size == 0:
        cv2.putText(canvas, "POINT CLOUD: no finite points", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
        return canvas

    x = pts[:, 0]
    y = pts[:, 1]
    z = pts[:, 2]

    yaw = np.deg2rad(-35.0)
    pitch = np.deg2rad(20.0)
    x1 = x * np.cos(yaw) - z * np.sin(yaw)
    z1 = x * np.sin(yaw) + z * np.cos(yaw)
    y1 = y * np.cos(pitch) - z1 * np.sin(pitch)

    proj = np.stack((x1, -y1), axis=1)
    mins = np.percentile(proj, 2, axis=0)
    maxs = np.percentile(proj, 98, axis=0)
    spans = np.maximum(maxs - mins, 1e-6)
    norm = (proj - mins) / spans
    px = np.clip((norm[:, 0] * (width - 1)).astype(np.int32), 0, width - 1)
    py = np.clip((norm[:, 1] * (height - 1)).astype(np.int32), 0, height - 1)

    order = np.argsort(z)
    for idx in order:
        cv2.circle(canvas, (int(px[idx]), int(py[idx])), 1, tuple(int(c) for c in colors[idx]), -1)

    cv2.putText(canvas, "POINT CLOUD", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return canvas


def make_quad_canvas(color_image, gray_image, depth_color, point_cloud):
    height, width = color_image.shape[:2]
    canvas = np.full((height * 2 + 80, width * 2 + 260, 3), 255, dtype=np.uint8)

    def paste(image, x, y):
        canvas[y : y + height, x : x + width] = image

    paste(color_image, 60, 60)
    paste(gray_image, 60, height + 120)
    paste(depth_color, width + 100, 60)
    paste(point_cloud, width + 100, height + 120)

    labels = [
        ("彩色", 60 + width // 2 - 40, 35),
        ("黑白", 60 + width // 2 - 40, height + 95),
        ("深度", width + 100 + width // 2 - 40, 35),
        ("点云", width + 100 + width // 2 - 40, height + 95),
    ]
    for text, x, y in labels:
        cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)

    cv2.rectangle(canvas, (60, 60), (60 + width, 60 + height), (0, 0, 0), 2)
    cv2.rectangle(canvas, (60, height + 120), (60 + width, height + 120 + height), (0, 0, 0), 2)
    cv2.rectangle(canvas, (width + 100, 60), (width + 100 + width, 60 + height), (0, 0, 0), 2)
    cv2.rectangle(canvas, (width + 100, height + 120), (width + 100 + width, height + 120 + height), (0, 0, 0), 2)
    return canvas


def save_image(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_image(path, image)


def timestamp_prefix(base_dir=Path("depth_outputs")):
    return base_dir / f"depth_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"


def qimage_from_bgr(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width, channels = rgb.shape
    return QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()


class ImagePane(QWidget):
    def __init__(self, title):
        super().__init__()
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 22px;")
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(320, 220)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setStyleSheet("background: white; border: 3px solid #0b2239;")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)
        self.setLayout(layout)

    def set_image(self, image):
        pixmap = QPixmap.fromImage(qimage_from_bgr(image))
        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def clear(self, text="关闭"):
        placeholder = np.full((360, 480, 3), 245, dtype=np.uint8)
        cv2.putText(placeholder, text, (160, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        self.set_image(placeholder)


class StereoDepthWindow(QMainWindow):
    def __init__(self, args, calibration, left_maps, right_maps, matcher):
        super().__init__()
        self.args = args
        self.calibration = calibration
        self.left_maps = left_maps
        self.right_maps = right_maps
        self.matcher = matcher
        self.captures = []
        self.read_frames = None
        self.left_frame = None
        self.right_frame = None
        self.left_rectified = None
        self.right_rectified = None
        self.depth = None
        self.valid = None
        self.depth_color = None
        self.points_3d = None
        self.gray_image = None
        self.point_cloud = None
        self.show_color = True
        self.show_gray = True
        self.show_depth = True
        self.show_point = True

        self.setWindowTitle("双目深度查看器")
        self.resize(1600, 950)

        self.color_pane = ImagePane("彩色")
        self.gray_pane = ImagePane("黑白")
        self.depth_pane = ImagePane("深度")
        self.point_pane = ImagePane("点云")

        placeholder = np.full((360, 480, 3), 245, dtype=np.uint8)
        for pane in (self.color_pane, self.gray_pane, self.depth_pane, self.point_pane):
            pane.set_image(placeholder)

        left_grid = QGridLayout()
        left_grid.setSpacing(12)
        left_grid.addWidget(self.color_pane, 0, 0)
        left_grid.addWidget(self.gray_pane, 0, 1)
        left_grid.addWidget(self.depth_pane, 1, 0)
        left_grid.addWidget(self.point_pane, 1, 1)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(16)
        right_panel.addWidget(self.make_control_group("彩色", self.toggle_color, self.save_color))
        right_panel.addWidget(self.make_control_group("黑白", self.toggle_gray, self.save_gray))
        right_panel.addWidget(self.make_control_group("深度", self.toggle_depth, self.save_depth))
        right_panel.addWidget(self.make_control_group("点云", self.toggle_point, self.save_point))
        right_panel.addStretch(1)

        root = QHBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(18)
        root.addLayout(left_grid, 4)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setFixedWidth(250)
        root.addWidget(right_widget, 1)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        self.statusBar().showMessage("准备打开相机...")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(max(1, round(1000 / self.args.fps)))
        self.start_camera()

    def make_control_group(self, title, toggle_fn, save_fn):
        box = QGroupBox(title)
        layout = QVBoxLayout()
        open_btn = QPushButton(f"打开{title}")
        close_btn = QPushButton(f"关闭{title}")
        save_btn = QPushButton(f"保存{title}图")
        for btn in (open_btn, close_btn, save_btn):
            btn.setMinimumHeight(42)
        open_btn.clicked.connect(lambda: toggle_fn(True))
        close_btn.clicked.connect(lambda: toggle_fn(False))
        save_btn.clicked.connect(save_fn)
        layout.addWidget(open_btn)
        layout.addWidget(close_btn)
        layout.addWidget(save_btn)
        box.setLayout(layout)
        return box

    def start_camera(self):
        try:
            if self.args.mode == "sbs":
                capture = open_camera(self.args.camera, self.args.backend, self.args.width, self.args.height, self.args.fps)
                self.captures = [capture]
                self.read_frames = lambda: read_side_by_side(capture)
            else:
                left_capture = open_camera(self.args.left, self.args.backend, self.args.width, self.args.height, self.args.fps)
                right_capture = open_camera(self.args.right, self.args.backend, self.args.width, self.args.height, self.args.fps)
                self.captures = [left_capture, right_capture]
                self.read_frames = lambda: read_dual(left_capture, right_capture)
        except RuntimeError as error:
            QMessageBox.critical(self, "相机打开失败", str(error))
            self.close()
            return
        self.statusBar().showMessage("相机已打开")

    def update_frame(self):
        if self.read_frames is None:
            return
        try:
            left_frame, right_frame = self.read_frames()
        except RuntimeError as error:
            self.statusBar().showMessage(f"读取失败: {error}")
            return

        try:
            ensure_image_size(left_frame, right_frame, self.calibration)
        except RuntimeError as error:
            self.statusBar().showMessage(str(error))
            return

        left_rectified, right_rectified = rectify_pair(left_frame, right_frame, self.left_maps, self.right_maps)
        disparity, depth, depth_color, valid, points_3d = compute_depth(
            left_rectified,
            right_rectified,
            self.matcher,
            self.calibration["disparity_to_depth"],
            self.args.max_depth,
        )
        self.left_rectified = left_rectified
        self.right_rectified = right_rectified
        self.depth = depth
        self.valid = valid
        self.depth_color = depth_color
        self.points_3d = points_3d
        self.gray_image = make_gray_bgr(left_rectified)
        self.point_cloud = render_point_cloud(points_3d, left_rectified, valid)

        self.refresh_views()

    def refresh_views(self):
        if self.left_rectified is None:
            return
        self.color_pane.set_image(self.left_rectified if self.show_color else np.full((360, 480, 3), 245, dtype=np.uint8))
        self.gray_pane.set_image(self.gray_image if self.show_gray else np.full((360, 480, 3), 245, dtype=np.uint8))
        self.depth_pane.set_image(self.depth_color if self.show_depth else np.full((360, 480, 3), 245, dtype=np.uint8))
        self.point_pane.set_image(self.point_cloud if self.show_point else np.full((360, 480, 3), 245, dtype=np.uint8))

    def toggle_color(self, enabled):
        self.show_color = enabled
        self.refresh_views()

    def toggle_gray(self, enabled):
        self.show_gray = enabled
        self.refresh_views()

    def toggle_depth(self, enabled):
        self.show_depth = enabled
        self.refresh_views()

    def toggle_point(self, enabled):
        self.show_point = enabled
        self.refresh_views()

    def save_color(self):
        if self.left_rectified is not None:
            self.save_current(self.left_rectified, "color")

    def save_gray(self):
        if self.gray_image is not None:
            self.save_current(self.gray_image, "gray")

    def save_depth(self):
        if self.depth_color is not None:
            self.save_current(self.depth_color, "depth")

    def save_point(self):
        if self.point_cloud is not None:
            self.save_current(self.point_cloud, "point_cloud")

    def save_current(self, image, tag):
        prefix = self.args.save_prefix or timestamp_prefix()
        path = prefix.parent / f"{prefix.name}_{tag}.png"
        save_image(path, image)
        self.statusBar().showMessage(f"已保存: {path.name}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()
        elif event.key() == Qt.Key.Key_S:
            self.save_color()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        for capture in self.captures:
            capture.release()
        event.accept()


def run_once(args, calibration, left_maps, right_maps, matcher):
    if not args.left_image or not args.right_image:
        raise RuntimeError("测试模式需要同时提供 --left-image 和 --right-image")

    left_frame = read_image(args.left_image)
    right_frame = read_image(args.right_image)
    ensure_image_size(left_frame, right_frame, calibration)
    left_rectified, right_rectified = rectify_pair(left_frame, right_frame, left_maps, right_maps)
    disparity, depth, depth_color, valid, points_3d = compute_depth(
        left_rectified,
        right_rectified,
        matcher,
        calibration["disparity_to_depth"],
        args.max_depth,
    )

    if args.save_prefix:
        prefix = args.save_prefix
        save_image(prefix.parent / f"{prefix.name}_color.png", left_rectified)
        save_image(prefix.parent / f"{prefix.name}_gray.png", make_gray_bgr(left_rectified))
        save_image(prefix.parent / f"{prefix.name}_depth.png", depth_color)
        save_image(prefix.parent / f"{prefix.name}_point_cloud.png", render_point_cloud(points_3d, left_rectified, valid))

    valid_depth = depth[valid]
    if valid_depth.size:
        print(f"有效深度点: {100.0 * valid_depth.size / depth.size:.2f}%")
        print(f"中位深度: {np.median(valid_depth):.1f} mm")
    else:
        print("有效深度点: 0.00%")

    if not args.no_display:
        app = QApplication.instance() or QApplication([])
        window = QMainWindow()
        window.setWindowTitle("双目深度查看器 - 单次测试")
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(QPixmap.fromImage(qimage_from_bgr(make_quad_canvas(
            left_rectified,
            make_gray_bgr(left_rectified),
            depth_color,
            render_point_cloud(points_3d, left_rectified, valid),
        ))))
        window.setCentralWidget(label)
        window.resize(1600, 950)
        window.show()
        app.exec()


def run(args):
    calibration = load_calibration(args.calibration)
    left_maps, right_maps = build_rectify_maps(calibration)
    matcher = create_matcher(args)

    if args.left_image and args.right_image:
        run_once(args, calibration, left_maps, right_maps, matcher)
        return

    app = QApplication.instance() or QApplication([])
    window = StereoDepthWindow(args, calibration, left_maps, right_maps, matcher)
    window.show()
    app.exec()


def main():
    args = parse_args()
    try:
        run(args)
    except RuntimeError as error:
        raise SystemExit(f"错误: {error}") from error


if __name__ == "__main__":
    main()
