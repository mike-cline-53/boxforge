"""Configuration dataclasses for a box generation run.

Everything is in millimeters. Validation happens eagerly in __post_init__ so
that bad input fails fast, before any geometry is generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Phase 1 ships with finger joints only. Keeping the Literal makes adding
# more types (rabbet/butt/dado) a one-line change once we're ready.
JoineryType = Literal["finger"]
CornerRelief = Literal["dogbone", "tbone", "none"]


@dataclass(frozen=True)
class BoxSpec:
    """Outside dimensions of the box. Width is X, depth is Y, height is Z.

    ``divider_heights`` is a sequence of Z-heights (in mm, measured from the
    inside-bottom face) where horizontal full-span shelves should be added.
    Each shelf is built like the bottom panel and joins all four walls with
    through-tenons. An empty sequence means no dividers (a plain box).
    Tight bounds (clearance from bottom, lid, and adjacent shelves) are
    enforced in :func:`boxforge.box.build_box` once the material thickness
    is known.
    """

    width: float
    depth: float
    height: float
    has_lid: bool = False
    divider_heights: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        for name in ("width", "depth", "height"):
            v = getattr(self, name)
            if v <= 0:
                raise ValueError(f"BoxSpec.{name} must be > 0, got {v}")
        # Coerce list/iterable input to a tuple so the dataclass stays hashable
        # and ordering is fixed.
        coerced = tuple(float(z) for z in self.divider_heights)
        object.__setattr__(self, "divider_heights", coerced)
        prev = -1.0
        for z in coerced:
            if z <= 0.0 or z >= self.height:
                raise ValueError(
                    f"BoxSpec.divider_heights values must be in (0, {self.height}), "
                    f"got {z}"
                )
            if z <= prev:
                raise ValueError(
                    f"BoxSpec.divider_heights must be strictly increasing, "
                    f"got {coerced}"
                )
            prev = z


@dataclass(frozen=True)
class MaterialSpec:
    """Sheet material. Thickness matters for joinery; sheet size is the
    virtual stock used by the layout packer."""

    thickness: float
    sheet_width: float = 1219.2   # 4 ft
    sheet_height: float = 2438.4  # 8 ft

    def __post_init__(self) -> None:
        if self.thickness <= 0:
            raise ValueError(f"MaterialSpec.thickness must be > 0, got {self.thickness}")
        if self.sheet_width <= 0 or self.sheet_height <= 0:
            raise ValueError("MaterialSpec sheet dimensions must be > 0")


@dataclass(frozen=True)
class CncSpec:
    """CNC-specific parameters."""

    bit_diameter: float
    kerf: float = 0.0

    def __post_init__(self) -> None:
        if self.bit_diameter <= 0:
            raise ValueError(f"CncSpec.bit_diameter must be > 0, got {self.bit_diameter}")
        if self.kerf < 0:
            raise ValueError(f"CncSpec.kerf must be >= 0, got {self.kerf}")


# Default job start/end sequences that match the EstlCAM pattern used
# by this project. These are raw multi-line gcode strings inserted
# verbatim into the output. Swap them out in the CONFIG block of
# scripts/make_box.py if your controller uses different commands.
_DEFAULT_PREAMBLE = """\
G92 X0 Y0
M0 (MSG Attach probe)
G38.2 Z-110 F200 P0.5
G1 Z10 F900
M0 (MSG Remove probe)
M62 P1
G00 X0.0000 Y0.0000 Z0.0000 F2400
G00 Z5.0000 F900"""

_DEFAULT_POSTAMBLE = """\
M63 P1
G00 X0.0000 Y0.0000 F2400
G00 Z0.0000 F900
$HZ
M30"""


@dataclass(frozen=True)
class CamSpec:
    """Parameters for generating gcode from the DXF layout.

    The DXF output always represents the KEPT part boundary; the CAM
    layer applies tool/kerf compensation so the emitted toolpath is
    ``bit_radius + kerf/2`` outside the outline (and inside any
    interior cutout).

    - total_depth: how deep the tool cuts at the final pass, in mm.
      Typically material thickness plus a small overcut so parts drop
      free (e.g. 18.25 for 3/4" plywood on a spoilboard).
    - pass_depth: maximum depth per pass; the total depth is split into
      N passes of at most this depth. A smaller pass depth is gentler on
      the bit but slower.
    - safe_z: rapid-move clearance above the material.
    - feed_rapid/feed_plunge/feed_cut: feed rates in mm/min for G00
      rapids, Z plunges, and XY cutting respectively.
    - plunge_ramp_length: horizontal distance over which the tool ramps
      from safe_z to the current pass depth when starting a part.
    - preamble: raw gcode block inserted after G21/G90/G94 (before the
      first part). Use this for your Z-probe touch-off sequence, spindle
      start command, and any machine-specific setup. Lines are emitted
      verbatim, one per line.
    - postamble: raw gcode block at the very end of the file (after the
      last part's retract move). Include your spindle-off command, home
      sequence, and M30 here.
    - use_tabs: when True, tabs are added to hold parts to the sheet on
      the final pass.
    - tab_height: how much material is left under the tab (mm) when the
      bit ramps up over it.
    - tab_ramp_length: total X travel from full depth up to the tab
      peak (so the tab footprint on the cut is roughly 2*this long).
    - tab_min_edge_length: only straight segments longer than this get
      tabs.
    - tab_corner_margin: distance from the end of a straight segment
      to the center of its nearest tab.
    """

    total_depth: float
    pass_depth: float = 5.0
    safe_z: float = 5.0
    feed_rapid: float = 2400.0
    feed_plunge: float = 600.0
    feed_cut: float = 1200.0
    plunge_ramp_length: float = 20.0
    preamble: str = _DEFAULT_PREAMBLE
    postamble: str = _DEFAULT_POSTAMBLE

    use_tabs: bool = False
    tab_height: float = 3.0
    tab_ramp_length: float = 10.0
    tab_min_edge_length: float = 80.0
    tab_corner_margin: float = 20.0

    def __post_init__(self) -> None:
        for name, minval in (
            ("total_depth", 0.0),
            ("pass_depth", 0.0),
            ("safe_z", 0.0),
            ("feed_rapid", 0.0),
            ("feed_plunge", 0.0),
            ("feed_cut", 0.0),
            ("plunge_ramp_length", 0.0),
        ):
            v = getattr(self, name)
            if v <= minval:
                raise ValueError(f"CamSpec.{name} must be > {minval}, got {v}")
        if self.use_tabs:
            for name, minval in (
                ("tab_height", 0.0),
                ("tab_ramp_length", 0.0),
                ("tab_min_edge_length", 0.0),
                ("tab_corner_margin", 0.0),
            ):
                v = getattr(self, name)
                if v <= minval:
                    raise ValueError(f"CamSpec.{name} must be > {minval}, got {v}")
            if self.tab_height >= self.total_depth:
                raise ValueError(
                    f"CamSpec.tab_height ({self.tab_height}) must be less than "
                    f"total_depth ({self.total_depth})"
                )


@dataclass(frozen=True)
class JoinerySpec:
    """How the panels connect.

    Vertical corners use finger joints. Bottom-to-wall (and lid-to-wall if
    present) uses through-tenons: the bottom panel has rectangular tabs
    extending out of its edges, which poke through matching rectangular
    slots cut in each side panel. The user glues or wedges to lock.

    - finger_width is the nominal finger width in mm for the vertical
      corner joints. The real finger count is computed from
      edge_length / finger_width and rounded to the nearest odd integer
      (>= 3) so the edge starts and ends with a matching feature.
    - corner_relief controls how inner corners of the finger notches are
      handled so a round CNC bit can clear them. Options: "dogbone",
      "tbone", "none".
    - bottom_tab_count is how many tabs per edge the bottom (and lid)
      has. 2 or 3 is typical.
    - bottom_tab_width is the width of each tab along the edge in mm.
    """

    type: JoineryType = "finger"
    finger_width: float = 20.0
    corner_relief: CornerRelief = "dogbone"
    bottom_tab_count: int = 2
    bottom_tab_width: float = 30.0

    def __post_init__(self) -> None:
        if self.type != "finger":
            raise ValueError(
                f"JoinerySpec.type invalid: {self.type!r}. Phase 1 only supports 'finger'."
            )
        if self.corner_relief not in ("dogbone", "tbone", "none"):
            raise ValueError(f"JoinerySpec.corner_relief invalid: {self.corner_relief!r}")
        if self.finger_width <= 0:
            raise ValueError(f"JoinerySpec.finger_width must be > 0, got {self.finger_width}")
        if self.bottom_tab_count < 1:
            raise ValueError(
                f"JoinerySpec.bottom_tab_count must be >= 1, got {self.bottom_tab_count}"
            )
        if self.bottom_tab_width <= 0:
            raise ValueError(
                f"JoinerySpec.bottom_tab_width must be > 0, got {self.bottom_tab_width}"
            )
