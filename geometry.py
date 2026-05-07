"""2D geometry primitives used by the joinery and panel code.

Everything is plain tuples of floats - no external dependencies - so that
the rest of the package stays easy to reason about. Points are (x, y) in
millimeters.

Edge-local frame convention
---------------------------
Every joinery edge profile is generated in a canonical local frame:

    local +X = along the edge, from start corner to end corner
    local +Y = inward (toward the panel interior)

A tab sticking OUT of the panel has positive Y. A notch cut INTO the panel
has negative Y. Edges are then rotated and translated into the panel frame
with :func:`place_edge_on_rect`.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]
Path = list[Point]


# ---------------------------------------------------------------------------
# low-level transforms
# ---------------------------------------------------------------------------

def rotate(p: Point, angle_deg: float) -> Point:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y = p
    return (c * x - s * y, s * x + c * y)


def translate(p: Point, dx: float, dy: float) -> Point:
    return (p[0] + dx, p[1] + dy)


def transform_path(points: Iterable[Point], dx: float, dy: float, angle_deg: float) -> Path:
    return [translate(rotate(p, angle_deg), dx, dy) for p in points]


# ---------------------------------------------------------------------------
# edge placement on a rectangle
# ---------------------------------------------------------------------------

# Panel frame: origin at bottom-left corner, +X right, +Y up. Edges are
# walked counter-clockwise so the outline polygon is CCW (the DXF convention
# for "material inside").

def place_edge_on_rect(
    edge_pts: Sequence[Point],
    panel_w: float,
    panel_h: float,
    side: str,
) -> Path:
    """Map an edge-local path onto one side of a panel rectangle.

    The resulting path runs along the chosen side in CCW direction. Edge-local
    +Y maps to the panel interior.
    """

    if side == "bottom":
        # start (0,0) -> (W,0); interior is +Y
        return transform_path(edge_pts, 0.0, 0.0, 0.0)
    if side == "right":
        # start (W,0) -> (W,H); interior is -X (rotate +90)
        return transform_path(edge_pts, panel_w, 0.0, 90.0)
    if side == "top":
        # start (W,H) -> (0,H); interior is -Y (rotate 180)
        return transform_path(edge_pts, panel_w, panel_h, 180.0)
    if side == "left":
        # start (0,H) -> (0,0); interior is +X (rotate 270)
        return transform_path(edge_pts, 0.0, panel_h, 270.0)
    raise ValueError(f"unknown side {side!r}")


# ---------------------------------------------------------------------------
# path building helpers
# ---------------------------------------------------------------------------

def dedupe_consecutive(points: Sequence[Point], tol: float = 1e-6) -> Path:
    """Drop consecutive duplicate points (within tol)."""

    out: Path = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol:
            out.append(p)
    return out


def stitch_edges(edges: Sequence[Sequence[Point]]) -> Path:
    """Join a CCW sequence of edge paths into a single closed outline.

    Each edge starts at the previous edge's end corner, so the corner points
    are duplicated; we drop them.
    """

    combined: Path = []
    for edge in edges:
        if not combined:
            combined.extend(edge)
        else:
            # skip the first point of this edge because it equals the last
            # point of the previous edge (corner).
            combined.extend(edge[1:])
    return dedupe_consecutive(combined)


def bounding_box(points: Iterable[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def translate_path(points: Iterable[Point], dx: float, dy: float) -> Path:
    return [(p[0] + dx, p[1] + dy) for p in points]


def rect(x: float, y: float, w: float, h: float) -> Path:
    """Axis-aligned rectangle as a CCW closed path (first point repeated)."""

    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
