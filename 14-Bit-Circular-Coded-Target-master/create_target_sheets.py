"""14-bit 环形编码点 SVG 片段生成。

这个文件来自 14-Bit-Circular-Coded-Target 项目的绘制逻辑。本项目只需要
`CODES` 和 `add_target()`，因此删掉了原来的 Inkscape/PDFtk 批量导出代码。
"""

import numpy as np

import find_codes


CODES = find_codes.generate_codes(14)


def add_target(x_center, y_center, dot_radius, code, code_num, first_segment, show_label=False):
    """返回单个环形编码点的 SVG。

    参数单位由调用方的 SVG 坐标系决定。本项目使用 mm。
    """
    target_svg = f'<circle fill="#fff" cx="{x_center}" cy="{y_center}" r="{dot_radius}"/>\n'
    target_svg += f'<g stroke="#fff" stroke-width="{dot_radius}" fill="none">\n'

    for index in range(14):
        if not ((1 << (13 - index)) & code):
            continue

        start_x = np.cos(np.deg2rad(360 / 14 * index)) * dot_radius * 2.5
        start_y = np.sin(np.deg2rad(360 / 14 * index)) * dot_radius * 2.5
        end_x = np.cos(np.deg2rad(360 / 14 * (index + 1))) * dot_radius * 2.5 - start_x
        end_y = np.sin(np.deg2rad(360 / 14 * (index + 1))) * dot_radius * 2.5 - start_y
        start_x += x_center
        start_y += y_center
        first_id = ' id="first"' if first_segment else ""
        target_svg += (
            f'<path fill="#fff" d="m{start_x} {start_y}'
            f'a{dot_radius * 2.5} {dot_radius * 2.5} 0 0 1 {end_x} {end_y}"{first_id}/>\n'
        )
        first_segment = False

    target_svg += "</g>\n"

    if show_label:
        target_svg += (
            f'<text x="{x_center - dot_radius * 3}" y="{y_center + dot_radius * 3}" '
            f'font-size="{dot_radius / 2}" alignment-base="bottom" '
            f'font-family="Source Sans Pro, sans-serif" fill="#fff">{code_num + 1}</text>'
        )
    return target_svg
