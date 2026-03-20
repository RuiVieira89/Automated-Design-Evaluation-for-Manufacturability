# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-src"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-build"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/tmp"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/src/libigl-populate-stamp"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/src"
  "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/src/libigl-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/src/libigl-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/rui/dev/Automated-Design-Evaluation-for-Manufacturability/build/_deps/libigl-subbuild/libigl-populate-prefix/src/libigl-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
