"""Naive shelf/row packer for arranging panels on a virtual sheet.

Sorts panels by descending height then lays them out left-to-right in
rows. When a panel would overrun the sheet width, a new row is started
above. The result is fine for simple box projects; for higher density
you would want a proper 2D bin-packer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .panel import Panel


@dataclass
class PlacedPanel:
    """A panel that has been placed on a sheet. ``dx, dy`` is the offset
    from the panel's local origin to its position on the sheet. Add this
    offset to every point in the panel's outline and reliefs at DXF time.
    """

    panel: Panel
    dx: float
    dy: float


def layout_panels(
    panels: list[Panel],
    sheet_w: float,
    sheet_h: float,
    spacing: float = 10.0,
    margin: float = 10.0,
) -> list[PlacedPanel]:
    """Place each panel on a (sheet_w x sheet_h) sheet with the given
    inter-panel spacing and sheet-edge margin.

    Raises ``ValueError`` if a single panel is too large to fit the sheet
    or if the overall layout would overflow.
    """

    if sheet_w <= 0 or sheet_h <= 0:
        raise ValueError("sheet dimensions must be > 0")
    if spacing < 0 or margin < 0:
        raise ValueError("spacing and margin must be >= 0")

    # Sort by bounding-box height (tallest first) to make shelves tight.
    ordered = sorted(panels, key=lambda p: p.height(), reverse=True)

    placed: list[PlacedPanel] = []
    cursor_x = margin
    row_bottom = margin
    row_height = 0.0

    for panel in ordered:
        x0, y0, x1, y1 = panel.extents()
        bw = x1 - x0
        bh = y1 - y0

        if bw > sheet_w - 2 * margin or bh > sheet_h - 2 * margin:
            raise ValueError(
                f"panel {panel.name!r} ({bw:.1f} x {bh:.1f} mm) is larger than "
                f"the sheet minus margin ({sheet_w - 2*margin:.1f} x "
                f"{sheet_h - 2*margin:.1f} mm)"
            )

        if cursor_x + bw > sheet_w - margin:
            # Wrap to a new row.
            row_bottom += row_height + spacing
            cursor_x = margin
            row_height = 0.0

        if row_bottom + bh > sheet_h - margin:
            raise ValueError(
                f"panel {panel.name!r} does not fit on the sheet; overall layout "
                f"would exceed {sheet_w} x {sheet_h} mm. Consider a larger sheet, "
                f"a smaller box, or cutting panels across multiple sheets."
            )

        # Offset places the panel's bounding-box lower-left at (cursor_x, row_bottom).
        dx = cursor_x - x0
        dy = row_bottom - y0
        placed.append(PlacedPanel(panel=panel, dx=dx, dy=dy))

        cursor_x += bw + spacing
        row_height = max(row_height, bh)

    return placed
