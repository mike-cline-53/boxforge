"""BoxForge GUI — generate DXF and G-code for CNC plywood boxes."""

import os
import sys
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

# Make the boxforge package importable when this script is run directly from
# inside the package directory (python gui.py) or from the parent directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boxforge.box import build_box
from boxforge.cam import write_gcode
from boxforge.config import BoxSpec, CamSpec, CncSpec, JoinerySpec, MaterialSpec
from boxforge.dxf_export import write_dxf
from boxforge.layout import layout_panels

PAD = 10


class BoxForgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BoxForge — CNC Box Generator")
        self.minsize(760, 640)
        self._tab_entries: list[ttk.Entry] = []
        self._build_ui()
        self._toggle_tabs()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))
        style.configure("Generate.TButton", font=("TkDefaultFont", 10, "bold"), padding=6)

        outer = ttk.Frame(self, padding=PAD)
        outer.pack(fill="both", expand=True)

        # Top row: Box Dimensions | Joinery
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, PAD // 2))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        self._build_box_section(top)
        self._build_joinery_section(top)

        # Middle row: Material | CNC
        mid = ttk.Frame(outer)
        mid.pack(fill="x", pady=(0, PAD // 2))
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)
        self._build_material_section(mid)
        self._build_cnc_section(mid)

        self._build_cam_section(outer)
        self._build_output_section(outer)
        self._build_status_section(outer)

    def _build_box_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Box Dimensions", padding=PAD)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, PAD // 2))
        f.columnconfigure(2, weight=1)

        self.box_width  = self._field(f, 0, "Width",  300.0, "mm")
        self.box_depth  = self._field(f, 1, "Depth",  200.0, "mm")
        self.box_height = self._field(f, 2, "Height", 150.0, "mm")

        self.has_lid = tk.BooleanVar(value=False)
        ttk.Label(f, text="Has lid").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Checkbutton(f, variable=self.has_lid).grid(row=3, column=1, sticky="w")

        ttk.Label(f, text="Dividers").grid(row=4, column=0, sticky="w", pady=3)
        self.dividers = tk.StringVar(value="")
        ttk.Entry(f, textvariable=self.dividers, width=16).grid(
            row=4, column=1, columnspan=2, sticky="w", padx=(4, 0))
        ttk.Label(f, text="heights in mm, comma-separated", foreground="gray").grid(
            row=5, column=1, columnspan=2, sticky="w")

    def _build_joinery_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Joinery", padding=PAD)
        f.grid(row=0, column=1, sticky="nsew", padx=(PAD // 2, 0))
        f.columnconfigure(2, weight=1)

        self.finger_width = self._field(f, 0, "Finger width", 20.0, "mm")
        self.tab_count    = self._field(f, 2, "Bottom tab count", 2,    "")
        self.tab_width    = self._field(f, 3, "Bottom tab width", 30.0, "mm")

        ttk.Label(f, text="Corner relief").grid(row=1, column=0, sticky="w", pady=3)
        self.corner_relief = tk.StringVar(value="dogbone")
        ttk.Combobox(f, textvariable=self.corner_relief,
                     values=["dogbone", "tbone", "none"],
                     state="readonly", width=10).grid(row=1, column=1, sticky="w", padx=(4, 0))

    def _build_material_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Material", padding=PAD)
        f.grid(row=0, column=0, sticky="nsew", padx=(0, PAD // 2))
        f.columnconfigure(2, weight=1)

        self.mat_thickness = self._field(f, 0, "Thickness",    18.0,   "mm")
        self.sheet_w       = self._field(f, 1, "Sheet width",  1219.2, "mm")
        self.sheet_h       = self._field(f, 2, "Sheet height", 2438.4, "mm")

    def _build_cnc_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="CNC", padding=PAD)
        f.grid(row=0, column=1, sticky="nsew", padx=(PAD // 2, 0))
        f.columnconfigure(2, weight=1)

        self.bit_diameter = self._field(f, 0, "Bit diameter", 6.35, "mm")
        self.kerf         = self._field(f, 1, "Kerf",         0.1,  "mm")

    def _build_cam_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="CAM / G-code", padding=PAD)
        f.pack(fill="x", pady=(0, PAD // 2))

        row0 = ttk.Frame(f)
        row0.pack(fill="x", pady=(0, 4))
        self.total_depth = self._inline(row0, "Cut depth",  18.25, "mm")
        self.pass_depth  = self._inline(row0, "Pass depth",  6.0,  "mm")
        self.safe_z      = self._inline(row0, "Safe Z",      5.0,  "mm")

        row1 = ttk.Frame(f)
        row1.pack(fill="x", pady=(0, 4))
        self.feed_rapid  = self._inline(row1, "Rapid feed",  40.0, "mm/s")
        self.feed_plunge = self._inline(row1, "Plunge feed", 10.0, "mm/s")
        self.feed_cut    = self._inline(row1, "Cut feed",    20.0, "mm/s")

        row2 = ttk.Frame(f)
        row2.pack(fill="x")
        self.use_tabs = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Holding tabs", variable=self.use_tabs,
                        command=self._toggle_tabs).pack(side="left", padx=(0, PAD))

        self.tab_height, te1   = self._inline_entry(row2, "Tab height",    3.0,  "mm")
        self.tab_ramp,   te2   = self._inline_entry(row2, "Tab ramp",      10.0, "mm")
        self.tab_min,    te3   = self._inline_entry(row2, "Min edge",      80.0, "mm")
        self.tab_margin, te4   = self._inline_entry(row2, "Corner margin", 20.0, "mm")
        self._tab_entries = [te1, te2, te3, te4]

    def _build_output_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Output", padding=PAD)
        f.pack(fill="x", pady=(0, PAD // 2))

        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, PAD // 2))

        ttk.Label(top, text="Project name").pack(side="left")
        self.project_name = tk.StringVar(value="my_box")
        ttk.Entry(top, textvariable=self.project_name, width=16).pack(
            side="left", padx=(4, PAD))

        ttk.Label(top, text="Output folder").pack(side="left")
        self.out_dir = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Desktop"))
        ttk.Entry(top, textvariable=self.out_dir, width=36).pack(
            side="left", padx=(4, 4))
        ttk.Button(top, text="Browse…", command=self._browse_dir).pack(side="left")

        btn = ttk.Frame(f)
        btn.pack()
        ttk.Button(btn, text="Generate DXF",
                   command=self._gen_dxf, style="Generate.TButton").pack(
                       side="left", padx=6)
        ttk.Button(btn, text="Generate G-code",
                   command=self._gen_gcode, style="Generate.TButton").pack(
                       side="left", padx=6)
        ttk.Button(btn, text="Generate Both",
                   command=self._gen_both, style="Generate.TButton").pack(
                       side="left", padx=6)

    def _build_status_section(self, parent: ttk.Frame) -> None:
        f = ttk.LabelFrame(parent, text="Status", padding=PAD)
        f.pack(fill="both", expand=True)
        self.status = scrolledtext.ScrolledText(
            f, height=5, state="disabled", wrap="word", font=("Courier", 10))
        self.status.pack(fill="both", expand=True)

    # ── widget helpers ───────────────────────────────────────────────────────

    def _field(self, parent: ttk.Frame, row: int, label: str,
               default: float | int, unit: str) -> tk.StringVar:
        """Grid-based label + entry + unit."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=10).grid(
            row=row, column=1, sticky="w", padx=(4, 2))
        if unit:
            ttk.Label(parent, text=unit, foreground="gray").grid(
                row=row, column=2, sticky="w")
        return var

    def _inline(self, parent: ttk.Frame, label: str,
                default: float, unit: str) -> tk.StringVar:
        """Pack-based inline label + entry + unit (no toggle needed)."""
        var, _ = self._inline_entry(parent, label, default, unit)
        return var

    def _inline_entry(self, parent: ttk.Frame, label: str,
                      default: float, unit: str) -> tuple[tk.StringVar, ttk.Entry]:
        """Pack-based inline label + entry + unit; returns (var, entry) for toggling."""
        ttk.Label(parent, text=label).pack(side="left")
        var = tk.StringVar(value=str(default))
        entry = ttk.Entry(parent, textvariable=var, width=6)
        entry.pack(side="left", padx=(4, 0))
        ttk.Label(parent, text=unit, foreground="gray").pack(side="left", padx=(2, PAD))
        return var, entry

    # ── event handlers ───────────────────────────────────────────────────────

    def _toggle_tabs(self) -> None:
        state = "normal" if self.use_tabs.get() else "disabled"
        for entry in self._tab_entries:
            entry.config(state=state)

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self.out_dir.set(d)

    def _gen_dxf(self) -> None:
        self._generate(dxf=True, gcode=False)

    def _gen_gcode(self) -> None:
        self._generate(dxf=False, gcode=True)

    def _gen_both(self) -> None:
        self._generate(dxf=True, gcode=True)

    # ── core logic ───────────────────────────────────────────────────────────

    def _build_specs(self) -> tuple[BoxSpec, MaterialSpec, CncSpec, JoinerySpec, CamSpec]:
        """Parse all form fields into config dataclasses. Raises ValueError on bad input."""
        divider_str = self.dividers.get().strip()
        divider_heights: tuple[float, ...] = ()
        if divider_str:
            divider_heights = tuple(
                float(x.strip()) for x in divider_str.split(",") if x.strip()
            )

        box = BoxSpec(
            width=float(self.box_width.get()),
            depth=float(self.box_depth.get()),
            height=float(self.box_height.get()),
            has_lid=self.has_lid.get(),
            divider_heights=divider_heights,
        )
        material = MaterialSpec(
            thickness=float(self.mat_thickness.get()),
            sheet_width=float(self.sheet_w.get()),
            sheet_height=float(self.sheet_h.get()),
        )
        cnc = CncSpec(
            bit_diameter=float(self.bit_diameter.get()),
            kerf=float(self.kerf.get()),
        )
        joinery = JoinerySpec(
            finger_width=float(self.finger_width.get()),
            corner_relief=self.corner_relief.get(),  # type: ignore[arg-type]
            bottom_tab_count=int(self.tab_count.get()),
            bottom_tab_width=float(self.tab_width.get()),
        )
        cam = CamSpec(
            total_depth=float(self.total_depth.get()),
            pass_depth=float(self.pass_depth.get()),
            safe_z=float(self.safe_z.get()),
            feed_rapid=float(self.feed_rapid.get()),
            feed_plunge=float(self.feed_plunge.get()),
            feed_cut=float(self.feed_cut.get()),
            use_tabs=self.use_tabs.get(),
            tab_height=float(self.tab_height.get()),
            tab_ramp_length=float(self.tab_ramp.get()),
            tab_min_edge_length=float(self.tab_min.get()),
            tab_corner_margin=float(self.tab_margin.get()),
        )
        return box, material, cnc, joinery, cam

    def _generate(self, dxf: bool, gcode: bool) -> None:
        self._clear_log()
        try:
            box, material, cnc, joinery, cam = self._build_specs()
        except ValueError as e:
            self._log(f"✗ Configuration error: {e}")
            return

        project = self.project_name.get().strip() or "box"
        out_dir = self.out_dir.get().strip()
        os.makedirs(out_dir, exist_ok=True)

        self._log(
            f"Building box:  {box.width} × {box.depth} × {box.height} mm"
            + (f"  +lid" if box.has_lid else "")
            + (f"  dividers={box.divider_heights}" if box.divider_heights else "")
        )
        try:
            panels = build_box(box, material, joinery, cnc)
        except ValueError as e:
            self._log(f"✗ {e}")
            return

        self._log(f"  {len(panels)} panels generated")

        try:
            placed = layout_panels(panels, material.sheet_width, material.sheet_height)
        except ValueError as e:
            self._log(f"✗ Layout error: {e}")
            return

        self._log("  Layout packed")

        if dxf:
            path = os.path.join(out_dir, f"{project}.dxf")
            try:
                write_dxf(placed, path,
                           sheet_w=material.sheet_width,
                           sheet_h=material.sheet_height)
                self._log(f"✓ DXF saved →  {path}")
            except Exception as e:
                self._log(f"✗ DXF export failed: {e}")

        if gcode:
            path = os.path.join(out_dir, f"{project}.gcode")
            try:
                write_gcode(placed, path, cnc, cam, project_name=project)
                self._log(f"✓ G-code saved → {path}")
            except Exception as e:
                self._log(f"✗ G-code export failed: {e}")

    # ── status log ───────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self.status.config(state="normal")
        self.status.insert("end", msg + "\n")
        self.status.see("end")
        self.status.config(state="disabled")

    def _clear_log(self) -> None:
        self.status.config(state="normal")
        self.status.delete("1.0", "end")
        self.status.config(state="disabled")


# ── USER DEFAULTS ────────────────────────────────────────────────────────────
# Edit these values to pre-fill the form with your most common settings.

DEFAULT_BOX_WIDTH    = 300.0   # mm
DEFAULT_BOX_DEPTH    = 200.0   # mm
DEFAULT_BOX_HEIGHT   = 150.0   # mm
DEFAULT_HAS_LID      = False
DEFAULT_DIVIDERS     = ""      # e.g. "60, 100" for two shelves at 60 mm and 100 mm

DEFAULT_THICKNESS    = 18.0    # mm  (nominal 3/4" plywood)
DEFAULT_SHEET_WIDTH  = 1219.2  # mm  (4 ft)
DEFAULT_SHEET_HEIGHT = 2438.4  # mm  (8 ft)

DEFAULT_BIT_DIAMETER = 6.35    # mm  (1/4" upcut spiral)
DEFAULT_KERF         = 0.1     # mm

DEFAULT_FINGER_WIDTH     = 20.0   # mm
DEFAULT_CORNER_RELIEF    = "dogbone"   # "dogbone" | "tbone" | "none"
DEFAULT_BOTTOM_TAB_COUNT = 2
DEFAULT_BOTTOM_TAB_WIDTH = 30.0   # mm

DEFAULT_TOTAL_DEPTH  = 18.25   # mm  (material + slight spoilboard overcut)
DEFAULT_PASS_DEPTH   = 6.0     # mm
DEFAULT_SAFE_Z       = 5.0     # mm
DEFAULT_FEED_RAPID   = 40.0    # mm/s
DEFAULT_FEED_PLUNGE  = 10.0    # mm/s
DEFAULT_FEED_CUT     = 20.0    # mm/s
DEFAULT_USE_TABS     = False
DEFAULT_TAB_HEIGHT   = 3.0     # mm
DEFAULT_TAB_RAMP     = 10.0    # mm
DEFAULT_TAB_MIN_EDGE = 80.0    # mm
DEFAULT_TAB_MARGIN   = 20.0    # mm

DEFAULT_PROJECT_NAME = "my_box"
DEFAULT_OUTPUT_DIR   = os.path.join(os.path.expanduser("~"), "Desktop")

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = BoxForgeApp()

    # Apply user defaults to form fields
    app.box_width.set(DEFAULT_BOX_WIDTH)
    app.box_depth.set(DEFAULT_BOX_DEPTH)
    app.box_height.set(DEFAULT_BOX_HEIGHT)
    app.has_lid.set(DEFAULT_HAS_LID)
    app.dividers.set(DEFAULT_DIVIDERS)

    app.mat_thickness.set(DEFAULT_THICKNESS)
    app.sheet_w.set(DEFAULT_SHEET_WIDTH)
    app.sheet_h.set(DEFAULT_SHEET_HEIGHT)

    app.bit_diameter.set(DEFAULT_BIT_DIAMETER)
    app.kerf.set(DEFAULT_KERF)

    app.finger_width.set(DEFAULT_FINGER_WIDTH)
    app.corner_relief.set(DEFAULT_CORNER_RELIEF)
    app.tab_count.set(DEFAULT_BOTTOM_TAB_COUNT)
    app.tab_width.set(DEFAULT_BOTTOM_TAB_WIDTH)

    app.total_depth.set(DEFAULT_TOTAL_DEPTH)
    app.pass_depth.set(DEFAULT_PASS_DEPTH)
    app.safe_z.set(DEFAULT_SAFE_Z)
    app.feed_rapid.set(DEFAULT_FEED_RAPID)
    app.feed_plunge.set(DEFAULT_FEED_PLUNGE)
    app.feed_cut.set(DEFAULT_FEED_CUT)
    app.use_tabs.set(DEFAULT_USE_TABS)
    app.tab_height.set(DEFAULT_TAB_HEIGHT)
    app.tab_ramp.set(DEFAULT_TAB_RAMP)
    app.tab_min.set(DEFAULT_TAB_MIN_EDGE)
    app.tab_margin.set(DEFAULT_TAB_MARGIN)

    app.project_name.set(DEFAULT_PROJECT_NAME)
    app.out_dir.set(DEFAULT_OUTPUT_DIR)

    app._toggle_tabs()
    app.mainloop()
