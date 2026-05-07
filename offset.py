"""Offset a closed CCW polygon by a perpendicular distance.

Positive ``d`` moves the boundary OUTWARD (away from the interior, which
for a CCW polygon sits on the LEFT of the travel direction). Negative
``d`` moves it inward.

Uses a simple miter join: each edge is shifted by ``d`` along its
outward normal, and consecutive shifted edges are intersected to find
the new vertex. That gives correct results for convex AND concave
corners (at concave corners the miter point lands on the exterior side,
which is exactly where the tool needs to sit for an outside profile).
A miter limit clamps degenerate spikes at very acute angles.

Self-intersection handling is intentionally out of scope; for the
panels we generate (which are simple, axis-aligned, with right angles
only) the miter offset is well-behaved.
"""

from __future__ import annotations

import math
from typing import Sequence

from .geometry import Path, Point


def offset_ccw_closed(
    pts: Sequence[Point],
    d: float,
    miter_limit: float = 4.0,
    tol: float = 1e-9,
) -> Path:
    """Offset a CCW closed polyline by ``d`` (outward if d > 0).

    ``pts`` must be closed (first point repeated as last). The result
    is also closed. ``miter_limit`` is the maximum allowed ratio of
    miter extension to |d| before falling back to a bevel join.
    """

    if len(pts) < 3:
        raise ValueError("polyline must have at least 3 distinct points")
    if abs(d) < tol:
        return list(pts)

    # Work on the open version (drop duplicated closing point).
    open_pts = list(pts)
    if (abs(open_pts[0][0] - open_pts[-1][0]) < tol and
            abs(open_pts[0][1] - open_pts[-1][1]) < tol):
        open_pts = open_pts[:-1]

    # Dedupe any consecutive duplicates so normals are well-defined.
    cleaned: list[Point] = []
    for p in open_pts:
        if not cleaned or abs(p[0] - cleaned[-1][0]) > tol or abs(p[1] - cleaned[-1][1]) > tol:
            cleaned.append(p)
    open_pts = cleaned
    n = len(open_pts)
    if n < 3:
        raise ValueError("polyline collapses to fewer than 3 points after dedup")

    # Compute each edge's shifted start/end plus its outward unit normal.
    shifted: list[tuple[Point, Point, Point]] = []
    for i in range(n):
        p1 = open_pts[i]
        p2 = open_pts[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < tol:
            continue
        # Outward normal for a CCW polygon = RIGHT of travel = (dy, -dx) / L.
        nx, ny = dy / length, -dx / length
        q1 = (p1[0] + d * nx, p1[1] + d * ny)
        q2 = (p2[0] + d * nx, p2[1] + d * ny)
        shifted.append((q1, q2, (nx, ny)))

    m = len(shifted)
    new_pts: list[Point] = []
    abs_d = abs(d)
    limit = miter_limit * abs_d
    for i in range(m):
        a1, a2, na = shifted[(i - 1) % m]
        b1, b2, nb = shifted[i]
        pt = _intersect_lines(a1, a2, b1, b2, tol)
        if pt is None:
            # Parallel offset lines (edges collinear); skip the
            # degenerate vertex by using the shared endpoint.
            new_pts.append(b1)
            continue
        # Miter clamp: if the new vertex is unreasonably far from the
        # original corner, bevel by inserting both shifted endpoints.
        orig_corner = open_pts[i]
        if math.hypot(pt[0] - orig_corner[0], pt[1] - orig_corner[1]) > limit:
            new_pts.append(a2)
            new_pts.append(b1)
        else:
            new_pts.append(pt)

    if not new_pts:
        raise ValueError("offset produced an empty polyline")

    # Close the result.
    new_pts.append(new_pts[0])
    return new_pts


def _intersect_lines(
    p1: Point, p2: Point, p3: Point, p4: Point, tol: float,
) -> Point | None:
    """Intersect the lines (p1,p2) and (p3,p4), extended as needed."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < tol:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
