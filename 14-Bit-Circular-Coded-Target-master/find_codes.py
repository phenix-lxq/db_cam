"""生成环形编码点可用的二进制编码序列。

这里保留原 14-Bit-Circular-Coded-Target 仓库的筛选规则，只删掉独立命令行
打印入口。本项目通过 `create_target_sheets.CODES` 间接调用 `generate_codes(14)`。
"""


def bitwise_rotate_left(value, shift, total_bits):
    """把 total_bits 位整数循环左移。"""
    mask = 2**total_bits - 1
    return ((value << shift) & mask) | ((value & mask) >> (total_bits - shift))


def find_smallest_rotation(value, total_bits):
    """返回所有循环旋转中数值最小的那个编码。"""
    smallest = value
    for shift in range(1, total_bits):
        smallest = min(bitwise_rotate_left(value, shift, total_bits), smallest)
    return smallest


def calc_parity(value):
    """偶校验返回 True，奇校验返回 False。"""
    parity = True
    while value:
        parity = not parity
        value = value & (value - 1)
    return parity


def count_bit_transitions(value):
    """统计从 0 到 1 的跳变次数，保持原仓库定义。"""
    transitions = 0
    previous_bit = 0
    while value:
        current_bit = value & 1
        if current_bit > previous_bit:
            transitions += 1
        previous_bit = current_bit
        value >>= 1
    return transitions


def generate_codes(bits, transitions=None):
    """生成指定 bit 数的环形编码。

    筛选条件：

    - 旋转等价编码只保留最小值。
    - 编码必须满足偶校验。
    - 至少有一对相对扇区同时为 1。
    - 如果指定 transitions，则跳变次数必须一致。
    """
    codes = []
    for value in range(2 ** (bits - 2)):
        code = (value << 1) + 1
        code = find_smallest_rotation(code, bits)

        half_bits = bits >> 1
        opposite_mask = 2**half_bits - 1
        opposite_pair = (code & opposite_mask) & ((code & (opposite_mask << half_bits)) >> half_bits)

        parity = calc_parity(code)
        transition_count = count_bit_transitions(code) if transitions else None

        if parity and opposite_pair > 0 and transitions == transition_count and code not in codes:
            codes.append(code)
    return codes
