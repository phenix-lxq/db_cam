"""CCT 编码值和二进制序列之间的转换工具。

原仓库中的这个文件还包含批量绘制 CCT 图片的函数。本项目只需要解码阶段的
旋转归一化逻辑，所以这里保留最小必要函数。
"""


def I2B(value, bit_count):
    """把整数转换成低位在前的 bit 列表。"""
    bits = []
    for _ in range(bit_count):
        bits.append(value & 1)
        value >>= 1
    return bits


def MoveBit(bits, shift):
    """循环左移 bit 列表。保留原函数名，兼容旧解码代码。"""
    shifted = list(bits)
    for _ in range(shift):
        shifted.append(shifted.pop(0))
    return shifted


def B2I(bits, bit_count):
    """把 bit 列表转换成旋转等价下的最小整数编码。"""
    rotations = []
    current = list(bits[:bit_count])
    for _ in range(bit_count):
        value = 0
        for index, bit in enumerate(current):
            if bit:
                value += 1 << index
        rotations.append(value)
        current = MoveBit(current, 1)
    return min(rotations)
