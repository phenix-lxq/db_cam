"""CCT 解码需要的几何辅助函数。"""

import numpy as np


def my_getAffineTransform(src, dst):
    """用最小二乘求 2D 仿射变换矩阵。

    OpenCV 的 getAffineTransform 只接受 3 个点。原解码算法使用外接矩形 4 个
    角点加中心点，共 5 个点，因此这里保留最小二乘版本。
    """
    src = np.asarray(src, dtype=np.float32)
    dst = np.asarray(dst, dtype=np.float32)
    point_count = len(src)

    matrix = np.zeros((2 * point_count, 6), dtype=np.float64)
    target = np.zeros((2 * point_count, 1), dtype=np.float64)
    for index, (source_point, target_point) in enumerate(zip(src, dst)):
        x, y = source_point
        target_x, target_y = target_point
        matrix[2 * index] = [x, y, 0, 0, 1, 0]
        matrix[2 * index + 1] = [0, 0, x, y, 0, 1]
        target[2 * index] = target_x
        target[2 * index + 1] = target_y

    normal = matrix.T @ matrix
    if abs(np.linalg.det(normal)) < 0.1:
        return 0

    solution = np.linalg.inv(normal) @ matrix.T @ target
    return np.array(
        [
            [solution[0, 0], solution[1, 0], solution[4, 0]],
            [solution[2, 0], solution[3, 0], solution[5, 0]],
        ],
        dtype=np.float32,
    )
