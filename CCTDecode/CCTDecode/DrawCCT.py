"""CCT 编码值和二进制序列之间的转换工具。

原仓库中的这个文件还包含批量绘制 CCT 图片的函数。本项目只需要解码阶段的
旋转归一化逻辑，所以这里保留最小必要函数。
"""

import numpy as np


def I2B(value, bit_count):
    """把整数转换成低位在前的 bit 向量。"""
    shifts = np.arange(bit_count, dtype=np.uint32)
    return ((int(value) >> shifts) & 1).astype(np.uint8)


def MoveBit(bits, shift):
    """循环左移 bit 向量。保留原函数名，兼容旧解码代码。"""
    return np.roll(np.asarray(bits, dtype=np.uint8), -shift)


def rotation_indices(bit_count):
    """生成所有循环左移对应的列索引矩阵。"""
    columns = np.arange(bit_count)
    shifts = columns[:, None]
    return (columns[None, :] + shifts) % bit_count


def B2I(bits, bit_count):
    """把 bit 向量转换成旋转等价下的最小整数编码。"""
    bits = np.asarray(bits[:bit_count], dtype=np.uint8)
    weights = (1 << np.arange(bit_count, dtype=np.uint32))
    rotations = bits[rotation_indices(bit_count)]
    return int(np.min(np.sum(rotations * weights, axis=1)))
