cmake_minimum_required(VERSION 3.10)
project(ManufacturabilityEval)

# 1. Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 2. Find CGAL (Ensure you ran 'brew install cgal' first)
find_package(CGAL REQUIRED)

# 3. Fetch libigl
include(FetchContent)
FetchContent_Declare(
  libigl
  GIT_REPOSITORY https://github.com/libigl/libigl.git
  GIT_TAG v2.5.0
)
FetchContent_MakeAvailable(libigl)

# 4. Define the executable
# Format: add_executable(TARGET_NAME SOURCE_FILES)
add_executable(eval_tool hello.cpp)

# 5. Link libraries using the PUBLIC keyword to avoid the previous error
target_link_libraries(eval_tool 
    PUBLIC 
        CGAL::CGAL 
        igl::core
)

