"""Parametric CAD generation of a fin-array heat sink using pythonocc-core.

Geometry
--------
A base plate with FinNumber rectangular fins extruded upward::

         |<--- ChannelLength --->|
         ___   ___   ___   ___      ↑
        |   | |   | |   | |   |    FinHeight
     ___|   |_|   |_|   |_|   |___
    |_____________________________| ↑ BaseHeight

    |←FinThick→| |←FinSpacing→|

Coordinate system
-----------------
* x — channel / extrusion direction  (length = ChannelLength)
* y — fin-array direction             (width  = FinNumber*FinThickness
                                               + (FinNumber-1)*FinSpacing)
* z — height direction                (total  = BaseHeight + FinHeight)

Named boundary-condition faces
-------------------------------
Each ADVANCED_FACE entity in the exported STEP file is assigned one of
the names defined in the ``BC_*`` constants below.  These names are
preserved in the STEP file and are visible in any STEP-compatible CAD
tool (FreeCAD, CATIA, Creo, …).

================================  ========================================
STEP face name                    FEA use
================================  ========================================
``mech_fixed_base``               Mechanical  — clamped base (all DOFs=0)
                                  Thermal     — convection / heat source
                                                at the base bottom (same
                                                face as the mechanical BC)
``mech_load_top``                 Mechanical  — applied surface pressure
``therm_conv_fins``               Thermal     — convection on fin surfaces
                                                (fin sides + channel floors)
``end_cap``                       No BC assigned (adiabatic / symmetry)
================================  ========================================

EasyFEA integration
-------------------
After meshing with ``Mesher.Mesh_Import_part()``, use ``Nodes_Conditions``
with coordinate-based lambdas that match each named face group::

    tol = 1e-3
    z_base  = BaseHeight                   # channel-floor z
    z_total = BaseHeight + FinHeight       # fin-top z

    # mech_fixed_base  (= therm_conv_base)
    nodes_fixed = mesh.Nodes_Conditions(lambda x, y, z: z <= tol)

    # mech_load_top
    nodes_top = mesh.Nodes_Conditions(lambda x, y, z: z >= z_total - tol)

    # therm_conv_fins  (fin sides and channel floors)
    nodes_fins = mesh.Nodes_Conditions(
        lambda x, y, z: (abs(z - z_base) < tol)          # channel floor
                        | (z > z_base - tol)              # all y-normal faces above base
    )

Usage
-----
As a library::

    from examples.case.CAD_heatSink import generate_heat_sink
    step_path = generate_heat_sink(fin_number=8, output_step="hs_8fins.step")

As a script::

    conda run -n auto_eval_manuf python examples/case/CAD_heatSink.py
"""

from __future__ import annotations

import re
import shutil
import sys
import warnings
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# repo root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.gp import gp_Pnt

# ---------------------------------------------------------------------------
# Default destination
# ---------------------------------------------------------------------------
_DEFAULT_DEST = ROOT / "data" / "CAD_generated"

# ===========================================================================
# BOUNDARY CONDITION FACE NAMES
# ---------------------------------------------------------------------------
# Edit the string VALUES on the right-hand side to rename a BC group.
# The same string will appear as the ADVANCED_FACE name in the STEP file
# and is what you see when you open the file in FreeCAD, CATIA, Creo, etc.
#
# Rules
# -----
# * BC_MECH_FIXED and BC_THERM_BASE refer to the SAME physical face
#   (the base bottom at z = 0).  They share the same string so that a
#   single face name covers both the mechanical clamped BC and the
#   thermal base BC.  Give them different strings only if your FEA
#   workflow requires distinct labels on that face.
#
# * BC_END_CAP covers the two x-direction end faces (x = 0 and
#   x = ChannelLength).  Assign "" to leave them unnamed (blank in STEP).
# ===========================================================================

BC_MECH_FIXED    = "mech_fixed_base"   # base bottom  — clamped support (mech)
BC_THERM_BASE    = "mech_fixed_base"   # base bottom  — convection / heat source (thermal)
                                        #   ↑ same face as BC_MECH_FIXED; change only if needed
BC_MECH_LOAD_TOP = "mech_load_top"     # fin tops     — applied load (mech)
BC_THERM_FINS    = "therm_conv_fins"   # fin surfaces — convection on fins (thermal)
                                        #   covers: fin side faces + channel floors
BC_END_CAP       = "end_cap"           # x-end faces  — no BC (adiabatic / symmetry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_heat_sink_step_text(
    fin_height: float = 20.0,
    fin_thickness: float = 2.0,
    fin_spacing: float = 5.0,
    base_height: float = 5.0,
    fin_number: int = 6,
    channel_length: float = 50.0,
) -> str:
    """Build a parametric fin-array heat sink and return the STEP content as a string.

    No files are written.  Pass the returned string directly to
    ``HeatSinkFEA(step_content=...)`` for an in-memory CAD→FEA pipeline.

    Parameters
    ----------
    fin_height, fin_thickness, fin_spacing, base_height, fin_number, channel_length:
        Same geometry parameters as ``generate_heat_sink``.

    Returns
    -------
    str
        Full STEP file content with BC face names applied.
    """
    import tempfile

    total_width  = fin_number * fin_thickness + (fin_number - 1) * fin_spacing
    total_height = base_height + fin_height

    base = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        channel_length, total_width, base_height,
    ).Shape()

    compound = base
    for i in range(fin_number):
        y0  = i * (fin_thickness + fin_spacing)
        fin = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, y0, base_height),
            channel_length, fin_thickness, fin_height,
        ).Shape()
        fuse = BRepAlgoAPI_Fuse(compound, fin)
        fuse.Build()
        compound = fuse.Shape()

    # OCC writer requires a real file path — use a temp file, read back, delete
    with tempfile.NamedTemporaryFile(suffix=".stp", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    status = writer.Write(str(tmp_path))
    if status != IFSelect_RetDone:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("STEP write failed (in-memory path)")

    raw = tmp_path.read_text()
    tmp_path.unlink(missing_ok=True)

    return _rename_step_faces(raw, base_height=base_height, total_height=total_height)


def generate_heat_sink(
    fin_height: float = 20.0,
    fin_thickness: float = 2.0,
    fin_spacing: float = 5.0,
    base_height: float = 5.0,
    fin_number: int = 6,
    channel_length: float = 50.0,
    output_step: str = "heat_sink.step",
    output_fcstd: Optional[str] = None,
    dest_folder: Optional[Path | str] = None,
) -> Path:
    """Generate a parametric fin-array heat sink and write it to STEP.

    Parameters
    ----------
    fin_height:
        Height of each fin above the base plate  [mm].
    fin_thickness:
        Thickness of one fin  [mm].
    fin_spacing:
        Clear distance between adjacent fins (channel width)  [mm].
    base_height:
        Thickness of the base plate  [mm].
    fin_number:
        Number of fins.
    channel_length:
        Length of the heat sink in the flow direction  [mm].
    output_step:
        File name (not path) of the exported STEP file.
    output_fcstd:
        File name of an optional FreeCAD .FCStd file.
        Pass ``None`` (default) to skip.  Requires FreeCAD.
    dest_folder:
        Destination directory.  Defaults to ``<repo_root>/data/CAD_generated``.

    Returns
    -------
    Path
        Absolute path of the written STEP file.
    """
    dest = Path(dest_folder) if dest_folder is not None else _DEFAULT_DEST
    dest.mkdir(parents=True, exist_ok=True)

    step_text = build_heat_sink_step_text(
        fin_height=fin_height,
        fin_thickness=fin_thickness,
        fin_spacing=fin_spacing,
        base_height=base_height,
        fin_number=fin_number,
        channel_length=channel_length,
    )

    step_path = dest / output_step
    step_path.write_text(step_text)
    print(f"STEP written → {step_path}")

    if output_fcstd is not None:
        _write_fcstd(step_path, dest / output_fcstd)

    return step_path


# ---------------------------------------------------------------------------
# STEP face-name post-processor
# ---------------------------------------------------------------------------
# OCC's STEPControl_Writer always writes blank ADVANCED_FACE names ('').
# We patch them here by:
#   1. Parsing every entity in the STEP text into a {id: (type, args)} dict.
#   2. For each ADVANCED_FACE, tracing the reference chain:
#        ADVANCED_FACE → PLANE → AXIS2_PLACEMENT_3D
#                                  ├─ CARTESIAN_POINT  (location on plane)
#                                  └─ DIRECTION        (plane normal = axis)
#   3. Calling _classify_face() to map (location, normal) → BC name.
#   4. Substituting the blank '' with the BC name string.
#
# This works with OCC-generated STEP files where entities fit on one line.
# ---------------------------------------------------------------------------

def _rename_step_faces(
    step_text: str,
    base_height: float,
    total_height: float,
    tol: float = 1e-3,
) -> str:
    """Return *step_text* with ADVANCED_FACE names filled in."""
    entities = _parse_step_entities(step_text)

    # Build a replacement map: {entity_id: new_name_string}
    replacements: dict[int, str] = {}
    for eid, (etype, args) in entities.items():
        if etype != "ADVANCED_FACE":
            continue

        name = _resolve_face_name(eid, args, entities, base_height, total_height, tol)
        if name:
            replacements[eid] = name

    if not replacements:
        return step_text

    # Apply substitutions: replace the blank first string arg of each face.
    # Pattern matches: #<id> = ADVANCED_FACE('', ...
    def _substitute(m: re.Match) -> str:
        eid = int(m.group(1))
        if eid in replacements:
            return m.group(0).replace("''", f"'{replacements[eid]}'", 1)
        return m.group(0)

    return re.sub(r"#(\d+)\s*=\s*ADVANCED_FACE\('',", _substitute, step_text)


def _resolve_face_name(
    eid: int,
    args: str,
    entities: dict,
    base_height: float,
    total_height: float,
    tol: float,
) -> str:
    """Trace one ADVANCED_FACE to its plane geometry and return a BC name."""
    parts = _split_args(args)
    # parts: [name, (bounds_list), surface_ref, same_sense]
    if len(parts) < 3:
        return ""

    # Surface reference (3rd arg) must be a PLANE
    surf_ref = _get_ref(parts[2])
    if surf_ref is None or surf_ref not in entities:
        return ""
    surf_type, surf_args = entities[surf_ref]
    if surf_type != "PLANE":
        return ""  # non-planar face — skip

    # AXIS2_PLACEMENT_3D reference (2nd arg of PLANE)
    ax2_ref = _get_ref(surf_args)
    if ax2_ref is None or ax2_ref not in entities:
        return ""
    _, ax2_args = entities[ax2_ref]
    ax2_parts = _split_args(ax2_args)
    # ax2_parts: [name, location_ref, axis_ref, refdir_ref]
    if len(ax2_parts) < 3:
        return ""

    loc_ref  = _get_ref(ax2_parts[1])  # CARTESIAN_POINT — a point on the plane
    axis_ref = _get_ref(ax2_parts[2])  # DIRECTION       — the plane normal

    loc  = _get_floats(entities[loc_ref][1])  if loc_ref  and loc_ref  in entities else []
    axis = _get_floats(entities[axis_ref][1]) if axis_ref and axis_ref in entities else []

    if len(loc) < 3 or len(axis) < 3:
        return ""

    return _classify_face(loc, axis, base_height, total_height, tol)


def _classify_face(
    loc: list[float],
    normal: list[float],
    base_height: float,
    total_height: float,
    tol: float,
) -> str:
    """Map (location-on-plane, plane-normal) to a BC face name.

    Classification rules
    --------------------
    The plane normal direction decides the face orientation; the z-coordinate
    of the location point identifies which horizontal level the face sits at.

    +-----------+------------------+-----------------------------+
    | |normal_z|≈1 | z_location ≈ 0            | BC_MECH_FIXED (= BC_THERM_BASE) |
    |           | z_location ≈ total_height | BC_MECH_LOAD_TOP                |
    |           | z_location ≈ base_height  | BC_THERM_FINS (channel floor)   |
    +-----------+------------------+-----------------------------+
    | |normal_y|≈1 | (any z)                   | BC_THERM_FINS (fin side faces)  |
    +-----------+------------------+-----------------------------+
    | |normal_x|≈1 | (any z)                   | BC_END_CAP                      |
    +-----------+------------------+-----------------------------+

    To change which face gets which name:
      • Modify the BC_* constants at the top of this module, OR
      • Edit the return statements below for finer control.
    """
    nx = abs(normal[0])
    ny = abs(normal[1])
    nz = abs(normal[2])
    z  = loc[2]

    if nz > 0.9:                              # horizontal face (z-normal)
        if abs(z) < tol:
            return BC_MECH_FIXED              # ← base bottom  (mech fixed + therm base)
        if abs(z - total_height) < tol:
            return BC_MECH_LOAD_TOP           # ← fin tops     (mech load)
        if abs(z - base_height) < tol:
            return BC_THERM_FINS             # ← channel floor (therm convection)

    elif ny > 0.9:                            # vertical face in y-direction
        return BC_THERM_FINS                 # ← fin side faces (therm convection)

    elif nx > 0.9:                            # vertical face in x-direction
        return BC_END_CAP                    # ← end caps (no BC)

    return ""                                 # unclassified — left blank in STEP


# ---------------------------------------------------------------------------
# STEP text parsing helpers
# ---------------------------------------------------------------------------

def _parse_step_entities(text: str) -> dict[int, tuple[str, str]]:
    """Return {entity_id: (type_string, args_string)} for all single-line entities."""
    out: dict[int, tuple[str, str]] = {}
    for m in re.finditer(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.+?)\)\s*;", text):
        out[int(m.group(1))] = (m.group(2), m.group(3))
    return out


def _split_args(args: str) -> list[str]:
    """Split comma-separated STEP args while respecting nested parentheses."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in args:
        if ch == "(":
            depth += 1; cur.append(ch)
        elif ch == ")":
            depth -= 1; cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _get_ref(s: str) -> Optional[int]:
    """Return the first #N entity reference found in *s*, or None."""
    m = re.search(r"#(\d+)", s)
    return int(m.group(1)) if m else None


def _get_floats(s: str) -> list[float]:
    """Return the first parenthesised float list from *s*."""
    m = re.search(r"\(([^()]+)\)", s)
    if m:
        return [float(x.strip()) for x in m.group(1).split(",")]
    return []


# ---------------------------------------------------------------------------
# Optional FreeCAD .FCStd export
# ---------------------------------------------------------------------------

def _write_fcstd(step_path: Path, fcstd_path: Path) -> None:
    """Import *step_path* into a FreeCAD document and save as .FCStd."""
    try:
        import FreeCAD   # type: ignore[import]
        import Import    # type: ignore[import]
    except ImportError:
        warnings.warn(
            "FreeCAD is not installed — skipping .FCStd export. "
            "Install FreeCAD and ensure its Python modules are on sys.path.",
            stacklevel=3,
        )
        return

    doc = FreeCAD.newDocument(fcstd_path.stem)
    Import.insert(str(step_path), doc.Name)
    doc.saveAs(str(fcstd_path))
    FreeCAD.closeDocument(doc.Name)
    print(f"FCStd written → {fcstd_path}")


# ---------------------------------------------------------------------------
# Script entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    generate_heat_sink(
        fin_height=20.0,
        fin_thickness=2.0,
        fin_spacing=5.0,
        base_height=5.0,
        fin_number=6,
        channel_length=50.0,
        output_step="heat_sink.step",
        output_fcstd=None,           # e.g. "heat_sink.FCStd" to enable
        dest_folder=None,            # defaults to data/CAD_generated/
    )
