# BoxForge

A Python library that generates production-ready DXF cut files and G-code for CNC-routed plywood boxes. Describe your box with a few parameters and BoxForge produces everything your router needs: finger-jointed side panels, a tabbed bottom (and optional lid), optional horizontal shelves, dogbone/T-bone corner relief, multi-pass toolpaths, and holding tabs.

## Features

- **Finger joints** on all four vertical corners, with automatic finger-count calculation from edge length
- **Through-tenon tab/slot joinery** connecting the bottom (and lid) to the four side panels — no dados, just glue or wedge
- **Horizontal dividers** (shelves) at arbitrary heights, each with matching mortises cut through the side walls
- **Corner relief** for round-bit CNC cutting: dogbone circles, T-bone squares, or none
- **DXF export** with color-coded layers (`CUT_OUTSIDE`, `CUT_INSIDE`, `LABEL`, `SHEET`) ready for EstlCAM or any CAM package
- **G-code generation** with configurable multi-pass depth, ramped plunges, nearest-neighbor part ordering, and optional holding tabs
- **Eager validation** — bad dimensions fail immediately with clear error messages, before any geometry is generated

## Requirements

- Python 3.10+
- [ezdxf](https://ezdxf.readthedocs.io/)

```bash
pip install ezdxf
```

## Quick Start

### GUI (recommended)

```bash
python gui.py
```

A desktop window opens with all parameters grouped into labeled sections. Fill in your box dimensions, material, CNC, and CAM settings, choose an output folder, and click **Generate DXF**, **Generate G-code**, or **Generate Both**. Status and error messages appear in the panel at the bottom.

To change your personal defaults (so the form pre-fills with your usual settings), edit the `# USER DEFAULTS` block at the bottom of `gui.py` — all values are grouped together there.

### Script (advanced)

BoxForge is also a library you can drive directly from a Python script. All user-configurable values live together at the bottom of the script. Here is a minimal example:

```python
from boxforge.config import BoxSpec, MaterialSpec, CncSpec, JoinerySpec, CamSpec
from boxforge.box import build_box
from boxforge.layout import pack_panels
from boxforge.dxf_export import write_dxf
from boxforge.cam import write_gcode

# ── build ──────────────────────────────────────────────────────────────────
panels = build_box(BOX, MATERIAL, JOINERY, CNC)
placed = pack_panels(panels, MATERIAL)

# ── export ─────────────────────────────────────────────────────────────────
write_dxf(placed, "output/my_box.dxf",
          sheet_w=MATERIAL.sheet_width, sheet_h=MATERIAL.sheet_height)
write_gcode(placed, "output/my_box.gcode", CNC, CAM, project_name="my_box")

# ── CONFIG ─────────────────────────────────────────────────────────────────
BOX = BoxSpec(
    width=300.0,        # outside X, mm
    depth=200.0,        # outside Y, mm
    height=150.0,       # outside Z, mm
    has_lid=False,
    divider_heights=(), # e.g. (60.0, 100.0) for two shelves
)
MATERIAL = MaterialSpec(
    thickness=18.0,     # nominal 3/4" plywood
    sheet_width=1219.2,
    sheet_height=2438.4,
)
CNC = CncSpec(
    bit_diameter=6.35,  # 1/4" upcut spiral
    kerf=0.1,
)
JOINERY = JoinerySpec(
    finger_width=20.0,
    corner_relief="dogbone",
    bottom_tab_count=2,
    bottom_tab_width=30.0,
)
CAM = CamSpec(
    total_depth=18.25,  # material + slight overcut into spoilboard
    pass_depth=6.0,
    safe_z=5.0,
    feed_rapid=40.0,    # mm/sec (converted to mm/min in G-code)
    feed_plunge=10.0,   # mm/sec
    feed_cut=20.0,      # mm/sec
    use_tabs=True,
    tab_height=3.0,
    tab_ramp_length=10.0,
)
```

## Project Structure

```
boxforge/
├── gui.py               # desktop GUI (run this to get started)
├── __init__.py          # package version
├── config.py            # BoxSpec, MaterialSpec, CncSpec, JoinerySpec, CamSpec
├── box.py               # panel geometry assembly (build_box)
├── panel.py             # Panel dataclass
├── geometry.py          # point/path primitives
├── layout.py            # 2-D bin-packing (pack_panels)
├── offset.py            # polyline offsetting for toolpath compensation
├── corner_relief.py     # dogbone / T-bone relief generation
├── dxf_export.py        # DXF writer (ezdxf)
├── cam.py               # G-code generation
└── joinery/
    ├── finger.py        # finger-joint edge profiles
    └── slots.py         # tab/slot edge profiles
```

## Configuration Reference

All dimensions are in **millimeters**.

### `BoxSpec`
| Field | Description |
|---|---|
| `width` | Outside X dimension |
| `depth` | Outside Y dimension |
| `height` | Outside Z dimension |
| `has_lid` | Add a lid panel (mirrors the bottom) |
| `divider_heights` | Tuple of Z-heights for horizontal shelves |

### `MaterialSpec`
| Field | Default | Description |
|---|---|---|
| `thickness` | — | Sheet thickness |
| `sheet_width` | 1219.2 | Stock sheet width (4 ft) |
| `sheet_height` | 2438.4 | Stock sheet height (8 ft) |

### `CncSpec`
| Field | Description |
|---|---|
| `bit_diameter` | Router bit diameter |
| `kerf` | Kerf compensation (set 0 to disable) |

### `JoinerySpec`
| Field | Default | Description |
|---|---|---|
| `finger_width` | 20.0 | Nominal finger width for corner joints |
| `corner_relief` | `"dogbone"` | `"dogbone"`, `"tbone"`, or `"none"` |
| `bottom_tab_count` | 2 | Tabs per edge on the bottom/lid/shelves |
| `bottom_tab_width` | 30.0 | Width of each tab in mm |

### `CamSpec`
| Field | Default | Description |
|---|---|---|
| `total_depth` | — | Full cut depth (material + overcut) |
| `pass_depth` | 5.0 | Max depth per pass |
| `safe_z` | 5.0 | Rapid clearance height |
| `feed_rapid` | 40.0 | Rapid move feed rate (mm/sec; converted to mm/min in G-code) |
| `feed_plunge` | 10.0 | Plunge feed rate (mm/sec) |
| `feed_cut` | 20.0 | Cutting feed rate (mm/sec) |
| `plunge_ramp_length` | 20.0 | Horizontal ramp distance on entry |
| `use_tabs` | False | Enable holding tabs |
| `tab_height` | 3.0 | Material left under each tab |
| `tab_ramp_length` | 10.0 | Half-footprint of the tab ramp |
| `tab_min_edge_length` | 80.0 | Minimum straight-edge length to receive a tab |
| `tab_corner_margin` | 20.0 | Distance from corner to tab center |
| `preamble` | *(see config.py)* | Raw G-code block inserted after G21/G90/G94 |
| `postamble` | *(see config.py)* | Raw G-code block at end of file |

## DXF Layers

| Layer | Color | Purpose |
|---|---|---|
| `CUT_OUTSIDE` | Red | Outer panel profiles — toolpath these |
| `CUT_INSIDE` | Blue | Corner reliefs and mortises — toolpath these |
| `LABEL` | Green | Panel name text — reference only, do not toolpath |
| `SHEET` | Gray | Virtual sheet border — reference only |

## License

MIT
