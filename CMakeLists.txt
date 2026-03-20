cmake_minimum_required(VERSION 3.12) # bumped slightly for better FetchContent support
project(ManufacturabilityEval)

# 1. Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 2. Find Eigen3 (Crucial for Ubuntu/macOS parity)
# This finds the system-wide Eigen installed via 'apt' or 'brew'
find_package(Eigen3 REQUIRED)

# 3. Find CGAL
find_package(CGAL REQUIRED)

# 4. Fetch libigl
# FetchContent is great for cross-platform because it downloads 
# the source to the 'build' folder, keeping your OS-specific files separate.
include(FetchContent)
FetchContent_Declare(
  libigl
  GIT_REPOSITORY https://github.com/libigl/libigl.git
  GIT_TAG v2.5.0
)
FetchContent_MakeAvailable(libigl)

# 5. Define the executable
add_executable(eval_tool hello.cpp)

# 6. Link libraries
# We add Eigen3::Eigen explicitly to ensure headers are found on both OSs.
target_link_libraries(eval_tool 
    PUBLIC 
        CGAL::CGAL 
        Eigen3::Eigen
        igl::core
)