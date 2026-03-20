
#include <iostream>
#include <filesystem>

#include <CGAL/Simple_cartesian.h>
#include <igl/readOFF.h>
#include <Eigen/Core>

typedef CGAL::Simple_cartesian<double> Kernel;
typedef Kernel::Point_2 Point_2;

int main() {
    Point_2 p(0, 0), q(1, 1);
    std::cout << "CGAL Point p: " << p << std::endl;
    std::cout << "Distance squared: " << CGAL::squared_distance(p, q) << std::endl;

    Eigen::MatrixXd V;
    Eigen::MatrixXi F;

    // Get current working directory
    std::filesystem::path full_path = std::filesystem::current_path() / ".." / "cube.off";
    std::string mesh_path = full_path.string();
    if (igl::readOFF(mesh_path, V, F)) {
        std::cout << "Vertices: " << V.rows() << std::endl;
        std::cout << "Faces:    " << F.rows() << std::endl;
    } else {
        std::cout << "Could not read mesh file." << std::endl;
    }

    return 0;
}



