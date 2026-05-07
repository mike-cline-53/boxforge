"""Assemble a complete box from the config specs.

Phase 1 convention (finger joints on vertical corners, through-tenons
between the bottom/lid and the four walls):

- Front and back panels are the "dominant" pair horizontally. Their flat
  width equals the box's outside width W. Both vertical edges have OUTIE
  finger joints (tabs extend outward by material thickness).
- Left and right panels are insets between front and back. Their flat
  width equals D - 2t. Both vertical edges have INNIE finger joints
  (notches cut inward, eating the body corners by t). The top and
  bottom straight edges on these panels are shortened by t on each end
  to meet the notched corners cleanly.
- The bottom panel sits inside the box, footprint (W - 2t) x (D - 2t),
  with rectangular TABS extending out by t on all four edges. Each side
  panel has matching rectangular SLOTS (notches) cut into its bottom
  edge, through which the bottom's tabs protrude. The lid (when
  present) mirrors the bottom at the top.

Axis convention: in every panel's flat frame, +X is along what will be
"width" when cut, +Y is along "height". The bottom-to-wall tabs face
what will be the BOTTOM of the assembled box.
"""

from __future__ import annotations

from typing import Sequence

from .config import BoxSpec, CncSpec, JoinerySpec, MaterialSpec
from .corner_relief import RectRelief, generate_relief
from .geometry import (
    Path,
    dedupe_consecutive,
    place_edge_on_rect,
    stitch_edges,
    translate_path,
)
from .joinery.finger import finger_edge, straight_edge
from .joinery.slots import slotted_edge, tab_positions, tabbed_edge
from .panel import Panel


# ---------------------------------------------------------------------------
# side panels (front, back, left, right)
# ---------------------------------------------------------------------------

def _side_panel(
    name: str,
    body_w: float,
    body_h: float,
    vertical_role: str,
    horizontal_slots: Sequence[tuple[float, float]],
    has_top_slots: bool,
    top_slots: Sequence[tuple[float, float]],
    material: MaterialSpec,
    joinery: JoinerySpec,
    cnc: CncSpec,
    interior_cuts: Sequence[RectRelief] = (),
) -> Panel:
    """Build one of the four side panels.

    ``vertical_role`` is "outie" for front/back panels or "innie" for
    left/right panels; it controls the finger joints on the vertical
    edges and the corner-inset of the horizontal edges.

    ``horizontal_slots`` is a list of (start_x, end_x) spans in the
    bottom-edge's local frame (so slot 0 starts at that edge's x=0, not
    in panel frame). ``top_slots`` is analogous for the top edge and is
    only used when ``has_top_slots`` is True (i.e. when the box has a
    lid).

    ``interior_cuts`` is an optional list of rectangular through-holes
    (mortises) in panel-frame coordinates. They are emitted on the
    CUT_INSIDE layer alongside corner reliefs.
    """

    t = material.thickness
    fw = joinery.finger_width

    # Innie panels have their horizontal edges shortened by t on each end,
    # because the corner notches eat the outer t at each vertical edge.
    corner_inset = t if vertical_role == "innie" else 0.0
    horiz_len = body_w - 2.0 * corner_inset

    bottom_local = slotted_edge(horiz_len, t, horizontal_slots)
    if has_top_slots:
        top_local = slotted_edge(horiz_len, t, top_slots)
    else:
        top_local = straight_edge(horiz_len)

    right_local = finger_edge(body_h, t, fw, vertical_role)  # type: ignore[arg-type]
    left_local = finger_edge(body_h, t, fw, vertical_role)  # type: ignore[arg-type]

    # Place each edge in panel frame.
    bottom_p = translate_path(
        place_edge_on_rect(bottom_local, horiz_len, body_h, "bottom"),
        corner_inset,
        0.0,
    )
    right_p = place_edge_on_rect(right_local, body_w, body_h, "right")
    top_p = translate_path(
        place_edge_on_rect(top_local, horiz_len, body_h, "top"),
        corner_inset,
        0.0,
    )
    left_p = place_edge_on_rect(left_local, body_w, body_h, "left")

    outline = stitch_edges([bottom_p, right_p, top_p, left_p])
    if outline[0] != outline[-1]:
        outline.append(outline[0])
    outline = dedupe_consecutive(outline)

    reliefs = generate_relief(outline, joinery.corner_relief, cnc.bit_diameter)
    reliefs = list(reliefs) + list(interior_cuts)
    return Panel(name=name, outline=outline, reliefs=reliefs)


# ---------------------------------------------------------------------------
# bottom / lid panels
# ---------------------------------------------------------------------------

def _bottom_panel(
    name: str,
    body_w: float,
    body_h: float,
    tab_count: int,
    tab_width: float,
    t: float,
) -> Panel:
    """Rectangle with tabs sticking out of all four edges."""

    fb_tabs = tab_positions(body_w, tab_count, tab_width)  # front + back
    lr_tabs = tab_positions(body_h, tab_count, tab_width)  # left + right

    bottom_local = tabbed_edge(body_w, t, fb_tabs)
    right_local = tabbed_edge(body_h, t, lr_tabs)
    top_local = tabbed_edge(body_w, t, fb_tabs)
    left_local = tabbed_edge(body_h, t, lr_tabs)

    bottom_p = place_edge_on_rect(bottom_local, body_w, body_h, "bottom")
    right_p = place_edge_on_rect(right_local, body_w, body_h, "right")
    top_p = place_edge_on_rect(top_local, body_w, body_h, "top")
    left_p = place_edge_on_rect(left_local, body_w, body_h, "left")

    outline = stitch_edges([bottom_p, right_p, top_p, left_p])
    if outline[0] != outline[-1]:
        outline.append(outline[0])
    outline = dedupe_consecutive(outline)

    return Panel(name=name, outline=outline, reliefs=[])


# ---------------------------------------------------------------------------
# slot positions: translate a bottom tab's local span into a slot span in
# the mating side panel's bottom-edge local frame.
# ---------------------------------------------------------------------------

def _slots_for_front_back(
    bottom_body_w: float,
    tab_count: int,
    tab_width: float,
    t: float,
) -> list[tuple[float, float]]:
    """Slots on the bottom edge of the front (or back) side panel.

    The bottom panel's body runs from box x = t to x = W - t. Its tabs
    on the front/back edges are at bottom-local x positions returned by
    tab_positions(W-2t, ...). In the front-panel frame those same tabs
    sit at box x + t (since the front panel spans box x in [0, W]), and
    the slot edge's local frame matches the front panel's bottom edge
    exactly. So each bottom tab span (a, b) becomes a slot span
    (a + t, b + t).
    """

    spans = tab_positions(bottom_body_w, tab_count, tab_width)
    return [(a + t, b + t) for a, b in spans]


def _slots_for_left_right(
    bottom_body_h: float,
    tab_count: int,
    tab_width: float,
    t: float,
) -> list[tuple[float, float]]:
    """Slots on the bottom edge of the left (or right) side panel.

    The bottom panel's left/right tabs are positioned along the bottom's
    y-axis at spans (a, b) in the bottom's frame. The left panel's
    bottom edge runs along box y (shifted by t because the panel itself
    sits between box y = t and y = D - t). After the innie corner inset
    of t on each end, the effective edge length equals D - 4t, starting
    at panel-frame x = t.

    Bottom's y = 0 sits at box y = t, which sits at the left panel's
    edge-local x = 0 (because we pass ``corner_inset`` separately as the
    edge's placement offset). So each bottom tab y-span (a, b) becomes
    a left-panel slot x-span (a - t, b - t) in the shortened edge's
    local frame.
    """

    spans = tab_positions(bottom_body_h, tab_count, tab_width)
    return [(a - t, b - t) for a, b in spans]


# ---------------------------------------------------------------------------
# horizontal-divider mortises
# ---------------------------------------------------------------------------

def _mortise_rect(x0: float, x1: float, y0: float, y1: float) -> RectRelief:
    """Build a CCW-closed rectangular RectRelief from min/max corners."""

    return RectRelief(outline=[
        (x0, y0),
        (x1, y0),
        (x1, y1),
        (x0, y1),
        (x0, y0),
    ])


def _shelf_mortises_for_front_back(
    z: float,
    bottom_body_w: float,
    tab_count: int,
    tab_width: float,
    t: float,
) -> list[RectRelief]:
    """Mortises in the front (or back) panel for one shelf at height ``z``.

    Front-panel frame is ``[0, W] x [0, H]``. Each mortise spans the same
    x-range as the matching bottom-edge slot (a + t, b + t), and from
    y = z to y = z + t (the shelf has thickness t and sits at height z).
    """

    spans = _slots_for_front_back(bottom_body_w, tab_count, tab_width, t)
    return [_mortise_rect(a, b, z, z + t) for a, b in spans]


def _shelf_mortises_for_left_right(
    z: float,
    bottom_body_h: float,
    tab_count: int,
    tab_width: float,
    t: float,
) -> list[RectRelief]:
    """Mortises in the left (or right) panel for one shelf at height ``z``.

    Left/right panel frame is ``[0, D - 2t] x [0, H]``. ``_slots_for_left_right``
    returns spans ``(a - t, b - t)`` in the shortened bottom-edge's local frame
    (where ``(a, b)`` are tab positions on the shelf body of length
    ``D - 2t``). The bottom edge is placed in the panel with a corner inset of
    ``t``, so adding ``t`` back maps each span into panel-frame x as ``(a, b)``.
    """

    edge_spans = _slots_for_left_right(bottom_body_h, tab_count, tab_width, t)
    return [
        _mortise_rect(a + t, b + t, z, z + t)
        for a, b in edge_spans
    ]


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def build_box(
    box: BoxSpec,
    material: MaterialSpec,
    joinery: JoinerySpec,
    cnc: CncSpec,
) -> list[Panel]:
    """Generate the list of panels for a box.

    Returns panels in the order: front, back, left, right, bottom, (lid).
    """

    t = material.thickness
    W, D, H = box.width, box.depth, box.height

    if D - 2 * t <= 0:
        raise ValueError(
            f"box depth {D} mm is too small for {t} mm material "
            f"(side panel width would be {D - 2*t} mm)"
        )
    if H <= t * 2:
        raise ValueError(
            f"box height {H} mm is too small for {t} mm material; "
            f"use height > 2 * thickness"
        )

    bottom_body_w = W - 2.0 * t
    bottom_body_h = D - 2.0 * t

    # Slot spans in each side-panel's bottom-edge local frame.
    fb_slots = _slots_for_front_back(bottom_body_w, joinery.bottom_tab_count,
                                     joinery.bottom_tab_width, t)
    lr_slots = _slots_for_left_right(bottom_body_h, joinery.bottom_tab_count,
                                     joinery.bottom_tab_width, t)

    # Sanity: slots must live inside the (possibly shortened) edge length.
    _validate_slots("front/back bottom", fb_slots, W, edge_len=W)
    _validate_slots("left/right bottom", lr_slots, D, edge_len=D - 4.0 * t)

    # Validate divider heights against material thickness and lid (if any),
    # then build a flat list of shelf-mortise rects per side panel.
    _validate_divider_heights(box.divider_heights, H, t, has_lid=box.has_lid)
    fb_mortises: list[RectRelief] = []
    lr_mortises: list[RectRelief] = []
    for z in box.divider_heights:
        fb_mortises.extend(_shelf_mortises_for_front_back(
            z, bottom_body_w, joinery.bottom_tab_count,
            joinery.bottom_tab_width, t,
        ))
        lr_mortises.extend(_shelf_mortises_for_left_right(
            z, bottom_body_h, joinery.bottom_tab_count,
            joinery.bottom_tab_width, t,
        ))

    panels: list[Panel] = []
    panels.append(_side_panel(
        "front", W, H, "outie", fb_slots, box.has_lid, fb_slots,
        material, joinery, cnc, interior_cuts=fb_mortises,
    ))
    panels.append(_side_panel(
        "back", W, H, "outie", fb_slots, box.has_lid, fb_slots,
        material, joinery, cnc, interior_cuts=fb_mortises,
    ))
    panels.append(_side_panel(
        "left", D - 2 * t, H, "innie", lr_slots, box.has_lid, lr_slots,
        material, joinery, cnc, interior_cuts=lr_mortises,
    ))
    panels.append(_side_panel(
        "right", D - 2 * t, H, "innie", lr_slots, box.has_lid, lr_slots,
        material, joinery, cnc, interior_cuts=lr_mortises,
    ))
    panels.append(_bottom_panel(
        "bottom", bottom_body_w, bottom_body_h,
        joinery.bottom_tab_count, joinery.bottom_tab_width, t,
    ))
    for i, _z in enumerate(box.divider_heights, start=1):
        panels.append(_bottom_panel(
            f"shelf_{i}", bottom_body_w, bottom_body_h,
            joinery.bottom_tab_count, joinery.bottom_tab_width, t,
        ))
    if box.has_lid:
        panels.append(_bottom_panel(
            "lid", bottom_body_w, bottom_body_h,
            joinery.bottom_tab_count, joinery.bottom_tab_width, t,
        ))
    return panels


def _validate_slots(
    label: str,
    slots: Sequence[tuple[float, float]],
    orig_edge_len: float,
    edge_len: float,
) -> None:
    """Raise if any slot span falls outside ``[0, edge_len]``."""

    for a, b in slots:
        if a < 0.0 or b > edge_len:
            raise ValueError(
                f"{label} slot ({a:.3f}, {b:.3f}) falls outside the edge "
                f"[0, {edge_len:.3f}] mm (panel outside length "
                f"{orig_edge_len:.3f} mm). Reduce bottom_tab_width or "
                f"bottom_tab_count, or use a bigger box."
            )


def _validate_divider_heights(
    heights: Sequence[float],
    box_height: float,
    t: float,
    has_lid: bool,
) -> None:
    """Tight bounds for divider Z-heights.

    The mortise band for the bottom occupies ``y in (-t, t)`` worth of slot
    notches plus the bottom-tab corners; we require ``z > 2t`` to keep clear.
    Symmetrically when there's a lid, ``z + t < H - t`` becomes ``z < H - 2t``.
    Two adjacent shelves must be separated by more than ``2 t`` so their
    mortise bands don't merge or starve the wall material between them.
    """

    if not heights:
        return
    lo = 2.0 * t
    hi = box_height - (2.0 * t if has_lid else t)
    prev = -1.0
    for z in heights:
        if z <= lo:
            raise ValueError(
                f"divider height {z:.3f} mm must be > 2 * thickness "
                f"({lo:.3f} mm) so its mortises clear the bottom slot band"
            )
        if z >= hi:
            kind = "below the lid mortise band" if has_lid else "below the top edge"
            raise ValueError(
                f"divider height {z:.3f} mm must stay {kind} "
                f"(< {hi:.3f} mm)"
            )
        if z + t >= box_height:
            raise ValueError(
                f"divider height {z:.3f} mm + thickness {t:.3f} mm exceeds "
                f"the box height {box_height:.3f} mm"
            )
        if prev >= 0.0 and (z - prev) <= 2.0 * t:
            raise ValueError(
                f"adjacent divider heights {prev:.3f} and {z:.3f} mm are "
                f"too close (need > 2 * thickness = {2*t:.3f} mm apart)"
            )
        prev = z
