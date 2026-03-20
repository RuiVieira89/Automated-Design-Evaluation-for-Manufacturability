cmake_minimum_required(VERSION 3.16)
project(geometry_project)

set(CMAKE_CXX_STANDARD 17)

# Dependencies
find_package(CGAL REQUIRED)
find_package(Eigen3 REQUIRED)

# If libigl is header-only
add_subdirectory(external/libigl)
# -------------------
# Main executable
# -------------------
add_executable(main_app main.cpp)

target_link_libraries(main_app
    CGAL::CGAL
    Eigen3::Eigen
    igl::core
)

# -------------------
# Test executable
# -------------------
add_executable(test_pkg_install tests/test_pkg_install.cpp)

target_link_libraries(test_pkg_install
    CGAL::CGAL
    Eigen3::Eigen
    igl::core
)
# Optional: enable `ctest`
enable_testing()
add_test(NAME EnvTest COMMAND test_env)