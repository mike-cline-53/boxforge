"""Finger-joint edge profiles.

Two edge roles exist in a finger joint: ``outie`` (starts and ends with a
tab) and ``innie`` (starts and ends with a notch). The two edges mesh
together - an outie tab fits into an innie notch and vice versa.

Convention (see :mod:`boxforge.geometry`):

- Tabs extrude outward, along local -Y, by the material thickness. A tab
  is a rectangular extension of the panel body.
- Notches cut inward, along local +Y, by the material thickness. A notch
  is a rectangular chunk removed from the panel body.
- An outie path starts at (0, 0) and ends at (length, 0) - its first and
  last features are tabs whose bottom edge sits at the body corner line.
- An innie path starts at (0, +t) and ends at (length, +t), because the
  first and last features are notches that eat the body corner. Adjacent
  edges on the same panel must therefore start/end at (0, +t) and
  (L, +t) too (typically by shortening the adjacent straight edge by t
  on each end).
"""

from __future__ import annotations

from typing import Literal

from ..geometry import Path

FingerRole = Literal["outie", "innie"]


def finger_count(length: float, nominal_finger_width: float) -> int:
    """Return the number of finger segments to use on an edge of this length.

    Always odd and >= 3 so outie and innie patterns are symmetric. Actual
    finger width is ``length / count``.
    """

    if length <= 0:
        raise ValueError(f"edge length must be > 0, got {length}")
    if nominal_finger_width <= 0:
        raise ValueError(f"nominal_finger_width must be > 0, got {nominal_finger_width}")

    n = int(round(length / nominal_finger_width))
    if n < 3:
        n = 3
    if n % 2 == 0:
        n += 1
    return n


def finger_edge(
    length: float,
    material_thickness: float,
    nominal_finger_width: float,
    role: FingerRole,
) -> Path:
    """Generate an edge-local finger-joint path.

    The returned path is an open polyline starting at (0, 0) and ending at
    (length, 0). Callers transform it into the panel frame with
    :func:`boxforge.geometry.place_edge_on_rect`.
    """

    if material_thickness <= 0:
        raise ValueError(f"material_thickness must be > 0, got {material_thickness}")
    if role not in ("outie", "innie"):
        raise ValueError(f"role must be 'outie' or 'innie', got {role!r}")

    n = finger_count(length, nominal_finger_width)
    w = length / n
    t = material_thickness

    path: Path = []
    if role == "outie":
        path.append((0.0, 0.0))  # outie starts at the body corner
    for i in range(n):
        # Outie pattern: T N T N ... T (i even -> tab).
        # Innie pattern: N T N T ... N (i even -> notch).
        is_tab = (role == "outie" and i % 2 == 0) or (role == "innie" and i % 2 == 1)
        y = -t if is_tab else +t
        x_start = i * w
        x_end = (i + 1) * w
        path.append((x_start, y))
        path.append((x_end, y))
    if role == "outie":
        path.append((length, 0.0))  # outie ends at the body corner
    # For innie the path already ends at (length, +t) - that IS the corner
    # of the outline because the notch eats the body corner.
    return path


def straight_edge(length: float) -> Path:
    """A flat edge with no joinery features."""

    if length <= 0:
        raise ValueError(f"length must be > 0, got {length}")
    return [(0.0, 0.0), (length, 0.0)]
