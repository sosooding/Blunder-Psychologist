cmake_minimum_required(VERSION 3.20)
project(blunder_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Default to an optimized build; the determinism guarantee is per-binary, so build flags
# only need to be fixed within one image, not across configurations.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

option(BLUNDER_BUILD_TESTS "Build the Catch2 test suite" ON)

# The pybind11 module is only built under scikit-build-core (wheel builds); a plain
# `cmake -S engine` (CI's cpp-build, local C++ dev loop) builds just the core lib + tests
# and needs no Python toolchain.
if(DEFINED SKBUILD)
  set(_blunder_python_default ON)
else()
  set(_blunder_python_default OFF)
endif()
option(BLUNDER_BUILD_PYTHON "Build the pybind11 module blunder_engine" ${_blunder_python_default})

# ---------------------------------------------------------------------------
# Core analysis library. chess.hpp is header-only (vendored); the UCI driver uses
# POSIX process/pipe APIs (the engine only ever builds inside the Linux containers).
# ---------------------------------------------------------------------------
add_library(blunder_core STATIC
  src/uci_engine.cpp
  src/engine_pool.cpp
  src/serialize.cpp
)
target_include_directories(blunder_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor
)
target_compile_features(blunder_core PUBLIC cxx_std_20)
# The static core is linked into the pybind11 shared module, so it must be position-independent.
set_target_properties(blunder_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

find_package(Threads REQUIRED)
target_link_libraries(blunder_core PUBLIC Threads::Threads)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if(BLUNDER_BUILD_TESTS)
  enable_testing()

  add_library(catch2_amalgamated STATIC vendor/catch_amalgamated.cpp)
  target_include_directories(catch2_amalgamated PUBLIC vendor)
  target_compile_features(catch2_amalgamated PUBLIC cxx_std_20)

  add_executable(blunder_tests
    tests/test_score.cpp
    tests/test_engine.cpp
  )
  target_link_libraries(blunder_tests PRIVATE blunder_core catch2_amalgamated)
  add_test(NAME blunder_tests COMMAND blunder_tests)
endif()

# ---------------------------------------------------------------------------
# pybind11 module (wheel build)
# ---------------------------------------------------------------------------
if(BLUNDER_BUILD_PYTHON)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(blunder_engine bindings/module.cpp)
  target_link_libraries(blunder_engine PRIVATE blunder_core)
  install(TARGETS blunder_engine LIBRARY DESTINATION .)
endif()
