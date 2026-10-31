###########################################################################
#   fheroes2: https://github.com/ihhub/fheroes2                           #
#   Copyright (C) 2022 - 2026                                             #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
###########################################################################

file(GLOB_RECURSE FHEROES2_SOURCES CONFIGURE_DEPENDS *.cpp)

if(ENABLE_PYTHON_ENV)
	# Only the entry point and environment adapters need this opt-in. Game rules stay shared.
	set_property(SOURCE game/fheroes2.cpp game/python_env.cpp game/python_env_world.cpp game/python_env_controllers.cpp game/python_env_castle.cpp game/python_env_army.cpp game/python_env_battle.cpp game/python_env_views.cpp APPEND PROPERTY COMPILE_DEFINITIONS FHEROES2_ENABLE_PYTHON_ENV)

	# Explicit test target: excluded from game builds and absent when the desktop adapter is disabled.
	add_executable(fheroes2_headless_checks EXCLUDE_FROM_ALL ${PROJECT_SOURCE_DIR}/python/tests/cpp/headless_checks.cpp)
	target_link_libraries(fheroes2_headless_checks PRIVATE engine)
	set_target_properties(fheroes2_headless_checks PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${PROJECT_BINARY_DIR})
endif()

add_compile_options("$<$<COMPILE_LANG_AND_ID:C,AppleClang,Clang,GNU>:${GNU_CC_WARN_OPTS}>")
add_compile_options("$<$<COMPILE_LANG_AND_ID:CXX,AppleClang,Clang,GNU>:${GNU_CXX_WARN_OPTS}>")
add_compile_options("$<$<OR:$<COMPILE_LANG_AND_ID:C,MSVC>,$<COMPILE_LANG_AND_ID:CXX,MSVC>>:${MSVC_CC_WARN_OPTS}>")

if(MACOS_APP_BUNDLE)
	set(FHEROES2_ICON ${CMAKE_CURRENT_SOURCE_DIR}/../resources/fheroes2.icns)
	set_source_files_properties(${FHEROES2_ICON} PROPERTIES MACOSX_PACKAGE_LOCATION Resources)

	add_executable(fheroes2 MACOSX_BUNDLE ${FHEROES2_ICON} ${FHEROES2_SOURCES} ${TRANSLATION_DATA})

	target_compile_definitions(
		fheroes2
		PRIVATE
		$<$<CONFIG:Debug>:WITH_DEBUG>
		$<$<BOOL:${MACOS_APP_BUNDLE}>:MACOS_APP_BUNDLE>
		)

	target_link_libraries(fheroes2 "-framework CoreFoundation")

	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_BUNDLE_NAME ${CMAKE_PROJECT_NAME})
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_BUNDLE_VERSION ${CMAKE_PROJECT_VERSION})
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_EXECUTABLE_NAME fheroes2)
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_GUI_IDENTIFIER org.fheroes2.${CMAKE_PROJECT_NAME})
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_ICON_FILE fheroes2.icns)
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/../resources/Info.plist.in)
	set_target_properties(fheroes2 PROPERTIES MACOSX_BUNDLE_SHORT_VERSION_STRING ${CMAKE_PROJECT_VERSION})
else(MACOS_APP_BUNDLE)
	cmake_path(
		ABSOLUTE_PATH FHEROES2_DATA
		BASE_DIRECTORY ${CMAKE_INSTALL_PREFIX}
		NORMALIZE
		OUTPUT_VARIABLE FHEROES2_DATA_ABSOLUTE
		)

	add_executable(
		fheroes2
		${FHEROES2_SOURCES}
		${CMAKE_CURRENT_SOURCE_DIR}/../resources/fheroes2.manifest
		${CMAKE_CURRENT_SOURCE_DIR}/../resources/fheroes2.rc
		)

	target_compile_definitions(
		fheroes2
		PRIVATE
		# MSVC: suppress deprecation warnings
		$<$<OR:$<COMPILE_LANG_AND_ID:C,MSVC>,$<COMPILE_LANG_AND_ID:CXX,MSVC>>:_CRT_SECURE_NO_WARNINGS>
		$<$<CONFIG:Debug>:WITH_DEBUG>
		FHEROES2_DATA=${FHEROES2_DATA_ABSOLUTE}
		)

	# Copy executable to root of the project.
	add_custom_command(
		TARGET fheroes2 POST_BUILD
		COMMAND ${CMAKE_COMMAND} -E copy
		$<TARGET_FILE:fheroes2>
		${PROJECT_SOURCE_DIR}/$<TARGET_FILE_NAME:fheroes2>
		)

	install(TARGETS fheroes2 DESTINATION ${CMAKE_INSTALL_BINDIR})
endif(MACOS_APP_BUNDLE)

target_include_directories(
	fheroes2
	PRIVATE
	agg
	ai
	army
	audio
	battle
	campaign
	castle
	dialog
	editor
	game
	gui
	h2d
	heroes
	image
	kingdom
	maps
	monster
	resource
	spell
	system
	world
	)

target_link_libraries(
	fheroes2
	engine
	${USE_SDL_VERSION}::${USE_SDL_VERSION}main
	)

if(ENABLE_PYTHON_ENV)
	# Native test-data builder only: never part of normal game builds or the production protocol.
	set(ARTIFACT_FIXTURE_SOURCES ${FHEROES2_SOURCES})
	list(FILTER ARTIFACT_FIXTURE_SOURCES EXCLUDE REGEX "/game/fheroes2\\.cpp$")
	add_executable(fheroes2_artifact_fixture EXCLUDE_FROM_ALL ${PROJECT_SOURCE_DIR}/python/tests/cpp/artifact_fixture.cpp ${ARTIFACT_FIXTURE_SOURCES})
	target_include_directories(fheroes2_artifact_fixture PRIVATE $<TARGET_PROPERTY:fheroes2,INCLUDE_DIRECTORIES>)
	target_compile_definitions(fheroes2_artifact_fixture PRIVATE FHEROES2_ENABLE_PYTHON_ENV $<TARGET_PROPERTY:fheroes2,COMPILE_DEFINITIONS>)
	target_link_libraries(fheroes2_artifact_fixture PRIVATE $<TARGET_PROPERTY:fheroes2,LINK_LIBRARIES>)
	set_target_properties(fheroes2_artifact_fixture PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${PROJECT_BINARY_DIR})
endif()
