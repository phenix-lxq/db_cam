import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parent
CCT_DECODE_DIR = PROJECT_DIR / "CCTDecode" / "CCTDecode"
if str(CCT_DECODE_DIR) not in sys.path:
    sys.path.insert(0, str(CCT_DECODE_DIR))

from CCTDecodeRelease import CCT_extract


@dataclass
class StereoView:
    name: str
    object_points: np.ndarray
    left_points: np.ndarray
    right_points: np.ndarray


def parse_args():
    parser = argparse.ArgumentParser(
        description="使用 14-bit 环形编码点进行双目标定"
    )
    parser.add_argument("--images", type=Path, default=Path("captures"),
                        help="左右标定照片目录")
    parser.add_argument("--layout", type=Path, default=Path("cct14_layout.csv"),
                        help="编码点物理坐标 CSV：id,x_mm,y_mm")
    parser.add_argument("--output", type=Path, default=Path("stereo_cct14.yaml"),
                        help="标定结果文件")
    parser.add_argument("--debug-dir", type=Path,
                        default=Path("calibration_debug"),
                        help="解码标注图保存目录")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="CCT 圆形轮廓阈值，范围 0 到 1")
    parser.add_argument("--min-iou", type=float, default=0.65,
                        help="候选轮廓与拟合椭圆的最小 IoU")
    parser.add_argument("--color", choices=("black", "white"), default="white",
                        help="编码点颜色：black 为白底黑标，white 为黑底白标")
    parser.add_argument("--min-points", type=int, default=6,
                        help="每对照片至少需要的共同编码点数")
    parser.add_argument("--min-views", type=int, default=3,
                        help="至少需要的有效照片对数")
    parser.add_argument("--fix-intrinsics", action="store_true",
                        help="双目标定阶段固定各相机独立内参")
    return parser.parse_args()


def load_layout(path):
    if not path.is_file():
        raise RuntimeError(f"找不到标定板布局文件: {path}")

    layout = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required_columns = {"id", "x_mm", "y_mm"}
        if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
            raise RuntimeError("布局 CSV 必须包含 id,x_mm,y_mm 三列")
        for line_number, row in enumerate(reader, start=2):
            try:
                code_id = int(row["id"])
                point = (float(row["x_mm"]), float(row["y_mm"]), 0.0)
            except (TypeError, ValueError) as error:
                raise RuntimeError(f"布局 CSV 第 {line_number} 行格式错误") from error
            if not 0 <= code_id < 2**14:
                raise RuntimeError(f"布局 CSV 第 {line_number} 行 ID 超出 14-bit 范围")
            if code_id in layout:
                raise RuntimeError(f"布局 CSV 中存在重复 ID: {code_id}")
            layout[code_id] = point
    if len(layout) < 6:
        raise RuntimeError("标定板至少需要 6 个编码点")
    return layout


def find_stereo_pairs(images_dir):
    if not images_dir.is_dir():
        raise RuntimeError(f"找不到照片目录: {images_dir}")

    left_images = {
        path.name.removeprefix("left_"): path
        for path in images_dir.glob("left_*") if path.is_file()
    }
    right_images = {
        path.name.removeprefix("right_"): path
        for path in images_dir.glob("right_*") if path.is_file()
    }
    common_names = sorted(left_images.keys() & right_images.keys())
    if not common_names:
        raise RuntimeError(
            f"{images_dir} 中没有同名配对的 left_* / right_* 图片"
        )
    return [(name, left_images[name], right_images[name]) for name in common_names]


def read_image(path):
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取图片: {path}")
    return image


def decode_points(image, threshold, color, min_iou):
    decoded, annotated = CCT_extract(image.copy(), 14, threshold, color, min_iou)
    grouped = {}
    for code_id, x, y in decoded:
        code_id = int(code_id)
        grouped.setdefault(code_id, []).append((float(x), float(y)))
    points = {
        code_id: coordinates[0]
        for code_id, coordinates in grouped.items()
        if len(coordinates) == 1
    }
    duplicate_ids = sorted(
        code_id for code_id, coordinates in grouped.items() if len(coordinates) > 1
    )
    return points, duplicate_ids, annotated


def write_debug_image(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    extension = path.suffix or ".png"
    ok, encoded = cv2.imencode(extension, image)
    if not ok:
        raise RuntimeError(f"无法编码调试图片: {path}")
    encoded.tofile(path)


def collect_views(pairs, layout, args):
    views = []
    image_size = None
    args.debug_dir.mkdir(parents=True, exist_ok=True)

    for index, (name, left_path, right_path) in enumerate(pairs, start=1):
        left_image = read_image(left_path)
        right_image = read_image(right_path)
        left_size = (left_image.shape[1], left_image.shape[0])
        right_size = (right_image.shape[1], right_image.shape[0])
        if left_size != right_size:
            print(f"[{index}/{len(pairs)}] 跳过 {name}: 左右尺寸不一致")
            continue
        if image_size is None:
            image_size = left_size
        elif left_size != image_size:
            print(f"[{index}/{len(pairs)}] 跳过 {name}: 与首组图片尺寸不一致")
            continue

        left_points, left_duplicates, left_debug = decode_points(
            left_image, args.threshold, args.color, args.min_iou
        )
        right_points, right_duplicates, right_debug = decode_points(
            right_image, args.threshold, args.color, args.min_iou
        )
        write_debug_image(args.debug_dir / f"left_{name}", left_debug)
        write_debug_image(args.debug_dir / f"right_{name}", right_debug)

        common_ids = sorted(layout.keys() & left_points.keys() & right_points.keys())
        duplicate_ids = sorted(set(left_duplicates) | set(right_duplicates))
        if duplicate_ids:
            print(f"[{index}/{len(pairs)}] {name}: 忽略重复解码 ID {duplicate_ids}")
        if len(common_ids) < args.min_points:
            print(
                f"[{index}/{len(pairs)}] 跳过 {name}: "
                f"左 {len(left_points)} / 右 {len(right_points)} / "
                f"共同有效 {len(common_ids)} 点"
            )
            continue

        object_points = np.asarray(
            [layout[code_id] for code_id in common_ids], dtype=np.float32
        )
        left_image_points = np.asarray(
            [left_points[code_id] for code_id in common_ids], dtype=np.float32
        )
        right_image_points = np.asarray(
            [right_points[code_id] for code_id in common_ids], dtype=np.float32
        )
        views.append(
            StereoView(
                name=name,
                object_points=object_points,
                left_points=left_image_points,
                right_points=right_image_points,
            )
        )
        print(f"[{index}/{len(pairs)}] 接受 {name}: {len(common_ids)} 个共同编码点")

    return views, image_size


def calculate_reprojection_error(object_points, image_points, rvecs, tvecs,
                                 camera_matrix, distortion):
    squared_error = 0.0
    point_count = 0
    for object_view, image_view, rvec, tvec in zip(
            object_points, image_points, rvecs, tvecs):
        projected, _ = cv2.projectPoints(
            object_view, rvec, tvec, camera_matrix, distortion
        )
        difference = image_view.reshape(-1, 2) - projected.reshape(-1, 2)
        squared_error += float(np.sum(difference * difference))
        point_count += len(object_view)
    return float(np.sqrt(squared_error / point_count))


def calibrate(views, image_size, fix_intrinsics):
    object_points = [view.object_points for view in views]
    left_points = [view.left_points for view in views]
    right_points = [view.right_points for view in views]

    calibration_flags = cv2.CALIB_RATIONAL_MODEL
    left_rms, left_matrix, left_distortion, left_rvecs, left_tvecs = (
        cv2.calibrateCamera(
            object_points, left_points, image_size, None, None,
            flags=calibration_flags,
        )
    )
    right_rms, right_matrix, right_distortion, right_rvecs, right_tvecs = (
        cv2.calibrateCamera(
            object_points, right_points, image_size, None, None,
            flags=calibration_flags,
        )
    )

    stereo_flags = cv2.CALIB_FIX_INTRINSIC if fix_intrinsics else (
        cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_RATIONAL_MODEL
    )
    stereo_result = cv2.stereoCalibrate(
        object_points,
        left_points,
        right_points,
        left_matrix,
        left_distortion,
        right_matrix,
        right_distortion,
        image_size,
        flags=stereo_flags,
        criteria=(
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
            200,
            1e-7,
        ),
    )
    (stereo_rms, left_matrix, left_distortion, right_matrix,
     right_distortion, rotation, translation, essential, fundamental) = stereo_result
    left_rectification, right_rectification, left_projection, right_projection, disparity_to_depth, _, _ = (
        cv2.stereoRectify(
            left_matrix,
            left_distortion,
            right_matrix,
            right_distortion,
            image_size,
            rotation,
            translation,
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0,
        )
    )

    return {
        "left_rms": left_rms,
        "right_rms": right_rms,
        "stereo_rms": stereo_rms,
        "left_reprojection_error": calculate_reprojection_error(
            object_points, left_points, left_rvecs, left_tvecs,
            left_matrix, left_distortion,
        ),
        "right_reprojection_error": calculate_reprojection_error(
            object_points, right_points, right_rvecs, right_tvecs,
            right_matrix, right_distortion,
        ),
        "left_camera_matrix": left_matrix,
        "left_distortion": left_distortion,
        "right_camera_matrix": right_matrix,
        "right_distortion": right_distortion,
        "rotation": rotation,
        "translation": translation,
        "essential": essential,
        "fundamental": fundamental,
        "left_rectification": left_rectification,
        "right_rectification": right_rectification,
        "left_projection": left_projection,
        "right_projection": right_projection,
        "disparity_to_depth": disparity_to_depth,
    }


def save_calibration(path, image_size, views, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    storage = cv2.FileStorage(str(path), cv2.FILE_STORAGE_WRITE)
    if not storage.isOpened():
        raise RuntimeError(f"无法写入标定结果: {path}")
    try:
        storage.write("image_width", image_size[0])
        storage.write("image_height", image_size[1])
        storage.write("valid_view_count", len(views))
        storage.write("valid_view_names", "\n".join(view.name for view in views))
        for key, value in result.items():
            storage.write(key, value)
    finally:
        storage.release()


def main():
    args = parse_args()
    try:
        layout = load_layout(args.layout)
        pairs = find_stereo_pairs(args.images)
        print(f"找到 {len(pairs)} 对照片，标定板包含 {len(layout)} 个编码点")
        views, image_size = collect_views(pairs, layout, args)
        if len(views) < args.min_views:
            raise RuntimeError(
                f"有效照片对只有 {len(views)}，至少需要 {args.min_views} 对；"
                "建议从不同距离和角度拍摄 15–25 对"
            )
        result = calibrate(views, image_size, args.fix_intrinsics)
        save_calibration(args.output, image_size, views, result)
    except (RuntimeError, cv2.error) as error:
        raise SystemExit(f"错误: {error}") from error

    baseline = float(np.linalg.norm(result["translation"]))
    print(f"\n标定完成: {args.output}")
    print(f"有效照片对: {len(views)}")
    print(f"左相机重投影误差: {result['left_reprojection_error']:.4f} px")
    print(f"右相机重投影误差: {result['right_reprojection_error']:.4f} px")
    print(f"双目标定 RMS: {result['stereo_rms']:.4f} px")
    print(f"双目基线: {baseline:.4f} mm（取决于布局文件单位）")
    print(f"解码标注图: {args.debug_dir}")


if __name__ == "__main__":
    main()
