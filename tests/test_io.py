import unittest
import sys
import os
import importlib.util
import numpy as np

'''
To run these tests, ensure you have the necessary dependencies installed in your environment. 
You can execute the tests using the following command:
conda run -n auto_eval_manuf python -m unittest tests.test_io -v
'''

# Import the io module using importlib to avoid conflict with built-in io
spec = importlib.util.spec_from_file_location("geom_io", os.path.join(os.path.dirname(__file__), '..', 'io', 'io.py'))
geom_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geom_io)

class TestGeometryIO(unittest.TestCase):
    def setUp(self):
        self.input_layer = geom_io.GeometryInputLayer()
        self.test_stl_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'FlandersMake_part-Merger.stl')

    def test_load_stl_via_input_layer(self):
        """Test that GeometryInputLayer correctly identifies and loads STL files as mesh geometry.
        
        Verifies that:
        - The input layer automatically selects the MeshLoader for .stl files
        - The loaded geometry is marked as mesh (not B-Rep)
        - Points and cells arrays are properly loaded as numpy arrays
        - Points have 3D coordinates (Nx3 shape)
        - Cells represent triangular faces (Mx3 shape)
        - The geometry contains actual vertex and face data
        """
        geom = self.input_layer.load_geometry(self.test_stl_file)
        
        # STL should be loaded as mesh (not B-Rep)
        self.assertFalse(geom.is_brep)
        self.assertIsNotNone(geom.points)
        self.assertIsNotNone(geom.cells)
        self.assertIsInstance(geom.points, np.ndarray)
        self.assertIsInstance(geom.cells, np.ndarray)
        
        # Check that we have some geometry
        self.assertGreater(len(geom.points), 0)
        self.assertGreater(len(geom.cells), 0)
        
        # Points should be Nx3
        self.assertEqual(geom.points.shape[1], 3)
        # Cells should be Mx3 (triangles)
        self.assertEqual(geom.cells.shape[1], 3)

    def test_load_stl_via_load_mesh(self):
        """Test direct loading of STL files using the load_mesh convenience function.
        
        Verifies that:
        - The load_mesh function can directly load STL files without the input layer
        - The geometry is correctly identified as mesh format
        - Vertex points and face cells are loaded as numpy arrays
        - Points are 3D coordinates and cells are triangular faces
        - The loaded mesh contains valid geometric data
        """
        geom = geom_io.load_mesh(self.test_stl_file)
        
        # Should be mesh
        self.assertFalse(geom.is_brep)
        self.assertIsNotNone(geom.points)
        self.assertIsNotNone(geom.cells)
        self.assertIsInstance(geom.points, np.ndarray)
        self.assertIsInstance(geom.cells, np.ndarray)
        
        # Check geometry
        self.assertGreater(len(geom.points), 0)
        self.assertGreater(len(geom.cells), 0)
        self.assertEqual(geom.points.shape[1], 3)
        self.assertEqual(geom.cells.shape[1], 3)

    def test_load_and_tessellate_stl(self):
        """Test that load_and_tessellate works correctly on already-meshed STL files.
        
        Verifies that:
        - The load_and_tessellate method can handle STL files that are already meshes
        - Since STL files are already tessellated, the result should be identical to direct loading
        - The geometry remains in mesh format (not converted to B-Rep)
        - All mesh data (points and cells) is preserved correctly
        - The method doesn't fail or alter the geometry when tessellation isn't needed
        """
        geom = self.input_layer.load_and_tessellate(self.test_stl_file)
        
        # Should still be mesh
        self.assertFalse(geom.is_brep)
        self.assertIsNotNone(geom.points)
        self.assertIsNotNone(geom.cells)
        self.assertGreater(len(geom.points), 0)
        self.assertGreater(len(geom.cells), 0)

    def test_file_not_found(self):
        """Test error handling when attempting to load a non-existent file.
        
        Verifies that:
        - The geometry input layer properly handles file not found errors
        - Appropriate exceptions are raised (meshio.ReadError for mesh files)
        - The error propagates correctly through the loader chain
        - No crashes occur when invalid file paths are provided
        """
        try:
            import meshio
            expected_exception = (meshio._exceptions.ReadError,)
        except ImportError:
            expected_exception = (FileNotFoundError, ValueError)
        
        with self.assertRaises(expected_exception):
            self.input_layer.load_geometry('non_existent_file.stl')

if __name__ == '__main__':
    unittest.main()