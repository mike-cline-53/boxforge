"""Generate G-code for a placed panel layout.

What this module does:

1. For each panel, take the DXF outline (which is the KEPT part boundary)
   and offset it outward by ``bit_radius + kerf/2`` to produce the actual
   tool toolpath. Interior cutouts (corner reliefs - dogbone circles,
   tbone rectangles) are offset inward by the same amount.
2. Choose a start point on each toolpath (midpoint of the longest
   straight segment) so the ramped plunge has room.
3. Decide the order parts get cut in. A greedy nearest-neighbor from
   (0, 0) keeps non-cutting travel short without pretending to be a real
   TSP solver.
4. When tabs are enabled, find straight segments of the toolpath that
   are at least ``tab_min_edge_length`` mm long and plant a tab at
   ``tab_corner_margin`` mm from each end of that segment.
5. Emit the gcode: a probe/home preamble, then for each part cut N
   passes at increasing depth, with a ramped plunge at the start of
   each pass. On the final pass every tab is a V-ramp up to
   ``-(total_depth - tab_height)`` and straight back down.

Coordinate conventions: +X right, +Y up, +Z up. Z=0 is the material
surface, cuts are negative Z. Units are mm (G21). The machine origin
(0, 0) is the sheet's bottom-left corner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .config import CamSpec, CncSpec
from .corner_relief import CircleRelief, RectRelief, Relief
from .geometry import Point, bounding_box
from .layout import PlacedPanel
from .offset import offset_ccw_closed


# ---------------------------------------------------------------------------
# toolpath data model
# ---------------------------------------------------------------------------

@dataclass
class Tab:
    """A holding tab placed at an arc-length position along a toolpath."""

    s_center: float  # arc-length along the toolpath, from its first point
    half_length: float  # half of the tab's horizontal footprint


@dataclass
class Toolpath:
    """A closed polyline the bit will trace, plus its planned tabs and
    chosen start index."""

    name: str
    pts: list[Point]  # closed: pts[0] == pts[-1]
    tabs: list[Tab]
    start_index: int  # index into pts[:-1] where cutting begins


# ---------------------------------------------------------------------------
# straight-segment extraction
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """A maximal run of collinear edges on a closed polyline."""

    start_idx: int  # index of first vertex in pts
    end_idx: int    # index of last vertex in the run
    s_start: float  # arc length at start vertex
    s_end: float    # arc length at end vertex
    dx: float       # unit direction x
    dy: float       # unit direction y

    @property
    def length(self) -> float:
        return self.s_end - self.s_start


def _cumulative_arc(pts: Sequence[Point]) -> list[float]:
    s = [0.0]
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        s.append(s[-1] + math.hypot(dx, dy))
    return s


def _segment_direction(a: Point, b: Point) -> tuple[float, float] | None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return None
    return (dx / L, dy / L)


def collinear_segments(pts: Sequence[Point], angle_tol_deg: float = 0.5) -> list[Segment]:
    """Collapse consecutive collinear edges into maximal straight runs.

    ``pts`` must be closed (first == last). The returned segments each
    span from ``start_idx`` to ``end_idx`` inclusive, and together
    cover the whole polyline end-to-end with no gaps.
    """

    if len(pts) < 3:
        raise ValueError("polyline needs at least 2 distinct points")
    s_arc = _cumulative_arc(pts)
    cos_tol = math.cos(math.radians(angle_tol_deg))

    segments: list[Segment] = []
    i = 0
    n_edges = len(pts) - 1  # pts is closed so last == first
    while i < n_edges:
        d0 = _segment_direction(pts[i], pts[i + 1])
        if d0 is None:
            i += 1
            continue
        start_idx = i
        j = i + 1
        while j < n_edges:
            dj = _segment_direction(pts[j], pts[j + 1])
            if dj is None:
                break
            if dj[0] * d0[0] + dj[1] * d0[1] < cos_tol:
                break
            j += 1
        segments.append(Segment(
            start_idx=start_idx,
            end_idx=j,
            s_start=s_arc[start_idx],
            s_end=s_arc[j],
            dx=d0[0],
            dy=d0[1],
        ))
        i = j
    return segments


# ---------------------------------------------------------------------------
# tab planning
# ---------------------------------------------------------------------------

def _body_bounds(pts: Sequence[Point], segments: list[Segment]) -> tuple[float, float, float, float]:
    """Return (x0, y0, x1, y1) of the panel's BODY rectangle - the two
    dominant horizontal Y-lines and two dominant vertical X-lines, by
    total segment length. For panels with tabs/fingers sticking out of
    the body, the outer polyline bbox passes through the protrusion
    tips (which are short); the body rectangle is the rectangle formed
    by the edge-lines with the most total length on them, which is
    much more useful for tab placement."""

    horiz_by_y: dict[int, float] = {}
    vert_by_x: dict[int, float] = {}
    y_values: dict[int, float] = {}
    x_values: dict[int, float] = {}
    for seg in segments:
        if abs(seg.dy) < 0.01:
            a = pts[seg.start_idx]
            key = int(round(a[1] * 100))
            horiz_by_y[key] = horiz_by_y.get(key, 0.0) + seg.length
            y_values[key] = a[1]
        elif abs(seg.dx) < 0.01:
            a = pts[seg.start_idx]
            key = int(round(a[0] * 100))
            vert_by_x[key] = vert_by_x.get(key, 0.0) + seg.length
            x_values[key] = a[0]

    # Fall back to full bbox if we somehow don't have enough data.
    xs_all = [p[0] for p in pts]
    ys_all = [p[1] for p in pts]

    top_ys = sorted(horiz_by_y.items(), key=lambda kv: kv[1], reverse=True)[:2]
    top_xs = sorted(vert_by_x.items(), key=lambda kv: kv[1], reverse=True)[:2]
    if len(top_ys) < 2 or len(top_xs) < 2:
        return min(xs_all), min(ys_all), max(xs_all), max(ys_all)
    ys_body = sorted(y_values[k] for k, _ in top_ys)
    xs_body = sorted(x_values[k] for k, _ in top_xs)
    return xs_body[0], ys_body[0], xs_body[1], ys_body[1]


def plan_tabs(
    pts: Sequence[Point],
    min_edge_length: float,
    corner_margin: float,
    tab_half_length: float,
) -> list[Tab]:
    """Place tabs near the four corners of the panel's BODY rectangle.

    For each of the eight "candidate" positions (one inset from each
    body corner along each of its two adjacent body edges), find the
    polyline straight segment that sits on that body edge AND contains
    that position. Plant a tab there iff that segment is at least
    ``min_edge_length`` long. Short-segment body edges (e.g. a heavily
    fingered wall) are skipped automatically.

    This yields at most 8 tabs per panel.
    """

    segments = collinear_segments(pts)
    if not segments:
        return []

    x0, y0, x1, y1 = _body_bounds(pts, segments)

    inset = corner_margin + tab_half_length
    # (target_x, target_y, needs_horizontal_segment)
    candidates: list[tuple[float, float, bool]] = [
        (x0 + inset, y0, True),
        (x1 - inset, y0, True),
        (x0 + inset, y1, True),
        (x1 - inset, y1, True),
        (x0, y0 + inset, False),
        (x0, y1 - inset, False),
        (x1, y0 + inset, False),
        (x1, y1 - inset, False),
    ]

    EDGE_TOL = 0.5  # mm - how close the segment must sit to the bbox edge
    tabs: list[Tab] = []
    seen: set[int] = set()
    for tx, ty, horizontal in candidates:
        best: Segment | None = None
        for seg in segments:
            if horizontal and abs(seg.dy) > 0.01:
                continue
            if not horizontal and abs(seg.dx) > 0.01:
                continue
            a = pts[seg.start_idx]
            b = pts[seg.end_idx]
            if horizontal:
                if abs(a[1] - ty) > EDGE_TOL:
                    continue
                lo, hi = sorted((a[0], b[0]))
                if not (lo - EDGE_TOL <= tx <= hi + EDGE_TOL):
                    continue
            else:
                if abs(a[0] - tx) > EDGE_TOL:
                    continue
                lo, hi = sorted((a[1], b[1]))
                if not (lo - EDGE_TOL <= ty <= hi + EDGE_TOL):
                    continue
            best = seg
            break
        if best is None or best.length < min_edge_length:
            continue
        a = pts[best.start_idx]
        # Arc-length along the polyline at the target point.
        dist = (tx - a[0]) * best.dx + (ty - a[1]) * best.dy
        s_center = best.s_start + dist
        # Avoid placing two tabs at the same s_center (can happen when a
        # short bbox edge has only one segment and both of its adjacent
        # candidates collapse onto the same point).
        key = int(round(s_center * 100))
        if key in seen:
            continue
        seen.add(key)
        tabs.append(Tab(s_center=s_center, half_length=tab_half_length))
    tabs.sort(key=lambda t: t.s_center)
    return tabs


# ---------------------------------------------------------------------------
# start-point selection
# ---------------------------------------------------------------------------

def rotate_to_longest_midpoint(pts: Sequence[Point]) -> list[Point]:
    """Return a new CLOSED polyline that starts at the midpoint of its
    longest straight segment.

    We insert a fresh vertex at that midpoint (so the start really is
    the middle of the edge, not whichever existing vertex happens to
    be closest), then rotate the polyline so that new vertex is first.
    """

    segments = collinear_segments(pts)
    if not segments:
        return list(pts)
    longest = max(segments, key=lambda s: s.length)

    # Midpoint of the longest segment in XY.
    a = pts[longest.start_idx]
    b = pts[longest.end_idx]
    mid = (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))

    # Open version.
    open_pts = list(pts[:-1]) if pts[0] == pts[-1] else list(pts)
    # Insert ``mid`` between start_idx and end_idx. Since the longest
    # segment spans a straight run of (potentially many) collinear
    # vertices, pick the last one strictly before the midpoint along
    # the segment direction and insert right after it.
    dx, dy = longest.dx, longest.dy
    insert_after = longest.start_idx
    base = open_pts[longest.start_idx]
    mid_along = (mid[0] - base[0]) * dx + (mid[1] - base[1]) * dy
    for k in range(longest.start_idx, longest.end_idx):
        proj = (open_pts[k][0] - base[0]) * dx + (open_pts[k][1] - base[1]) * dy
        if proj < mid_along - 1e-9:
            insert_after = k
    new_list = open_pts[:insert_after + 1] + [mid] + open_pts[insert_after + 1:]

    # Rotate so ``mid`` is first.
    start_idx = insert_after + 1
    rotated = new_list[start_idx:] + new_list[:start_idx]
    rotated.append(rotated[0])
    return rotated


# ---------------------------------------------------------------------------
# toolpath construction from a placed panel
# ---------------------------------------------------------------------------

def _translate_path(pts: Iterable[Point], dx: float, dy: float) -> list[Point]:
    return [(p[0] + dx, p[1] + dy) for p in pts]


def build_panel_toolpaths(
    placed: PlacedPanel,
    cnc: CncSpec,
    cam: CamSpec,
) -> tuple[Toolpath, list[Toolpath]]:
    """Return the (outer_profile_toolpath, relief_toolpaths) for a
    single placed panel, in sheet-absolute coordinates.

    The outer profile is offset outward by ``bit_radius + kerf/2``.
    Circle reliefs whose diameter equals the bit diameter collapse to a
    single plunge point; larger circles stay as circle toolpaths.
    Rectangular tbone reliefs are offset inward by the same amount.
    """

    bit_radius = cnc.bit_diameter / 2.0
    offset = bit_radius + cnc.kerf / 2.0

    outline_abs = _translate_path(placed.panel.outline, placed.dx, placed.dy)
    tool_pts = offset_ccw_closed(outline_abs, +offset)
    tool_pts = rotate_to_longest_midpoint(tool_pts)

    tabs: list[Tab] = []
    if cam.use_tabs:
        tabs = plan_tabs(
            tool_pts,
            min_edge_length=cam.tab_min_edge_length,
            corner_margin=cam.tab_corner_margin,
            tab_half_length=cam.tab_ramp_length,
        )

    outer = Toolpath(name=placed.panel.name, pts=tool_pts, tabs=tabs, start_index=0)

    relief_paths: list[Toolpath] = []
    for i, r in enumerate(placed.panel.reliefs):
        rp = _relief_toolpath(r, placed.dx, placed.dy, cnc, offset)
        if rp is None:
            continue
        rp.name = f"{placed.panel.name}.relief{i}"
        relief_paths.append(rp)
    return outer, relief_paths


def _relief_toolpath(
    r: Relief,
    dx: float,
    dy: float,
    cnc: CncSpec,
    offset: float,
) -> Toolpath | None:
    """Build a toolpath for one interior relief, or None if the relief
    is smaller than the bit (no motion needed, just a plunge -
    callers handle that as a single-point toolpath)."""

    if isinstance(r, CircleRelief):
        cx, cy = r.center[0] + dx, r.center[1] + dy
        radius = r.diameter / 2.0
        if radius <= offset + 1e-6:
            # Bit is larger than the relief - just plunge at the centre.
            return Toolpath(name="", pts=[(cx, cy), (cx, cy)], tabs=[], start_index=0)
        r_tool = radius - offset
        pts = _sample_circle(cx, cy, r_tool, n=64)
        return Toolpath(name="", pts=pts, tabs=[], start_index=0)

    # RectRelief: rectangular pocket, offset inward.
    outline_abs = _translate_path(r.outline, dx, dy)
    try:
        inner = offset_ccw_closed(outline_abs, -offset)
    except ValueError:
        # Rectangle is smaller than 2 * offset - plunge at centre.
        x0, y0, x1, y1 = bounding_box(outline_abs)
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        return Toolpath(name="", pts=[(cx, cy), (cx, cy)], tabs=[], start_index=0)
    return Toolpath(name="", pts=inner, tabs=[], start_index=0)


def _sample_circle(cx: float, cy: float, r: float, n: int) -> list[Point]:
    pts: list[Point] = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return pts


# ---------------------------------------------------------------------------
# part ordering
# ---------------------------------------------------------------------------

def order_toolpaths_nearest_neighbor(
    paths: list[Toolpath],
    origin: Point = (0.0, 0.0),
) -> list[Toolpath]:
    """Greedy nearest-neighbor: repeatedly pick the path whose start
    point is closest to the current position, pretending we jump to
    that path's end point when done with it (which is the same as the
    start for closed paths)."""

    remaining = list(paths)
    ordered: list[Toolpath] = []
    cursor = origin
    while remaining:
        best_i = 0
        best_d = math.inf
        for i, p in enumerate(remaining):
            s = p.pts[0]
            d = math.hypot(s[0] - cursor[0], s[1] - cursor[1])
            if d < best_d:
                best_d = d
                best_i = i
        picked = remaining.pop(best_i)
        ordered.append(picked)
        cursor = picked.pts[0]  # closed path ends where it began
    return ordered


# ---------------------------------------------------------------------------
# gcode emission
# ---------------------------------------------------------------------------

def _fmt_xy(p: Point) -> str:
    return f"X{p[0]:.4f} Y{p[1]:.4f}"


def _interp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _point_at_arc(pts: Sequence[Point], s_arc: Sequence[float], s: float) -> tuple[Point, int]:
    """Return the point at arc-length ``s`` along the polyline and the
    index of the edge it falls on (i.e. between ``pts[i]`` and
    ``pts[i+1]``)."""

    total = s_arc[-1]
    s = max(0.0, min(total, s))
    # Binary search for the edge.
    lo, hi = 0, len(s_arc) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if s_arc[mid] <= s:
            lo = mid
        else:
            hi = mid
    seg_len = s_arc[hi] - s_arc[lo]
    if seg_len < 1e-9:
        return pts[lo], lo
    t = (s - s_arc[lo]) / seg_len
    return _interp(pts[lo], pts[hi], t), lo


def _emit_pass(
    lines: list[str],
    path: Toolpath,
    z_prev: float,
    z_now: float,
    cam: CamSpec,
    is_final_pass: bool,
) -> None:
    """Emit one pass of one toolpath.

    Z as a function of arc-length ``s`` is defined piecewise:
    - During the plunge: linear from ``z_prev`` at s=0 to ``z_now`` at
      s=``ramp_len``.
    - Inside a tab (final pass only): linear from ``z_now`` at the tab
      start up to ``z_tab`` at the tab centre, then linear back down
      to ``z_now`` at the tab end.
    - Everywhere else: ``z_now``.

    We evaluate this Z function at every polyline vertex PLUS every
    "keypoint" (plunge-end, tab start/centre/end) and emit G01 moves to
    each keypoint in arc-length order.
    """

    pts = path.pts
    s_arc = _cumulative_arc(pts)
    total_s = s_arc[-1]
    if total_s <= 1e-9:
        return
    ramp_len = min(cam.plunge_ramp_length, total_s * 0.5)

    # Build the list of "breakpoint" arc-lengths where the Z rule
    # changes slope: start, plunge-end, tab start/centre/end, final.
    breakpoints: list[float] = [0.0, ramp_len]
    tab_ranges: list[tuple[float, float, float]] = []  # (s_start, s_centre, s_end)
    if is_final_pass and path.tabs:
        z_tab = -(cam.total_depth - cam.tab_height)
        for tab in path.tabs:
            s_start = tab.s_center - tab.half_length
            s_end = tab.s_center + tab.half_length
            if s_start < ramp_len or s_end > total_s:
                # Skip tabs that collide with the plunge ramp or overrun.
                continue
            tab_ranges.append((s_start, tab.s_center, s_end))
            breakpoints.extend([s_start, tab.s_center, s_end])
    else:
        z_tab = z_now  # unused
    breakpoints.append(total_s)

    def z_of(s: float) -> float:
        if s <= 0.0:
            return z_prev
        if s < ramp_len:
            return z_prev + (z_now - z_prev) * (s / ramp_len)
        for s0, sc, s1 in tab_ranges:
            if s0 <= s <= sc:
                if sc == s0:
                    return z_tab
                return z_now + (z_tab - z_now) * ((s - s0) / (sc - s0))
            if sc < s <= s1:
                if s1 == sc:
                    return z_now
                return z_tab + (z_now - z_tab) * ((s - sc) / (s1 - sc))
        return z_now

    # Merge the polyline vertex arc-lengths with the breakpoints.
    merged: list[float] = sorted(set(breakpoints) | set(s_arc))
    merged = [s for s in merged if -1e-6 <= s <= total_s + 1e-6]

    feed_cut = cam.feed_cut
    prev_xy: Point = pts[0]
    prev_z = z_prev
    for s in merged:
        if s < 1e-9:
            continue
        pt, _ = _point_at_arc(pts, s_arc, s)
        z = z_of(s)
        # Skip zero-length moves.
        if (abs(pt[0] - prev_xy[0]) < 1e-6 and
                abs(pt[1] - prev_xy[1]) < 1e-6 and
                abs(z - prev_z) < 1e-6):
            continue
        parts = [f"G01 {_fmt_xy(pt)}"]
        if abs(z - prev_z) > 1e-6:
            parts.append(f"Z{z:.4f}")
        parts.append(f"F{feed_cut:.0f}")
        lines.append(" ".join(parts))
        prev_xy = pt
        prev_z = z


def emit_gcode(
    placed: list[PlacedPanel],
    cnc: CncSpec,
    cam: CamSpec,
    project_name: str = "boxforge",
) -> str:
    """Return the full gcode for the layout as a string."""

    # Build toolpaths: outer profile + interior reliefs for each panel.
    all_paths: list[Toolpath] = []
    untabbed: list[str] = []
    for p in placed:
        outer, reliefs = build_panel_toolpaths(p, cnc, cam)
        if cam.use_tabs and not outer.tabs:
            untabbed.append(outer.name)
        all_paths.append(outer)
        all_paths.extend(reliefs)
    if untabbed:
        import warnings
        warnings.warn(
            "No straight edges long enough for tabs on: "
            + ", ".join(untabbed)
            + f" (tab_min_edge_length={cam.tab_min_edge_length:.0f} mm)."
            " These parts will cut free. Lower tab_min_edge_length if needed.",
            stacklevel=2,
        )
    ordered = order_toolpaths_nearest_neighbor(all_paths)

    n_passes = max(1, math.ceil(cam.total_depth / cam.pass_depth))
    depths = [min(cam.total_depth, cam.pass_depth * (i + 1)) for i in range(n_passes)]

    lines: list[str] = []
    # ---- header ----
    lines.append(f"(Project {project_name})")
    lines.append(f"(Generated by boxforge)")
    lines.append(f"(Material thickness cut: {cam.total_depth:.3f} mm in {n_passes} passes)")
    lines.append(f"(Bit diameter: {cnc.bit_diameter:.3f} mm, kerf: {cnc.kerf:.3f} mm)")
    if cam.use_tabs:
        lines.append(
            f"(Holding tabs: height {cam.tab_height:.2f} mm, "
            f"ramp {cam.tab_ramp_length:.2f} mm, "
            f"min edge {cam.tab_min_edge_length:.0f} mm)"
        )
    lines.append("")
    lines.append("G21")  # mm
    lines.append("G90")  # absolute positioning
    lines.append("G94")  # feed rate per minute
    lines.extend(cam.preamble.strip().splitlines())
    lines.append("")

    # ---- per-part ----
    for part_i, path in enumerate(ordered, start=1):
        lines.append(f"(No. {part_i}: {path.name})")
        start = path.pts[0]
        lines.append(f"G00 {_fmt_xy(start)} Z{cam.safe_z:.4f} F{cam.feed_rapid:.0f}")
        lines.append(f"G01 Z0.0000 F{cam.feed_plunge:.0f}")
        prev_z = 0.0
        for pass_i, depth in enumerate(depths):
            z_now = -depth
            is_final = (pass_i == len(depths) - 1)
            _emit_pass(lines, path, prev_z, z_now, cam, is_final)
            prev_z = z_now
        lines.append(f"G00 Z{cam.safe_z:.4f} F{cam.feed_rapid:.0f}")
        lines.append("")

    # ---- footer ----
    lines.extend(cam.postamble.strip().splitlines())
    lines.append("")
    return "\n".join(lines)


def write_gcode(
    placed: list[PlacedPanel],
    out_path: str,
    cnc: CncSpec,
    cam: CamSpec,
    project_name: str = "boxforge",
) -> None:
    text = emit_gcode(placed, cnc, cam, project_name=project_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
