cmake_minimum_required(VERSION 3.20)

project(lightweave_uno_runner LANGUAGES CXX)

option(LIGHTWEAVE_WITH_NCNN "Build the strict ncnn Vulkan reconstruction backend" OFF)

add_executable(lightweave-uno-runner
    src/entropy_decoder.cpp
    src/main.cpp
)

target_include_directories(lightweave-uno-runner PRIVATE include)
target_compile_features(lightweave-uno-runner PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(lightweave-uno-runner PRIVATE /W4 /permissive-)
else()
    target_compile_options(lightweave-uno-runner PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

if(LIGHTWEAVE_WITH_NCNN)
    find_package(ncnn 20260526 REQUIRED CONFIG)
    target_sources(lightweave-uno-runner PRIVATE src/ncnn_decoder.cpp)
    target_link_libraries(lightweave-uno-runner PRIVATE ncnn)
    target_compile_definitions(lightweave-uno-runner PRIVATE LIGHTWEAVE_WITH_NCNN=1)
endif()

install(TARGETS lightweave-uno-runner RUNTIME DESTINATION bin)
