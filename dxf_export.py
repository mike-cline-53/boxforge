"""Write placed panels out to a DXF file ready for EstlCAM.

Layers used:

- ``CUT_OUTSIDE`` (red): outer profile polyline of every panel.
- ``CUT_INSIDE`` (blue): inner cuts (dogbone circles, tbone squares).
- ``LABEL`` (green): panel name text, for reference only - do NOT toolpath.
- ``SHEET`` (gray): a virtual 4' x 8' sheet border for context - do NOT
  toolpath.

Output is DXF R2010 with units set to millimeters.
"""

from __future__ import annotations

import os
from typing import Sequence

import ezdxf

from .corner_relief import CircleRelief, RectRelief, Relief
from .layout import PlacedPanel


LAYER_CUT_OUTSIDE = "CUT_OUTSIDE"
LAYER_CUT_INSIDE = "CUT_INSIDE"
LAYER_LABEL = "LABEL"
LAYER_SHEET = "SHEET"


def _ensure_layers(doc: "ezdxf.document.Drawing") -> None:
    layers = doc.layers
    for name, color in [
        (LAYER_CUT_OUTSIDE, 1),  # red
        (LAYER_CUT_INSIDE, 5),   # blue
        (LAYER_LABEL, 3),        # green
        (LAYER_SHEET, 8),        # dark gray
    ]:
        if name in layers:
            continue
        layers.add(name=name, color=color)


def _translate_outline(points, dx: float, dy: float):
    return [(p[0] + dx, p[1] + dy) for p in points]


def _add_relief(msp, relief: Relief, dx: float, dy: float) -> None:
    attribs = {"layer": LAYER_CUT_INSIDE}
    if isinstance(relief, CircleRelief):
        cx, cy = relief.center
        msp.add_circle(
            center=(cx + dx, cy + dy),
            radius=relief.diameter / 2.0,
            dxfattribs=attribs,
        )
    elif isinstance(relief, RectRelief):
        msp.add_lwpolyline(
            _translate_outline(relief.outline, dx, dy),
            close=True,
            dxfattribs=attribs,
        )
    else:  # pragma: no cover - defensive
        raise TypeError(f"unknown relief type {type(relief)!r}")


def _label_position(placed: PlacedPanel) -> tuple[float, float]:
    x0, y0, x1, y1 = placed.panel.extents()
    cx = (x0 + x1) / 2.0 + placed.dx
    cy = (y0 + y1) / 2.0 + placed.dy
    return cx, cy


def _add_label(msp, placed: PlacedPanel, text_height: float) -> None:
    cx, cy = _label_position(placed)
    text = msp.add_text(
        placed.panel.name,
        dxfattribs={
            "layer": LAYER_LABEL,
            "height": text_height,
        },
    )
    # align=MIDDLE_CENTER; set_placement is the modern ezdxf helper.
    text.set_placement(
        (cx, cy),
        align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER,
    )


def _add_sheet_border(msp, sheet_w: float, sheet_h: float) -> None:
    msp.add_lwpolyline(
        [(0, 0), (sheet_w, 0), (sheet_w, sheet_h), (0, sheet_h)],
        close=True,
        dxfattribs={"layer": LAYER_SHEET},
    )


def write_dxf(
    placed: Sequence[PlacedPanel],
    out_path: str,
    sheet_w: float | None = None,
    sheet_h: float | None = None,
    draw_sheet_border: bool = True,
    label_height: float = 12.0,
) -> None:
    """Write the placed panels to ``out_path`` as a DXF."""

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    _ensure_layers(doc)

    if draw_sheet_border and sheet_w and sheet_h:
        _add_sheet_border(msp, sheet_w, sheet_h)

    for pp in placed:
        outline_pts = _translate_outline(pp.panel.outline, pp.dx, pp.dy)
        msp.add_lwpolyline(
            outline_pts,
            close=True,
            dxfattribs={"layer": LAYER_CUT_OUTSIDE},
        )
        for relief in pp.panel.reliefs:
            _add_relief(msp, relief, pp.dx, pp.dy)
        _add_label(msp, pp, text_height=label_height)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.saveas(out_path)
