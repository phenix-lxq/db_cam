import argparse
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from stereo_camera import open_camera, read_dual, read_side_by_side


def parse_args():
    parser = argparse.ArgumentParser(description="双目相机实时深度检测")
    parser.add_argument("--calibration", type=Path, default=Path("stereo_cct14.yaml"), help="双目标定 YAML")
    parser.add_argument("--mode", choices=("sbs", "dual"), default="sbs", help="sbs: 左右拼接相机；dual: 两个独立相机")
    parser.add_argument("--camera", type=int, default=1, help="sbs 模式的相机编号")
    parser.add_argument("--left", type=int, default=0, help="dual 模式的左相机编号")
    parser.add_argument("--right", type=int, default=1, help="dual 模式的右相机编号")
    parser.add_argument("--width", type=int, default=2560, help="sbs 模式整幅图宽度")
    parser.add_argument("--height", type=int, default=720, help="相机图像高度")
    parser.add_argument("--fps", type=float, default=30.0, help="目标帧率")
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf"), default="dshow", help="Windows 视频后端")
    parser.add_argument("--left-image", type=Path, help="用已有左图测试")
    parser.add_argument("--right-image", type=Path, help="用已有右图测试")
    parser.add_argument("--min-disparity", type=int, default=0, help="最小视差")
    parser.add_argument("--num-disparities", type=int, default=128, help="视差搜索范围，必须是 16 的倍数")
    parser.add_argument("--block-size", type=int, default=5, help="SGBM 匹配块大小，建议 3/5/7")
    parser.add_argument("--max-depth", type=float, default=2000.0, help="显示深度上限，单位 mm")
    parser.add_argument("--save-prefix", type=Path, help="保存一次结果的文件名前缀")
    parser.add_argument("--no-display", action="store_true", help="只计算不打开窗口，适合脚本验证")
    parser.add_argument("--display-scale", type=float, default=0.5, help="窗口显示缩放比例，默认 0.5")
    return parser.parse_args()


def read_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取图片: {path}")
    return image


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
    channels = 1
    left_matcher = cv2.StereoSGBM_create(
        minDisparity=args.min_disparity,
        numDisparities=num_disparities,
        blockSize=block_size,
        P1=8 * channels * block_size * block_size,
        P2=32 * channels * block_size * block_size,
        disp12MaxDiff=1,
        uniquenessRatio=8,
        speckleWindowSize=80,
        speckleRange=2,
        preFilterCap=31,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    return left_matcher


def rectify_pair(left_frame, right_frame, left_maps, right_maps):
    left_rectified = cv2.remap(left_frame, left_maps[0], left_maps[1], cv2.INTER_LINEAR)
    right_rectified = cv2.remap(right_frame, right_maps[0], right_maps[1], cv2.INTER_LINEAR)
    return left_rectified, right_rectified


def ensure_image_size(left_frame, right_frame, calibration):
    expected_size = (calibration["image_height"], calibration["image_width"])
    left_size = left_frame.shape[:2]
    right_size = right_frame.shape[:2]
    if left_size != expected_size or right_size != expected_size:
        raise RuntimeError(
            "输入图像尺寸必须和标定文件一致。"
            f"标定尺寸: {expected_size[1]}x{expected_size[0]}，"
            f"左图: {left_size[1]}x{left_size[0]}，右图: {right_size[1]}x{right_size[0]}"
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
    return disparity, depth, depth_color, valid


def print_depth_stats(depth, valid):
    valid_depth = depth[valid]
    valid_ratio = 100.0 * valid_depth.size / depth.size
    if valid_depth.size == 0:
        print("有效深度点: 0.00%，当前参数下没有可靠深度")
        return
    print(
        "有效深度点: "
        f"{valid_ratio:.2f}% | "
        f"中位深度: {np.median(valid_depth):.1f} mm | "
        f"范围: {np.percentile(valid_depth, 5):.1f} ~ {np.percentile(valid_depth, 95):.1f} mm"
    )


def make_depth_rgb_view(depth_color, rgb_image, depth, valid, cursor):
    """把深度图和 RGB 图拼到同一个窗口：左边深度，右边 RGB。"""
    depth_width = depth_color.shape[1]
    output = np.hstack((depth_color, rgb_image.copy()))

    cv2.putText(output, "DEPTH", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(output, "RGB", (depth_width + 20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA)

    if cursor is not None:
        x, y = cursor
        if 0 <= y < depth.shape[0] and 0 <= x < depth_width:
            if valid[y, x]:
                text = f"Depth: {depth[y, x]:.1f} mm"
            else:
                text = "Depth: invalid"
            cv2.circle(output, (x, y), 5, (0, 255, 255), 2)
            cv2.putText(output, text, (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)

    cv2.putText(output, "S: save  Q/Esc: quit", (20, output.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    return output


def resize_for_display(image, scale):
    """只缩放窗口显示，不改变保存结果的原始分辨率。"""
    scale = float(scale)
    if scale <= 0:
        scale = 1.0
    if abs(scale - 1.0) < 1e-6:
        return image
    width = max(1, int(round(image.shape[1] * scale)))
    height = max(1, int(round(image.shape[0] * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(image, (width, height), interpolation=interpolation)


def display_to_image_point(x, y, scale):
    """把缩放后窗口中的鼠标坐标换算回原始深度图坐标。"""
    scale = float(scale)
    if scale <= 0:
        scale = 1.0
    return int(round(x / scale)), int(round(y / scale))


def save_outputs(prefix, left_rectified, right_rectified, disparity, depth_color):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    write_image(prefix.with_name(prefix.name + "_left_rectified.png"), left_rectified)
    write_image(prefix.with_name(prefix.name + "_right_rectified.png"), right_rectified)
    disparity_vis = cv2.normalize(disparity, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    write_image(prefix.with_name(prefix.name + "_disparity.png"), disparity_vis)
    write_image(prefix.with_name(prefix.name + "_depth.png"), depth_color)
    print(f"已保存深度结果: {prefix}_*.png")


def write_image(path, image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"无法编码图片: {path}")
    encoded.tofile(path)


def timestamp_prefix(base_dir=Path("depth_outputs")):
    return base_dir / f"depth_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"


def run_once(args, calibration, left_maps, right_maps, matcher):
    if not args.left_image or not args.right_image:
        raise RuntimeError("使用图片测试时必须同时提供 --left-image 和 --right-image")
    left_frame = read_image(args.left_image)
    right_frame = read_image(args.right_image)
    ensure_image_size(left_frame, right_frame, calibration)
    left_rectified, right_rectified = rectify_pair(left_frame, right_frame, left_maps, right_maps)
    disparity, depth, depth_color, valid = compute_depth(
        left_rectified,
        right_rectified,
        matcher,
        calibration["disparity_to_depth"],
        args.max_depth,
    )
    if args.save_prefix:
        save_outputs(args.save_prefix, left_rectified, right_rectified, disparity, depth_color)
    print_depth_stats(depth, valid)
    if not args.no_display:
        view = make_depth_rgb_view(depth_color, left_rectified, depth, valid, None)
        cv2.imshow("depth + rgb", resize_for_display(view, args.display_scale))
        cv2.waitKey(0)


def run_live(args, calibration, left_maps, right_maps, matcher):
    captures = []
    cursor = {"point": None}

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_MOUSEMOVE:
            cursor["point"] = display_to_image_point(x, y, args.display_scale)

    window_name = "depth + rgb"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

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

        print("深度检测已启动。鼠标移动查看深度，按 S 保存结果，按 Q 或 Esc 退出。")
        last_outputs = None
        while True:
            left_frame, right_frame = read_frames()
            ensure_image_size(left_frame, right_frame, calibration)
            left_rectified, right_rectified = rectify_pair(left_frame, right_frame, left_maps, right_maps)
            disparity, depth, depth_color, valid = compute_depth(
                left_rectified,
                right_rectified,
                matcher,
                calibration["disparity_to_depth"],
                args.max_depth,
            )
            view = make_depth_rgb_view(depth_color, left_rectified, depth, valid, cursor["point"])
            cv2.imshow(window_name, resize_for_display(view, args.display_scale))
            last_outputs = (left_rectified, right_rectified, disparity, depth_color)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s") and last_outputs is not None:
                prefix = args.save_prefix or timestamp_prefix()
                save_outputs(prefix, *last_outputs)
    finally:
        for capture in captures:
            capture.release()
        cv2.destroyAllWindows()


def main():
    args = parse_args()
    calibration = load_calibration(args.calibration)
    left_maps, right_maps = build_rectify_maps(calibration)
    matcher = create_matcher(args)

    if args.left_image or args.right_image:
        run_once(args, calibration, left_maps, right_maps, matcher)
    else:
        run_live(args, calibration, left_maps, right_maps, matcher)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, cv2.error) as error:
        raise SystemExit(f"错误: {error}") from error
