import sys
import re
from pathlib import Path

import pymupdf


PROJECT_DIR = Path(__file__).resolve().parent
TARGET_REPO_DIR = PROJECT_DIR / "14-Bit-Circular-Coded-Target-master"
if str(TARGET_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(TARGET_REPO_DIR))

import create_target_sheets as target_sheets


PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
MARKER_DIAMETER_MM = 40.0
CENTER_SPACING_MM = 60.0
BOARD_CENTER_X_MM = PAGE_WIDTH_MM / 2
BOARD_CENTER_Y_MM = PAGE_HEIGHT_MM / 2
OUTPUT_SVG = PROJECT_DIR / "cct14_3x3_A4_60mm.svg"
OUTPUT_PDF = PROJECT_DIR / "cct14_3x3_A4_60mm.pdf"
OUTPUT_LAYOUT = PROJECT_DIR / "cct14_layout.csv"

# 1-based target numbers from this repository's 516-code sequence.
TARGET_NUMBERS = (
    (105, 143, 161),
    (311, 398, 423),
    (440, 455, 485),
)


def rotate_left(value, shift, bit_count=14):
    mask = (1 << bit_count) - 1
    return ((value << shift) & mask) | (value >> (bit_count - shift))


def decoded_code_id(source_code, bit_count=14):
    reversed_code = sum(
        ((source_code >> index) & 1) << (bit_count - 1 - index)
        for index in range(bit_count)
    )
    return min(rotate_left(reversed_code, shift, bit_count)
               for shift in range(bit_count))


def marker_center_mm(row, column):
    return (
        BOARD_CENTER_X_MM + (column - 1) * CENTER_SPACING_MM,
        BOARD_CENTER_Y_MM + (row - 1) * CENTER_SPACING_MM,
    )


def selected_targets():
    for row, target_row in enumerate(TARGET_NUMBERS):
        for column, target_number in enumerate(target_row):
            source_code = target_sheets.CODES[target_number - 1]
            yield row, column, target_number, source_code


def create_svg():
    dot_radius = MARKER_DIAMETER_MM / 6
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{PAGE_WIDTH_MM}mm" height="{PAGE_HEIGHT_MM}mm" '
        f'viewBox="0 0 {PAGE_WIDTH_MM} {PAGE_HEIGHT_MM}">',
        f'<rect width="{PAGE_WIDTH_MM}" height="{PAGE_HEIGHT_MM}" fill="#fff"/>',
        '<rect x="5" y="5" width="200" height="247" fill="#000"/>',
    ]
    first_segment = True
    for row, column, target_number, source_code in selected_targets():
        center_x, center_y = marker_center_mm(row, column)
        target_svg = target_sheets.add_target(
            center_x,
            center_y,
            dot_radius,
            source_code,
            target_number - 1,
            first_segment,
        )
        parts.append(re.sub(r"<text\b.*?</text>", "", target_svg, flags=re.DOTALL))
        first_segment = False

    parts.append('</svg>')
    return "\n".join(parts)


def write_pdf(svg):
    svg_document = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
    OUTPUT_PDF.write_bytes(svg_document.convert_to_pdf())


def write_layout():
    lines = ["id,x_mm,y_mm,target_number,source_code"]
    for row, column, target_number, source_code in selected_targets():
        lines.append(
            f"{decoded_code_id(source_code)},"
            f"{column * CENTER_SPACING_MM:.1f},"
            f"{row * CENTER_SPACING_MM:.1f},"
            f"{target_number},{source_code}"
        )
    OUTPUT_LAYOUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    svg = create_svg()
    OUTPUT_SVG.write_text(svg, encoding="utf-8")
    write_pdf(svg)
    write_layout()
    print(f"Source: {TARGET_REPO_DIR / 'create_target_sheets.py'}")
    print(f"SVG: {OUTPUT_SVG}")
    print(f"PDF: {OUTPUT_PDF}")
    print(f"Layout: {OUTPUT_LAYOUT}")
    print("Target diameter: 40.0 mm")
    print("Horizontal/vertical center spacing: 60.0 mm")


if __name__ == "__main__":
    main()
