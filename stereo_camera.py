import argparse
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


BACKENDS = {
    "auto": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
}


def parse_args():
    parser = argparse.ArgumentParser(description="USB 双目相机预览和左右图采集")
    parser.add_argument(
        "--mode",
        choices=("sbs", "dual"),
        default="sbs",
        help="sbs: 单设备左右拼接；dual: 两个独立摄像头",
    )
    parser.add_argument("--camera", type=int, default=1, help="sbs 模式的相机编号")
    parser.add_argument("--left", type=int, default=0, help="dual 模式的左相机编号")
    parser.add_argument("--right", type=int, default=1, help="dual 模式的右相机编号")
    parser.add_argument("--width", type=int, default=2560, help="相机输出宽度")
    parser.add_argument("--height", type=int, default=720, help="相机输出高度")
    parser.add_argument("--fps", type=float, default=30.0, help="目标帧率")
    parser.add_argument("--backend", choices=BACKENDS, default="dshow", help="Windows 视频后端")
    parser.add_argument("--output", type=Path, default=Path("captures"), help="截图保存目录")
    parser.add_argument("--list", action="store_true", help="探测相机编号后退出")
    return parser.parse_args()


def open_camera(index, backend, width, height, fps):
    """打开摄像头，并尽量在构造阶段就设置好 MJPG、分辨率和帧率。"""
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    parameters = [
        int(cv2.CAP_PROP_FOURCC),
        int(fourcc),
        int(cv2.CAP_PROP_FPS),
        round(fps),
    ]
    if width is not None:
        parameters.extend((int(cv2.CAP_PROP_FRAME_WIDTH), int(width)))
    if height is not None:
        parameters.extend((int(cv2.CAP_PROP_FRAME_HEIGHT), int(height)))

    # 部分 OpenCV 版本不支持第三个 params 参数，所以失败后退回 set() 方式。
    try:
        capture = cv2.VideoCapture(index, BACKENDS[backend], parameters)
    except cv2.error:
        capture = None

    if capture is None or not capture.isOpened():
        if capture is not None:
            capture.release()
        capture = cv2.VideoCapture(index, BACKENDS[backend])
        capture.set(cv2.CAP_PROP_FOURCC, fourcc)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, fps)

    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"无法打开相机 {index}")
    return capture


def list_cameras(backend, max_index=10):
    print("正在探测相机，请稍候...")
    found = []
    for index in range(max_index):
        capture = cv2.VideoCapture(index, BACKENDS[backend])
        if capture.isOpened():
            ok, frame = capture.read()
            if ok:
                height, width = frame.shape[:2]
                found.append(index)
                print(f"相机 {index}: {width} x {height}")
        capture.release()

    if not found:
        print("未发现可用相机。请检查 USB 连接，或尝试 --backend msmf")


def read_side_by_side(capture):
    """读取左右拼接画面，并从中间切成左图和右图。"""
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError("读取相机画面失败")

    width = frame.shape[1]
    if width < 2 or width % 2:
        raise RuntimeError(f"拼接画面宽度必须为偶数，当前为 {width}")

    middle = width // 2
    return frame[:, :middle], frame[:, middle:]


def read_dual(left_capture, right_capture):
    """尽量同步地读取两个独立 USB 摄像头。"""
    if not left_capture.grab() or not right_capture.grab():
        raise RuntimeError("抓取双相机画面失败")
    left_ok, left_frame = left_capture.retrieve()
    right_ok, right_frame = right_capture.retrieve()
    if not left_ok or not right_ok:
        raise RuntimeError("读取双相机画面失败")
    return left_frame, right_frame


def make_preview(left_frame, right_frame):
    """生成窗口中显示的左右并排预览图，不在中间额外画分割线。"""
    target_height = max(left_frame.shape[0], right_frame.shape[0])
    if left_frame.shape[0] < target_height:
        bottom = target_height - left_frame.shape[0]
        left_frame = cv2.copyMakeBorder(left_frame, 0, bottom, 0, 0, cv2.BORDER_CONSTANT)
    if right_frame.shape[0] < target_height:
        bottom = target_height - right_frame.shape[0]
        right_frame = cv2.copyMakeBorder(right_frame, 0, bottom, 0, 0, cv2.BORDER_CONSTANT)

    preview = np.hstack((left_frame, right_frame))
    middle = left_frame.shape[1]
    cv2.putText(preview, "LEFT", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(preview, "RIGHT", (middle + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
    return preview


def write_image(path, image):
    """使用 imencode + tofile 保存，避免中文路径下 cv2.imwrite 失败。"""
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise RuntimeError(f"编码图片失败: {path}")
    encoded.tofile(path)


def save_pair(output_dir, left_frame, right_frame):
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    left_path = output_dir / f"left_{timestamp}.png"
    right_path = output_dir / f"right_{timestamp}.png"
    write_image(left_path, left_frame)
    write_image(right_path, right_frame)
    print(f"已保存: {left_path} 和 {right_path}")
    return left_path, right_path


class StereoCameraWindow(QMainWindow):
    """双目相机采集窗口。"""

    def __init__(self, read_frames, output_dir, fps):
        super().__init__()
        self.read_frames = read_frames
        self.output_dir = output_dir
        self.left_frame = None
        self.right_frame = None
        self.preview_pixmap = None

        self.setWindowTitle("USB 双目相机")
        self.resize(1280, 480)
        self.setMinimumSize(720, 320)

        self.preview_label = QLabel("正在打开相机...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setStyleSheet("background: #111; color: #ddd;")

        self.capture_button = QPushButton("拍照")
        self.capture_button.setEnabled(False)
        self.capture_button.setMinimumHeight(48)
        self.capture_button.setStyleSheet(
            "QPushButton { font-size: 20px; font-weight: bold; "
            "background: #1677ff; color: white; border-radius: 6px; }"
            "QPushButton:hover { background: #4096ff; }"
            "QPushButton:pressed { background: #0958d9; }"
            "QPushButton:disabled { background: #777; }"
        )
        self.capture_button.clicked.connect(self.capture_photo)

        self.status_label = QLabel("等待相机画面...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(self.preview_label, 1)
        layout.addWidget(self.capture_button)
        layout.addWidget(self.status_label)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(max(1, round(1000 / fps)))

    def update_frame(self):
        try:
            self.left_frame, self.right_frame = self.read_frames()
        except RuntimeError as error:
            self.timer.stop()
            QMessageBox.critical(self, "相机错误", str(error))
            self.close()
            return

        preview = make_preview(self.left_frame, self.right_frame)
        rgb_preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb_preview.shape
        image = QImage(
            rgb_preview.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        self.preview_pixmap = QPixmap.fromImage(image)
        self.update_preview_size()
        self.capture_button.setEnabled(True)

        if self.status_label.text() == "等待相机画面...":
            self.status_label.setText(f"双目画面: {width} x {height}，点击“拍照”保存标定图片")

    def update_preview_size(self):
        if self.preview_pixmap is None:
            return
        scaled_pixmap = self.preview_pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled_pixmap)

    def capture_photo(self):
        if self.left_frame is None or self.right_frame is None:
            return
        try:
            left_path, right_path = save_pair(self.output_dir, self.left_frame, self.right_frame)
        except RuntimeError as error:
            QMessageBox.critical(self, "保存失败", str(error))
            return
        self.status_label.setText(f"拍照成功: {left_path.name} / {right_path.name}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview_size()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_S:
            self.capture_photo()
        elif event.key() in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


def run(args):
    if args.list:
        list_cameras(args.backend)
        return

    captures = []
    try:
        if args.mode == "sbs":
            capture = open_camera(args.camera, args.backend, args.width, args.height, args.fps)
            captures.append(capture)
            read_frames = lambda: read_side_by_side(capture)
        else:
            left_capture = open_camera(args.left, args.backend, args.width, args.height, args.fps)
            right_capture = open_camera(args.right, args.backend, args.width, args.height, args.fps)
            captures.extend((left_capture, right_capture))
            read_frames = lambda: read_dual(left_capture, right_capture)

        print("相机已打开。点击“拍照”或按 S 保存，按 Q 或 Esc 退出。")
        application = QApplication.instance() or QApplication([])
        window = StereoCameraWindow(read_frames, args.output, args.fps)
        window.show()
        application.exec()
    finally:
        for capture in captures:
            capture.release()


def main():
    args = parse_args()
    try:
        run(args)
    except RuntimeError as error:
        raise SystemExit(f"错误: {error}") from error


if __name__ == "__main__":
    main()
