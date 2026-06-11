cmake_minimum_required(VERSION 3.20)
project(blunder_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Phase 0 placeholder so CI has a real target to configure and build.
# Phase 1 vendors a header-only chess library, drives Stockfish over UCI, adds Catch2
# tests, and exposes a pybind11 module `blunder_engine`.
add_library(blunder_engine STATIC src/placeholder.cpp)
target_include_directories(blunder_engine PUBLIC include)
