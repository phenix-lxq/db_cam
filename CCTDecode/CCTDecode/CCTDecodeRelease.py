"""14-bit 环形编码点检测与解码。

本项目只需要从标定照片中提取编码点 ID 和中心坐标，因此这里删掉了原仓库中
与批处理演示、视频演示、绘图生成无关的代码。
"""

import math

import cv2
import numpy as np

from DrawCCT import B2I, rotation_indices
from Support import my_getAffineTransform


DEFAULT_MIN_ELLIPSE_IOU = 0.65
DEFAULT_MIN_CENTER_DIAMETER = 10.0
DEFAULT_MIN_RING_TRANSITIONS = 4


def contour_circularity(area, perimeter):
    """计算轮廓圆度，圆形接近 1，细长或扇形碎片会明显更低。"""
    if area <= 0 or perimeter <= 0:
        return 0.0
    return 4.0 * math.pi * area / (perimeter * perimeter)


def ellipse_contour_iou(contour, ellipse):
    """计算轮廓填充区域与拟合椭圆填充区域的 IoU。"""
    if ellipse[1][0] <= 0 or ellipse[1][1] <= 0:
        return 0.0

    contour_points = contour.reshape(-1, 2).astype(np.float32)
    ellipse_points = cv2.boxPoints(ellipse).astype(np.float32)
    all_points = np.vstack((contour_points, ellipse_points))

    margin = 3
    x_min = int(np.floor(np.min(all_points[:, 0]))) - margin
    y_min = int(np.floor(np.min(all_points[:, 1]))) - margin
    x_max = int(np.ceil(np.max(all_points[:, 0]))) + margin
    y_max = int(np.ceil(np.max(all_points[:, 1]))) + margin
    width = x_max - x_min + 1
    height = y_max - y_min + 1
    if width <= 1 or height <= 1:
        return 0.0

    shifted_contour = contour.copy()
    shifted_contour[:, 0, 0] -= x_min
    shifted_contour[:, 0, 1] -= y_min
    shifted_ellipse = (
        (ellipse[0][0] - x_min, ellipse[0][1] - y_min),
        ellipse[1],
        ellipse[2],
    )

    contour_mask = np.zeros((height, width), dtype=np.uint8)
    ellipse_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.drawContours(contour_mask, [shifted_contour], -1, 255, -1)
    cv2.ellipse(ellipse_mask, shifted_ellipse, 255, -1)

    intersection = np.count_nonzero(cv2.bitwise_and(contour_mask, ellipse_mask))
    union = np.count_nonzero(cv2.bitwise_or(contour_mask, ellipse_mask))
    return 0.0 if union == 0 else intersection / union


def sample_binary_points(image, x_points, y_points):
    """一次性采样多个二值图坐标，返回与输入形状一致的数组。"""
    rows = np.rint(y_points).astype(np.intp)
    columns = np.rint(x_points).astype(np.intp)
    samples = np.zeros(rows.shape, dtype=np.uint8)
    valid = (
        (rows >= 0)
        & (rows < image.shape[0])
        & (columns >= 0)
        & (columns < image.shape[1])
    )
    samples[valid] = image[rows[valid], columns[valid]]
    return samples


def sample_ring(image, center_x, center_y, radius, sample_count):
    """沿指定半径的圆周做向量化采样。"""
    angles = np.linspace(0.0, 2.0 * np.pi, sample_count, endpoint=False, dtype=np.float32)
    return sample_binary_points(
        image,
        center_x + radius * np.cos(angles),
        center_y + radius * np.sin(angles),
    )


def ring_transition_count(samples):
    """统计圆周采样序列中的明暗跳变次数。"""
    samples = np.asarray(samples, dtype=np.uint8)
    return int(np.count_nonzero(samples != np.roll(samples, -1)))


def ring_mean(binary, center_x, center_y, base_radius, radius_scales, sample_count=96):
    """对多个同心圆采样，并返回整体白色像素比例。"""
    angles = np.linspace(0.0, 2.0 * np.pi, sample_count, endpoint=False, dtype=np.float32)
    radii = base_radius * np.asarray(radius_scales, dtype=np.float32)[:, None]
    samples = sample_binary_points(
        binary,
        center_x + radii * np.cos(angles)[None, :],
        center_y + radii * np.sin(angles)[None, :],
    )
    return float(np.mean(samples))


def normalize_cct_roi(image, center_ellipse):
    """把透视后的椭圆区域仿射拉正成正圆图像。"""
    outer_ellipse = (
        center_ellipse[0],
        (center_ellipse[1][0] * 3, center_ellipse[1][1] * 3),
        center_ellipse[2],
    )
    outer_box = cv2.boxPoints(outer_ellipse)
    side = max(outer_ellipse[1])
    if side <= 0:
        return None

    center_x, center_y = center_ellipse[0]
    row_min = round(center_y - side / 2)
    row_max = round(center_y + side / 2)
    col_min = round(center_x - side / 2)
    col_max = round(center_x + side / 2)
    if row_min < 0 or col_min < 0 or row_max > image.shape[0] or col_max > image.shape[1]:
        return None

    roi = image[row_min:row_max, col_min:col_max]
    if roi.size == 0:
        return None

    dx = center_x - side / 2
    dy = center_y - side / 2
    src = np.float32(
        [
            [outer_box[0][0] - dx, outer_box[0][1] - dy],
            [outer_box[1][0] - dx, outer_box[1][1] - dy],
            [outer_box[2][0] - dx, outer_box[2][1] - dy],
            [outer_box[3][0] - dx, outer_box[3][1] - dy],
            [center_x - dx, center_y - dy],
        ]
    )
    dst = np.float32(
        [
            [center_x - side / 2 - dx, center_y - side / 2 - dy],
            [center_x + side / 2 - dx, center_y - side / 2 - dy],
            [center_x + side / 2 - dx, center_y + side / 2 - dy],
            [center_x - side / 2 - dx, center_y + side / 2 - dy],
            [center_x - dx, center_y - dy],
        ]
    )
    matrix = my_getAffineTransform(src, dst)
    if isinstance(matrix, int):
        return None

    normalized = cv2.warpAffine(roi, matrix, (round(side), round(side)))
    return cv2.resize(
        normalized,
        (0, 0),
        fx=200.0 / side,
        fy=200.0 / side,
        interpolation=cv2.INTER_LANCZOS4,
    )


def CCT_extract(
    image,
    bit_count,
    min_roundness,
    color="white",
    min_iou=DEFAULT_MIN_ELLIPSE_IOU,
    min_center_diameter=DEFAULT_MIN_CENTER_DIAMETER,
    min_ring_transitions=DEFAULT_MIN_RING_TRANSITIONS,
    valid_ids=None,
):
    """提取图像中的 CCT 编码点。

    返回值为 `(code_table, annotated_image)`。`code_table` 中每一项是
    `[code_id, center_x, center_y]`。
    """
    code_table = []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    for contour in contours:
        area = cv2.contourArea(contour, False)
        perimeter = cv2.arcLength(contour, True)
        roundness = 2 * math.sqrt(math.pi * area) / (perimeter + 1)
        if roundness < min_roundness:
            continue
        if contour_circularity(area, perimeter) < min_roundness * min_roundness:
            continue
        if len(contour) < 20:
            continue

        center_ellipse = cv2.fitEllipse(np.asarray(contour))
        if min(center_ellipse[1]) < min_center_diameter:
            continue
        if ellipse_contour_iou(contour, center_ellipse) < min_iou:
            continue

        normalized = normalize_cct_roi(image, center_ellipse)
        if normalized is None:
            continue

        normalized_gray = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)
        _, normalized_binary = cv2.threshold(
            normalized_gray,
            0,
            1,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        eroded = cv2.erode(normalized_binary, kernel)

        if not CCT_or_not(eroded, color, min_ring_transitions):
            continue

        code = CCT_Decode(eroded, bit_count, color)
        if valid_ids is not None and code not in valid_ids:
            continue

        center_x, center_y = center_ellipse[0]
        code_table.append([code, center_x, center_y])

        outer_ellipse = (
            center_ellipse[0],
            (center_ellipse[1][0] * 3, center_ellipse[1][1] * 3),
            center_ellipse[2],
        )
        middle_ellipse = (
            center_ellipse[0],
            (center_ellipse[1][0] * 2, center_ellipse[1][1] * 2),
            center_ellipse[2],
        )
        side = max(outer_ellipse[1])
        cv2.putText(
            image,
            str(code),
            (int(center_x - 0.25 * side), int(center_y + 0.5 * side)),
            cv2.FONT_HERSHEY_COMPLEX,
            1,
            (0, 0, 255),
            2,
        )
        cv2.ellipse(image, center_ellipse, (0, 255, 0), 1)
        cv2.ellipse(image, middle_ellipse, (0, 255, 0), 1)
        cv2.ellipse(image, outer_ellipse, (0, 255, 0), 1)

    return code_table, image


def CCT_or_not(cct_binary, color="white", min_ring_transitions=DEFAULT_MIN_RING_TRANSITIONS):
    """判断归一化后的候选区域是否具有 CCT 的中心圆和编码环结构。"""
    sample_count = 96
    height, width = cct_binary.shape[:2]
    center_x = width / 2
    center_y = height / 2
    radius = center_x / 3.0

    center_ratio = ring_mean(cct_binary, center_x, center_y, radius, (0.30, 0.55, 0.80), sample_count)
    gap_ratio = ring_mean(cct_binary, center_x, center_y, radius, (1.20, 1.45, 1.70), sample_count)
    code_ring = sample_ring(cct_binary, center_x, center_y, radius * 2.5, sample_count)
    code_ratio = float(np.mean(code_ring))
    transitions = ring_transition_count(code_ring)

    if color == "white":
        center_ok = center_ratio >= 0.90
        gap_ok = gap_ratio <= 0.10
    else:
        center_ok = center_ratio <= 0.10
        gap_ok = gap_ratio >= 0.90

    code_ring_is_mixed = 0.12 <= code_ratio <= 0.88
    code_ring_has_segments = transitions >= min_ring_transitions
    return center_ok and gap_ok and code_ring_is_mixed and code_ring_has_segments


def canonicalize_code_rows(bit_rows):
    """把多行采样 bit 旋转归一化成最小整数对应的 bit 行。"""
    bit_rows = np.asarray(bit_rows, dtype=np.uint8)
    bit_count = bit_rows.shape[1]
    weights = (1 << np.arange(bit_count, dtype=np.uint32))
    rotations = bit_rows[:, rotation_indices(bit_count)]
    values = np.sum(rotations * weights, axis=2)
    best_rotation_indices = np.argmin(values, axis=1)
    return rotations[np.arange(bit_rows.shape[0]), best_rotation_indices]


def CCT_Decode(cct_binary, bit_count, color):
    """沿编码环采样并转成旋转归一化后的整数 ID。"""
    height, width = cct_binary.shape[:2]
    center_x = width / 2
    center_y = height / 2
    radius = center_x * 0.333333

    offsets = np.arange(int(360 / bit_count), dtype=np.float32)[:, None]
    bit_indices = np.arange(bit_count, dtype=np.float32)[None, :]
    angles = np.deg2rad(360.0 / bit_count * bit_indices + offsets)
    sampled_bits = sample_binary_points(
        cct_binary,
        2.5 * radius * np.cos(angles) + center_x,
        2.5 * radius * np.sin(angles) + center_y,
    )

    # 每一圈采样都先做旋转归一化，再参与平均，降低起始角误差影响。
    sampled_codes = canonicalize_code_rows(sampled_bits)
    result = (np.mean(sampled_codes, axis=0) > 0.5).astype(np.uint8)
    if color == "black":
        result = swap0and1(result)
    return B2I(result, len(result))


def swap0and1(bits):
    """黑码白底时需要把采样结果反相。"""
    return 1 - np.asarray(bits, dtype=np.uint8)
