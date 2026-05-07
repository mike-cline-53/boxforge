"""CNC corner relief for inner corners of finger-joint notches.

A round CNC bit cannot cut a sharp 90 degree inner corner - it leaves a
fillet of radius = bit radius of uncut material. If the mating panel has a
matching sharp outside corner, it will not seat flush.

Two common fixes are implemented here, both emitted as separate closed
geometry on the ``CUT_INSIDE`` layer so you can set them up as a small
pocket or drill operation in EstlCAM:

- ``dogbone``: a circle of diameter = bit_diameter, centered at the inner
  corner. A plunge/drill at this position removes the uncut fillet.
- ``tbone``: a bit_diameter x bit_diameter square with one corner at the
  inner corner, extending diagonally into the material along the corner's
  bisector. A pocket of this square gives the same relief as a dogbone but
  with visible square profile on one face.

Use ``none`` to skip relief entirely (you will have to clean corners by
hand or with a chisel).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

from .config import CornerRelief
from .geometry import Path, Point


@dataclass(frozen=True)
class CircleRelief:
    center: Point
    diameter: float


@dataclass(frozen=True)
class RectRelief:
    outline: Path  # closed rectangular path (first point repeated)


Relief = CircleRelief | RectRelief


# ---------------------------------------------------------------------------
# concave corner detection
# ---------------------------------------------------------------------------

def _iter_vertices(outline: Sequence[Point], tol: float) -> list[Point]:
    pts = list(outline)
    if len(pts) >= 2:
        p0, pn = pts[0], pts[-1]
        if abs(p0[0] - pn[0]) < tol and abs(p0[1] - pn[1]) < tol:
            pts = pts[:-1]
    return pts


def concave_corners(
    outline: Sequence[Point],
    tol: float = 1e-6,
) -> Iterator[tuple[Point, Point, Point]]:
    """Yield ``(prev, corner, next)`` triples at each concave vertex.

    Assumes the outline is counter-clockwise (material on the left while
    walking); at a concave vertex the turn is clockwise, which is the z-
    component of the cross product being negative.
    """

    pts = _iter_vertices(outline, tol)
    n = len(pts)
    if n < 3:
        return
    for i in range(n):
        prev = pts[(i - 1) % n]
        curr = pts[i]
        nxt = pts[(i + 1) % n]
        ax, ay = curr[0] - prev[0], curr[1] - prev[1]
        bx, by = nxt[0] - curr[0], nxt[1] - curr[1]
        cross = ax * by - ay * bx
        if cross < -tol:
            yield prev, curr, nxt


# ---------------------------------------------------------------------------
# relief generation
# ---------------------------------------------------------------------------

def _unit(a: Point, b: Point, tol: float = 1e-9) -> Point:
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = (dx * dx + dy * dy) ** 0.5
    if m < tol:
        return (0.0, 0.0)
    return (dx / m, dy / m)


def _material_axial_signs(d_in: Point, d_out: Point) -> tuple[int, int]:
    """For a CCW polygon with axis-aligned edges, return the axial signs
    (sx, sy) pointing into the material from the corner."""

    # 90 degree CCW rotation of a direction gives the inward (material-side)
    # normal for a CCW polygon.
    nx_in, ny_in = -d_in[1], d_in[0]
    nx_out, ny_out = -d_out[1], d_out[0]
    bx = nx_in + nx_out
    by = ny_in + ny_out
    sx = 0 if abs(bx) < 1e-9 else (1 if bx > 0 else -1)
    sy = 0 if abs(by) < 1e-9 else (1 if by > 0 else -1)
    return sx, sy


def generate_relief(
    outline: Sequence[Point],
    mode: CornerRelief,
    bit_diameter: float,
) -> list[Relief]:
    """Emit relief geometry for every concave corner of an outline."""

    if mode == "none":
        return []
    if bit_diameter <= 0:
        raise ValueError(f"bit_diameter must be > 0, got {bit_diameter}")

    reliefs: list[Relief] = []
    for prev, curr, nxt in concave_corners(outline):
        if mode == "dogbone":
            reliefs.append(CircleRelief(center=curr, diameter=bit_diameter))
            continue

        # tbone: square extending into the material bisector
        d_in = _unit(prev, curr)
        d_out = _unit(curr, nxt)
        sx, sy = _material_axial_signs(d_in, d_out)
        if sx == 0 or sy == 0:
            # Non-axis-aligned or degenerate corner; fall back to dogbone.
            reliefs.append(CircleRelief(center=curr, diameter=bit_diameter))
            continue
        cx, cy = curr
        x0, x1 = sorted((cx, cx + sx * bit_diameter))
        y0, y1 = sorted((cy, cy + sy * bit_diameter))
        rect: Path = [
            (x0, y0),
            (x1, y0),
            (x1, y1),
            (x0, y1),
            (x0, y0),
        ]
        reliefs.append(RectRelief(outline=rect))
    return reliefs


def translate_relief(relief: Relief, dx: float, dy: float) -> Relief:
    """Return a copy of ``relief`` translated by (dx, dy)."""

    if isinstance(relief, CircleRelief):
        return CircleRelief(center=(relief.center[0] + dx, relief.center[1] + dy),
                            diameter=relief.diameter)
    return RectRelief(outline=[(p[0] + dx, p[1] + dy) for p in relief.outline])


def translate_reliefs(reliefs: Iterable[Relief], dx: float, dy: float) -> list[Relief]:
    return [translate_relief(r, dx, dy) for r in reliefs]
