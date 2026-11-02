cmake_minimum_required(VERSION 3.21)

project(gui-control LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Quick Network)

add_library(guicontrol SHARED
    hook/Scene.cpp
    hook/Scene.hpp
    hook/Actions.cpp
    hook/Actions.hpp
    hook/ControlServer.cpp
    hook/ControlServer.hpp
    hook/Hook.cpp
)

target_include_directories(guicontrol PRIVATE hook)

target_link_libraries(guicontrol PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Quick
    Qt6::Network
)

set_target_properties(guicontrol PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
)

add_executable(gui-control-launch hook/launcher.c)

set_target_properties(gui-control-launch PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}
    AUTOMOC OFF
)
