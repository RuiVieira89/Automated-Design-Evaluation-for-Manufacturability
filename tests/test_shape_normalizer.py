"""Tests for the shape normalization layer (post_process.shape_normalizer)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OCC_IMPORT_ERROR = None
try:
    from load_cad.step_reader import read_step_single
    from post_process.shape_normalizer import (
        AssemblyNode,
        FaceData,
        NormalizedShape,
        SolidData,
        normalize_shape,
    )

    HAVE_OCC = True
except Exception as exc:
    HAVE_OCC = False
    OCC_IMPORT_ERROR = exc

DATA_DIR = ROOT / "data"

_STEP_FILES = [
    "simple_rib.step",
    "escavator_arm-Assembly.step",
    "FlandersMake_part_NOK-Merger.step",
]

_VALID_SURFACE_TYPES = {
    "Plane",
    "Cylinder",
    "Cone",
    "Sphere",
    "Torus",
    "Bezier",
    "BSpline",
    "Other",
}


@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestNormalizedShapeStructure(unittest.TestCase):
    """Tests that normalize_shape returns a well-formed NormalizedShape."""

    def _normalize(self, filename: str, **kwargs) -> NormalizedShape:
        compound = read_step_single(str(DATA_DIR / filename))
        return normalize_shape(compound, **kwargs)

    # ------------------------------------------------------------------
    # Basic structure
    # ------------------------------------------------------------------

    def test_returns_normalized_shape_instance(self) -> None:
        result = self._normalize("simple_rib.step")
        self.assertIsInstance(result, NormalizedShape)

    def test_solids_is_list(self) -> None:
        result = self._normalize("simple_rib.step")
        self.assertIsInstance(result.solids, list)

    def test_at_least_one_solid_extracted_from_each_file(self) -> None:
        for filename in _STEP_FILES:
            with self.subTest(filename=filename):
                result = self._normalize(filename)
                self.assertGreater(
                    len(result.solids),
                    0,
                    f"No solids extracted from {filename}",
                )

    def test_solid_ids_are_sequential_zero_based(self) -> None:
        result = self._normalize("simple_rib.step")
        for expected, solid_data in enumerate(result.solids):
            self.assertEqual(solid_data.solid_id, expected)

    def test_every_solid_has_faces(self) -> None:
        result = self._normalize("simple_rib.step")
        for solid_data in result.solids:
            self.assertGreater(
                len(solid_data.faces),
                0,
                f"Solid {solid_data.solid_id} has no faces",
            )

    def test_face_ids_are_sequential_zero_based(self) -> None:
        result = self._normalize("simple_rib.step")
        for solid_data in result.solids:
            for expected, face_data in enumerate(solid_data.faces):
                self.assertEqual(face_data.face_id, expected)

    # ------------------------------------------------------------------
    # Assembly context
    # ------------------------------------------------------------------

    def test_no_assembly_context_by_default(self) -> None:
        result = self._normalize("simple_rib.step")
        self.assertIsNone(result.assembly_context)

    def test_assembly_context_present_when_requested(self) -> None:
        result = self._normalize("simple_rib.step", keep_context=True)
        self.assertIsNotNone(result.assembly_context)

    def test_assembly_context_length_matches_solid_count(self) -> None:
        for filename in _STEP_FILES:
            with self.subTest(filename=filename):
                result = self._normalize(filename, keep_context=True)
                self.assertEqual(
                    len(result.assembly_context),  # type: ignore[arg-type]
                    len(result.solids),
                )

    def test_assembly_context_solid_ids_are_valid(self) -> None:
        result = self._normalize("escavator_arm-Assembly.step", keep_context=True)
        assert result.assembly_context is not None
        for node in result.assembly_context:
            self.assertIsInstance(node, AssemblyNode)
            self.assertIsInstance(node.path, tuple)
            self.assertGreaterEqual(node.solid_id, 0)
            self.assertLess(node.solid_id, len(result.solids))

    def test_assembly_context_solid_ids_are_unique_and_ordered(self) -> None:
        result = self._normalize("simple_rib.step", keep_context=True)
        assert result.assembly_context is not None
        ids = [node.solid_id for node in result.assembly_context]
        self.assertEqual(ids, list(range(len(result.solids))))

    # ------------------------------------------------------------------
    # Bare solid input
    # ------------------------------------------------------------------

    def test_bare_solid_accepted(self) -> None:
        """normalize_shape should work when given a bare TopoDS_Solid."""
        from OCC.Core.TopoDS import topods
        from OCC.Core.TopAbs import TopAbs_SOLID
        from OCC.Core.TopExp import TopExp_Explorer

        compound = read_step_single(str(DATA_DIR / "simple_rib.step"))
        exp = TopExp_Explorer(compound, TopAbs_SOLID)
        self.assertTrue(exp.More(), "No solid found in simple_rib.step")
        single_solid = topods.Solid(exp.Current())

        result = normalize_shape(single_solid)
        self.assertEqual(len(result.solids), 1)


@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestFaceAttributes(unittest.TestCase):
    """Tests for per-face attribute computation on simple_rib.step."""

    @classmethod
    def setUpClass(cls) -> None:
        compound = read_step_single(str(DATA_DIR / "simple_rib.step"))
        cls.result: NormalizedShape = normalize_shape(compound)

    def _all_faces(self):
        for solid_data in self.result.solids:
            yield from solid_data.faces

    def test_area_is_positive(self) -> None:
        for face_data in self._all_faces():
            self.assertGreater(
                face_data.area,
                0.0,
                f"Face {face_data.face_id} has non-positive area",
            )

    def test_surface_type_is_valid_string(self) -> None:
        for face_data in self._all_faces():
            self.assertIn(face_data.surface_type, _VALID_SURFACE_TYPES)

    def test_center_is_3_tuple_of_floats(self) -> None:
        for face_data in self._all_faces():
            self.assertEqual(len(face_data.center), 3)
            for v in face_data.center:
                self.assertIsInstance(v, float)

    def test_planar_faces_have_normal(self) -> None:
        for face_data in self._all_faces():
            if face_data.surface_type == "Plane":
                self.assertIsNotNone(
                    face_data.normal,
                    f"Planar face {face_data.face_id} has no normal",
                )
                self.assertEqual(len(face_data.normal), 3)  # type: ignore[arg-type]

    def test_non_planar_faces_have_no_normal(self) -> None:
        for face_data in self._all_faces():
            if face_data.surface_type != "Plane":
                self.assertIsNone(
                    face_data.normal,
                    f"Non-planar face {face_data.face_id} unexpectedly has a normal",
                )

    def test_bounding_box_is_6_element_tuple(self) -> None:
        for face_data in self._all_faces():
            self.assertEqual(len(face_data.bounding_box), 6)

    def test_bounding_box_min_le_max(self) -> None:
        for face_data in self._all_faces():
            xmin, ymin, zmin, xmax, ymax, zmax = face_data.bounding_box
            self.assertLessEqual(xmin, xmax, f"Face {face_data.face_id}: xmin > xmax")
            self.assertLessEqual(ymin, ymax, f"Face {face_data.face_id}: ymin > ymax")
            self.assertLessEqual(zmin, zmax, f"Face {face_data.face_id}: zmin > zmax")

    def test_face_data_is_dataclass_instance(self) -> None:
        for face_data in self._all_faces():
            self.assertIsInstance(face_data, FaceData)


@unittest.skipUnless(HAVE_OCC, f"pythonocc-core not available: {OCC_IMPORT_ERROR}")
class TestFaceAdjacency(unittest.TestCase):
    """Tests for the face-adjacency graph built via shared edges."""

    @classmethod
    def setUpClass(cls) -> None:
        compound = read_step_single(str(DATA_DIR / "simple_rib.step"))
        cls.result: NormalizedShape = normalize_shape(compound)

    def test_adjacency_keys_match_face_ids(self) -> None:
        for solid_data in self.result.solids:
            expected = set(range(len(solid_data.faces)))
            self.assertEqual(set(solid_data.adjacency.keys()), expected)

    def test_adjacency_is_symmetric(self) -> None:
        for solid_data in self.result.solids:
            for face_id, neighbours in solid_data.adjacency.items():
                for nb in neighbours:
                    self.assertIn(
                        face_id,
                        solid_data.adjacency[nb],
                        f"Solid {solid_data.solid_id}: adjacency not symmetric "
                        f"between face {face_id} and {nb}",
                    )

    def test_adjacency_has_no_self_loops(self) -> None:
        for solid_data in self.result.solids:
            for face_id, neighbours in solid_data.adjacency.items():
                self.assertNotIn(
                    face_id,
                    neighbours,
                    f"Face {face_id} is listed as adjacent to itself",
                )

    def test_adjacency_neighbour_ids_are_valid_face_ids(self) -> None:
        for solid_data in self.result.solids:
            valid = set(range(len(solid_data.faces)))
            for face_id, neighbours in solid_data.adjacency.items():
                for nb in neighbours:
                    self.assertIn(nb, valid)

    def test_adjacency_lists_have_no_duplicates(self) -> None:
        for solid_data in self.result.solids:
            for face_id, neighbours in solid_data.adjacency.items():
                self.assertEqual(
                    len(neighbours),
                    len(set(neighbours)),
                    f"Duplicate neighbours for face {face_id}",
                )

    def test_solid_face_graph_is_connected(self) -> None:
        """All faces of a valid closed solid should be reachable from face 0."""
        for solid_data in self.result.solids:
            if len(solid_data.faces) <= 1:
                continue
            visited: set = set()
            queue = [0]
            while queue:
                node = queue.pop()
                if node in visited:
                    continue
                visited.add(node)
                queue.extend(solid_data.adjacency[node])
            self.assertEqual(
                len(visited),
                len(solid_data.faces),
                f"Solid {solid_data.solid_id}: face adjacency graph is not connected",
            )

    def test_assembly_adjacency_all_files(self) -> None:
        """Adjacency is symmetric for every STEP file."""
        for filename in _STEP_FILES:
            with self.subTest(filename=filename):
                compound = read_step_single(str(DATA_DIR / filename))
                result = normalize_shape(compound)
                for solid_data in result.solids:
                    for face_id, neighbours in solid_data.adjacency.items():
                        for nb in neighbours:
                            self.assertIn(face_id, solid_data.adjacency[nb])


if __name__ == "__main__":
    unittest.main()
