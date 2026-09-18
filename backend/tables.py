"""Measured native table geometry, shared by planning and PowerPoint export."""

import math
from .design import FONT_PAIRS, block_metrics, wrapped_lines, fitted_size


def table_layout(rows, style="modern", human=False):
    maximum = 8 if human else 7
    if (
        not rows
        or len(rows) > maximum
        or not 1 <= len(rows[0]) <= 5
        or any(len(r) != len(rows[0]) for r in rows)
    ):
        raise ValueError(
            "A table needs matching columns, at most 5 columns, and at most 7 data rows. Choose Review slides to repaginate it."
        )
    width = 11200000 // len(rows[0])
    available = 4500000
    for size in range(22 if human else 18, (18 if human else 12) - 1, -1):
        heights = []
        for i, row in enumerate(rows):
            family = FONT_PAIRS[style][0 if i == 0 else 1]
            # Match fitted_size's conservative text margins and line-height, including cell padding.
            lines = max(
                wrapped_lines(
                    b["plain"],
                    width / 12700 - 20,
                    family,
                    size,
                    max(b["stretch"], 1.05 if i == 0 else 1),
                )
                for cell in row
                for b in block_metrics(cell)
            )
            heights.append(
                max(
                    520000 if human else 400000,
                    math.ceil((lines * size * 1.27 + 16) * 12700),
                )
            )
        if sum(heights) > available:
            continue
        for i, row in enumerate(rows):
            for cell in row:
                fitted_size(
                    [0, 0, width, heights[i] - 40000],
                    cell,
                    size,
                    size,
                    FONT_PAIRS[style][0 if i == 0 else 1],
                )
        return dict(
            widths=[width] * len(rows[0]),
            heights=heights,
            size=size,
            height=sum(heights),
        )
    raise ValueError(
        "This table needs more vertical space. Choose Review slides to split its rows across readable slides; shorten very long column headings."
    )


def paginate_table(rows, style="modern", human=False):
    if len(rows) < 2:
        return [rows]
    limit = 7 if human else 6
    remaining = rows[1:]
    pages = []
    while remaining:
        for count in range(min(limit, len(remaining)), 0, -1):
            page = [rows[0]] + remaining[:count]
            try:
                table_layout(page, style, human)
            except ValueError:
                if count == 1:
                    raise
            else:
                break
        pages.append(page)
        remaining = remaining[count:]
    # Balance the final two pages if both still fit, avoiding an isolated final row.
    if len(pages) > 1:
        tail = pages[-2][1:] + pages[-1][1:]
        mid = math.ceil(len(tail) / 2)
        candidates = [[rows[0]] + tail[:mid], [rows[0]] + tail[mid:]]
        try:
            for page in candidates:
                table_layout(page, style, human)
        except ValueError:
            pass
        else:
            pages[-2:] = candidates
    return pages
