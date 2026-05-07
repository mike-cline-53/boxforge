"""Through-tenon joinery: tabs on the bottom/lid, matching slots in the sides.

A "tab" is a rectangular extrusion that sticks out along the edge's local
-Y axis. A "slot" is a rectangular notch cut inward along local +Y; its
depth equals the material thickness, so the mating tab passes all the
way through the sheet.

Both edge generators return open polylines starting at (0, 0) and ending
at (length, 0). The edge body between features is flat.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ..geometry import Path


def tab_positions(
    edge_length: float,
    tab_count: int,
    tab_width: float,
) -> list[tuple[float, float]]:
    """Distribute ``tab_count`` tabs evenly along an edge of ``edge_length``.

    Returns a list of ``(start, end)`` x-ranges for each tab, with equal
    gaps between each pair of tabs and at the ends of the edge.
    """

    if tab_count <= 0:
        return []
    if tab_width <= 0:
        raise ValueError(f"tab_width must be > 0, got {tab_width}")
    usable = edge_length - tab_count * tab_width
    if usable <= 0:
        raise ValueError(
            f"{tab_count} tabs of {tab_width} mm do not fit on an edge of "
            f"{edge_length} mm (need gaps between them)"
        )
    gap = usable / (tab_count + 1)
    spans: list[tuple[float, float]] = []
    for i in range(tab_count):
        start = gap + i * (tab_width + gap)
        spans.append((start, start + tab_width))
    return spans


def _featured_edge(
    length: float,
    t: float,
    features: Sequence[tuple[float, float]],
    y_feature: float,
) -> Path:
    """Straight edge with rectangular features along it.

    ``features`` are ``(start_x, end_x)`` spans, strictly within ``(0, length)``
    and non-overlapping. ``y_feature`` is the depth of each feature off the
    baseline (negative for tabs sticking out, positive for notches cut in).
    """

    if length <= 0:
        raise ValueError(f"edge length must be > 0, got {length}")
    if t <= 0:
        raise ValueError(f"material thickness must be > 0, got {t}")

    path: Path = [(0.0, 0.0)]
    x_cur = 0.0
    eps = 1e-9
    for start, end in sorted(features):
        if start < -eps or end > length + eps:
            raise ValueError(
                f"feature ({start}, {end}) falls outside edge [0, {length}]"
            )
        if start < x_cur - eps:
            raise ValueError(
                f"feature ({start}, {end}) overlaps previous feature at {x_cur}"
            )
        if start > x_cur + eps:
            path.append((start, 0.0))
        path.append((start, y_feature))
        path.append((end, y_feature))
        path.append((end, 0.0))
        x_cur = end
    if x_cur < length - eps:
        path.append((length, 0.0))
    return path


def slotted_edge(length: float, t: float, slots: Iterable[tuple[float, float]]) -> Path:
    """Straight edge with rectangular through-slots cut INTO the panel body."""
    return _featured_edge(length, t, list(slots), y_feature=+t)


def tabbed_edge(length: float, t: float, tabs: Iterable[tuple[float, float]]) -> Path:
    """Straight edge with rectangular tabs extending OUT of the panel body."""
    return _featured_edge(length, t, list(tabs), y_feature=-t)
