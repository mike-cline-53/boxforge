"""Panel: a single flat piece of plywood with an outline and relief cuts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .corner_relief import Relief
from .geometry import Path, bounding_box


@dataclass
class Panel:
    """One flat panel to be cut out of the sheet.

    - ``name`` is a short label written onto the DXF on the ``LABEL`` layer.
    - ``outline`` is a closed polyline; it is the outer profile cut on the
      ``CUT_OUTSIDE`` layer.
    - ``reliefs`` are drill/pocket features (dogbone circles or tbone
      squares) placed at concave corners of the outline and written on the
      ``CUT_INSIDE`` layer.
    - ``qty`` is the number of copies of this panel that go into the box.
    """

    name: str
    outline: Path
    reliefs: list[Relief] = field(default_factory=list)
    qty: int = 1

    def extents(self) -> tuple[float, float, float, float]:
        """min_x, min_y, max_x, max_y including tabs but ignoring reliefs."""
        return bounding_box(self.outline)

    def width(self) -> float:
        x0, _, x1, _ = self.extents()
        return x1 - x0

    def height(self) -> float:
        _, y0, _, y1 = self.extents()
        return y1 - y0
