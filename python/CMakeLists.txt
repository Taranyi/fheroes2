find_package(Python3 COMPONENTS Development REQUIRED)

set(PYFHEROES2_SOURCES
    pyfheroes2.cpp
)

Python3_add_library(fheroes2_py MODULE ${PYFHEROES2_SOURCES})

set_target_properties(fheroes2_py PROPERTIES
    PREFIX ""
    OUTPUT_NAME "fheroes2"
)

# Ensure PIC for shared library
set_target_properties(fheroes2_py PROPERTIES POSITION_INDEPENDENT_CODE ON)

# Include engine headers
target_include_directories(fheroes2_py PRIVATE
    ${CMAKE_SOURCE_DIR}/src/fheroes2/agg
    ${CMAKE_SOURCE_DIR}/src/fheroes2/ai
    ${CMAKE_SOURCE_DIR}/src/fheroes2/army
    ${CMAKE_SOURCE_DIR}/src/fheroes2/audio
    ${CMAKE_SOURCE_DIR}/src/fheroes2/battle
    ${CMAKE_SOURCE_DIR}/src/fheroes2/campaign
    ${CMAKE_SOURCE_DIR}/src/fheroes2/castle
    ${CMAKE_SOURCE_DIR}/src/fheroes2/dialog
    ${CMAKE_SOURCE_DIR}/src/fheroes2/editor
    ${CMAKE_SOURCE_DIR}/src/fheroes2/game
    ${CMAKE_SOURCE_DIR}/src/fheroes2/gui
    ${CMAKE_SOURCE_DIR}/src/fheroes2/h2d
    ${CMAKE_SOURCE_DIR}/src/fheroes2/heroes
    ${CMAKE_SOURCE_DIR}/src/fheroes2/image
    ${CMAKE_SOURCE_DIR}/src/fheroes2/kingdom
    ${CMAKE_SOURCE_DIR}/src/fheroes2/maps
    ${CMAKE_SOURCE_DIR}/src/fheroes2/monster
    ${CMAKE_SOURCE_DIR}/src/fheroes2/resource
    ${CMAKE_SOURCE_DIR}/src/fheroes2/spell
    ${CMAKE_SOURCE_DIR}/src/fheroes2/system
    ${CMAKE_SOURCE_DIR}/src/fheroes2/world
)

# Link with fheroes2 core library and engine
if(TARGET fheroes2core)
    target_link_libraries(fheroes2_py PRIVATE fheroes2core engine Python3::Python)
else()
    target_link_libraries(fheroes2_py PRIVATE engine Python3::Python)
endif()
