"""14-bit 环形编码点 SVG 片段生成。

这个文件来自 14-Bit-Circular-Coded-Target 项目的绘制逻辑。本项目只需要
`CODES` 和 `add_target()`，因此删掉了原来的 Inkscape/PDFtk 批量导出代码。
"""

import math

import find_codes


CODES = find_codes.generate_codes(14)
SEGMENT_OVERLAP_DEGREES = 0.15


def polar_point(x_center, y_center, radius, angle_degrees):
    """把极坐标转换成 SVG 坐标。"""
    angle = math.radians(angle_degrees)
    return (
        x_center + math.cos(angle) * radius,
        y_center + math.sin(angle) * radius,
    )


def annular_sector_path(x_center, y_center, inner_radius, outer_radius, start_angle, end_angle):
    """生成一个闭合的环形扇区 path，避免描边圆弧产生打印接缝。"""
    outer_start = polar_point(x_center, y_center, outer_radius, start_angle)
    outer_end = polar_point(x_center, y_center, outer_radius, end_angle)
    inner_end = polar_point(x_center, y_center, inner_radius, end_angle)
    inner_start = polar_point(x_center, y_center, inner_radius, start_angle)

    return (
        f"M {outer_start[0]} {outer_start[1]} "
        f"A {outer_radius} {outer_radius} 0 0 1 {outer_end[0]} {outer_end[1]} "
        f"L {inner_end[0]} {inner_end[1]} "
        f"A {inner_radius} {inner_radius} 0 0 0 {inner_start[0]} {inner_start[1]} "
        "Z"
    )


def add_target(x_center, y_center, dot_radius, code, code_num, first_segment, show_label=False):
    """返回单个环形编码点的 SVG。

    参数单位由调用方的 SVG 坐标系决定。本项目使用 mm。
    """
    target_svg = f'<circle fill="#fff" cx="{x_center}" cy="{y_center}" r="{dot_radius}"/>\n'
    target_svg += '<g fill="#fff" stroke="none">\n'

    for index in range(14):
        if not ((1 << (13 - index)) & code):
            continue

        start_angle = 360 / 14 * index - SEGMENT_OVERLAP_DEGREES
        end_angle = 360 / 14 * (index + 1) + SEGMENT_OVERLAP_DEGREES
        sector_path = annular_sector_path(
            x_center,
            y_center,
            dot_radius * 2.0,
            dot_radius * 3.0,
            start_angle,
            end_angle,
        )
        first_id = ' id="first"' if first_segment else ""
        target_svg += f'<path d="{sector_path}"{first_id}/>\n'
        first_segment = False

    target_svg += "</g>\n"

    if show_label:
        target_svg += (
            f'<text x="{x_center - dot_radius * 3}" y="{y_center + dot_radius * 3}" '
            f'font-size="{dot_radius / 2}" alignment-base="bottom" '
            f'font-family="Source Sans Pro, sans-serif" fill="#fff">{code_num + 1}</text>'
        )
    return target_svg
