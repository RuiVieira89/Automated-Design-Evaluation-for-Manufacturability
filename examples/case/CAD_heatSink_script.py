# ============================================================
#  FreeCAD Parametric Heat Sink — VS Code / external Python
#  Run with:  FreeCADCmd heatsink_vscode.py
#             or via VS Code terminal with FreeCADCmd on PATH
# ============================================================
#
#  SETUP — add FreeCAD's bin/lib folders to sys.path so Python
#  can find the FreeCAD, Part, Sketcher modules.
#  Edit FREECAD_PATH below to match your installation.
# ------------------------------------------------------------

import sys
import os

# --- Adjust this path for your OS and FreeCAD version -------
#
#  Windows (typical):
FREECAD_PATH_WIN = r"C:\Program Files\FreeCAD 1.0\bin"
#
#  macOS (AppBundle):
FREECAD_PATH_MAC = "/Applications/FreeCAD.app/Contents/Resources/lib"
#
#  Linux (apt / flatpak):
FREECAD_PATH_LIN = "/usr/lib/freecad/lib"   # apt install freecad
# FREECAD_PATH_LIN = "/var/lib/flatpak/app/org.freecadweb.FreeCAD/current/active/files/lib"

if sys.platform == "win32":
    sys.path.insert(0, FREECAD_PATH_WIN)
elif sys.platform == "darwin":
    sys.path.insert(0, FREECAD_PATH_MAC)
else:
    sys.path.insert(0, FREECAD_PATH_LIN)

# ------------------------------------------------------------
#  IMPORTS  — all from FreeCAD's own bundled Python modules.
#  Do NOT pip-install these; they live inside the FreeCAD folder.
# ------------------------------------------------------------
import FreeCAD as App   # core document / vector API
import Part             # BRep geometry primitives (LineSegment, etc.)
import Sketcher         # sketch constraints (Coincident, etc.)
# Import is FreeCAD's built-in file importer/exporter (STEP, IGES, STL…)
import Import

# ------------------------------------------------------------
#  PARAMETERS
# ------------------------------------------------------------
FinHeight     = 20.0
FinThickness  = 2.0
FinSpacing    = 5.0
BaseHeight    = 5.0
FinNumber     = 6
ChannelLength = 50.0

OUTPUT_STEP   = "heatsink.step"   # output file path (relative or absolute)
OUTPUT_FCSTD  = "heatsink.FCStd"  # optional: also save native FreeCAD file

# ------------------------------------------------------------
#  DERIVED DIMENSIONS
# ------------------------------------------------------------
W = FinThickness + FinSpacing     # unit-cell width
H = FinHeight + BaseHeight        # total profile height

# ------------------------------------------------------------
#  DOCUMENT + BODY
# ------------------------------------------------------------
doc  = App.newDocument("HeatSink")
body = doc.addObject("PartDesign::Body", "Body")

# ------------------------------------------------------------
#  SKETCH  on XY plane
# ------------------------------------------------------------
sketch = body.newObject("Sketcher::SketchObject", "FinSketch")
# OriginFeatures index 3 = XY_Plane
sketch.Support  = (body.Origin.OriginFeatures[3], "")
sketch.MapMode  = "FlatFace"

# ---- Rectangle 1: outer cell  (0,0) → (W, H) ---------------
#  Edge indices after addGeometry: 0=bottom 1=right 2=top 3=left
sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(W, 0, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(W, 0, 0), App.Vector(W, H, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(W, H, 0), App.Vector(0, H, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(0, H, 0), App.Vector(0, 0, 0)), False)

# Close corners of rect1
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 3, 2, 0, 1))

# Pin bottom-left corner to the sketch origin
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))

# ---- Rectangle 2: channel cutout  (FinThickness, BaseHeight) → (W, H) ---
#  Edge indices: 4=bottom 5=right 6=top 7=left
cx1, cy1 = FinThickness, BaseHeight
cx2, cy2 = W, H

sketch.addGeometry(Part.LineSegment(App.Vector(cx1, cy1, 0), App.Vector(cx2, cy1, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(cx2, cy1, 0), App.Vector(cx2, cy2, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(cx2, cy2, 0), App.Vector(cx1, cy2, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(cx1, cy2, 0), App.Vector(cx1, cy1, 0)), False)

# Close corners of rect2
sketch.addConstraint(Sketcher.Constraint("Coincident", 4, 2, 5, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 5, 2, 6, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 6, 2, 7, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", 7, 2, 4, 1))

# Share top edge with rect1 (both rectangles meet at y = H)
sketch.addConstraint(Sketcher.Constraint("Coincident", 6, 1, 2, 2))
sketch.addConstraint(Sketcher.Constraint("Coincident", 6, 2, 2, 1))

doc.recompute()

# ------------------------------------------------------------
#  PAD — extrude the sketch profile by ChannelLength
# ------------------------------------------------------------
pad = body.newObject("PartDesign::Pad", "FinPad")
pad.Profile      = sketch
pad.Length       = ChannelLength
pad.Reversed     = False
pad.Symmetric    = False
pad.TaperAngle   = 0.0

doc.recompute()

# ------------------------------------------------------------
#  LINEAR PATTERN — repeat FinNumber times along X axis
# ------------------------------------------------------------
pattern = body.newObject("PartDesign::LinearPattern", "FinPattern")
pattern.Originals   = [pad]
pattern.Direction   = (body.Origin.OriginFeatures[0], ["Edge1"])  # X axis
pattern.Reversed    = False
pattern.Length      = W * (FinNumber - 1)   # total span (first to last copy)
pattern.Occurrences = FinNumber

doc.recompute()

# ------------------------------------------------------------
#  EXPORT STEP
#  Import.export() takes a list of objects and a file path.
#  We export the Body's final shape (the pattern result).
# ------------------------------------------------------------
step_path = os.path.abspath(OUTPUT_STEP)
Import.export([pattern], step_path)
print(f"STEP exported → {step_path}")

# ------------------------------------------------------------
#  OPTIONALLY SAVE NATIVE .FCStd
# ------------------------------------------------------------
fcstd_path = os.path.abspath(OUTPUT_FCSTD)
doc.saveAs(fcstd_path)
print(f"FreeCAD file saved → {fcstd_path}")

print(f"\nHeat sink summary:")
print(f"  Fins:          {FinNumber}")
print(f"  Fin size:      {FinThickness} mm thick × {FinHeight} mm tall")
print(f"  Channel width: {FinSpacing} mm")
print(f"  Base height:   {BaseHeight} mm")
print(f"  Length:        {ChannelLength} mm")
print(f"  Total width:   {W * FinNumber} mm")


