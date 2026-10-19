include(FetchContent)
file(READ "${CMAKE_CURRENT_LIST_DIR}/../manifests/runtime-deps.json" KHCOM_DEPENDENCIES)
set(KHCOM_SELECTED_DEPS mgba json miniz)
if(KHCOM_BUILD_DESKTOP OR KHCOM_BUILD_DIAGNOSTIC)
  list(APPEND KHCOM_SELECTED_DEPS sdl)
endif()
if(KHCOM_BUILD_DESKTOP)
  list(APPEND KHCOM_SELECTED_DEPS imgui)
endif()
foreach(dependency IN LISTS KHCOM_SELECTED_DEPS)
  string(JSON dep_url GET "${KHCOM_DEPENDENCIES}" sources ${dependency} url)
  string(JSON dep_hash GET "${KHCOM_DEPENDENCIES}" sources ${dependency} sha256)
  string(JSON dep_archive GET "${KHCOM_DEPENDENCIES}" sources ${dependency} archive)
  set(local_archive "${CMAKE_CURRENT_LIST_DIR}/../.deps/${dep_archive}")
  if(EXISTS "${local_archive}")
    set(dep_url "${local_archive}")
  endif()
  if(dependency STREQUAL "mgba")
    FetchContent_Declare(${dependency} URL "${dep_url}"
      URL_HASH "SHA256=${dep_hash}" DOWNLOAD_EXTRACT_TIMESTAMP TRUE
      PATCH_COMMAND "${CMAKE_COMMAND}" "-DSOURCE_DIR=<SOURCE_DIR>"
        -P "${CMAKE_CURRENT_LIST_DIR}/PatchMgbaVersion.cmake")
  else()
    FetchContent_Declare(${dependency} URL "${dep_url}"
      URL_HASH "SHA256=${dep_hash}" DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
  endif()
endforeach()

# Only the software GBA core and memory/file adapters. No GUI, network debug,
# recording, scripting, GB core, external BIOS discovery or optional libraries.
set(LIBMGBA_ONLY ON)
set(M_CORE_GBA ON CACHE BOOL "" FORCE)
set(M_CORE_GB OFF CACHE BOOL "" FORCE)
set(SKIP_GIT ON)
foreach(feature BUILD_QT BUILD_SDL BUILD_LIBRETRO BUILD_OPENEMU BUILD_GL BUILD_GLES2
    BUILD_GLES3 USE_DEBUGGERS USE_GDB_STUB USE_EDITLINE USE_FFMPEG USE_ZLIB USE_PNG
    USE_LIBZIP USE_MINIZIP USE_SQLITE3 USE_ELF USE_LZMA USE_LUA USE_DISCORD_RPC ENABLE_SCRIPTING)
  set(${feature} OFF CACHE BOOL "" FORCE)
endforeach()
FetchContent_MakeAvailable(mgba)
string(JSON KHCOM_PINNED_CORE_VERSION GET "${KHCOM_DEPENDENCIES}" sources mgba version)

if(KHCOM_BUILD_DESKTOP OR KHCOM_BUILD_DIAGNOSTIC)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SDL_INSTALL OFF CACHE BOOL "" FORCE)
# The codeload tag archive has no REVISION.txt. Without this official
# override SDL's git_describe walks into the containing application's repo.
string(JSON KHCOM_PINNED_SDL_REVISION GET "${KHCOM_DEPENDENCIES}" sources sdl build_revision)
string(JSON sdl_version GET "${KHCOM_DEPENDENCIES}" sources sdl version)
if(NOT KHCOM_PINNED_SDL_REVISION STREQUAL "SDL-${sdl_version}")
  message(FATAL_ERROR "SDL version/revision manifest mismatch")
endif()
set(SDL_REVISION "${KHCOM_PINNED_SDL_REVISION}" CACHE STRING "Pinned archive revision, independent of parent Git" FORCE)
FetchContent_MakeAvailable(sdl)
endif()

# Portable patch/storage model dependencies. They contain no game resources.
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
set(JSON_Install OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(json miniz)
if(KHCOM_BUILD_DESKTOP)
FetchContent_MakeAvailable(imgui)
add_library(khcom_imgui STATIC
  "${imgui_SOURCE_DIR}/imgui.cpp" "${imgui_SOURCE_DIR}/imgui_draw.cpp"
  "${imgui_SOURCE_DIR}/imgui_tables.cpp" "${imgui_SOURCE_DIR}/imgui_widgets.cpp"
  "${imgui_SOURCE_DIR}/backends/imgui_impl_sdl3.cpp"
  "${imgui_SOURCE_DIR}/backends/imgui_impl_sdlrenderer3.cpp")
target_include_directories(khcom_imgui PUBLIC "${imgui_SOURCE_DIR}" "${imgui_SOURCE_DIR}/backends")
target_link_libraries(khcom_imgui PUBLIC SDL3::SDL3-static)
# Embed only the freely licensed application font, never assets from the ROM.
file(READ "${imgui_SOURCE_DIR}/misc/fonts/DroidSans.ttf" font_hex HEX)
string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," font_bytes "${font_hex}")
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/generated")
file(WRITE "${CMAKE_BINARY_DIR}/generated/ui_font.hpp" "#pragma once\ninline unsigned char khcom_ui_font[] = {${font_bytes}};\n")

endif()

# Retain the selected upstream license texts beside diagnostic builds. Release
# packaging must additionally ship corresponding sources/relink materials.
set(notices "${CMAKE_BINARY_DIR}/third-party-notices.txt")
file(WRITE "${notices}" "KHCoM diagnostic dependencies; not a release compliance bundle.\n")
foreach(dependency IN LISTS KHCOM_SELECTED_DEPS)
  string(JSON version GET "${KHCOM_DEPENDENCIES}" sources ${dependency} version)
  string(JSON count LENGTH "${KHCOM_DEPENDENCIES}" sources ${dependency} license_files)
  math(EXPR last "${count}-1")
  foreach(index RANGE ${last})
    string(JSON license_path GET "${KHCOM_DEPENDENCIES}" sources ${dependency} license_files ${index})
    file(READ "${${dependency}_SOURCE_DIR}/${license_path}" license_text)
    file(APPEND "${notices}" "\n${dependency} ${version}: ${license_path}\n${license_text}\n")
  endforeach()
endforeach()
file(APPEND "${notices}" "\nmGBA src/util/hash.c: MurmurHash3 was written by Austin Appleby and placed in the public domain.\n")
file(APPEND "${notices}" "\nLocal build-only modification: cmake/PatchMgbaVersion.cmake forwards SKIP_GIT=ON to mGBA's version-info generator; emulation sources are unchanged.\n")

if(KHCOM_BUILD_DESKTOP)
file(READ "${CMAKE_CURRENT_LIST_DIR}/../platform/licenses/DroidSans-Apache-2.0.txt" font_license)
file(APPEND "${notices}" "\nDroid Sans by Steve Matteson, Apache-2.0:\n${font_license}\n")

file(APPEND "${notices}" "\nCRT shader: SDL testgpurender_effects_CRT, from pinned SDL source (Zlib); original Lightweight CRT Effect by pxlforge, CC0-1.0, https://godotshaders.com/shader/lightweight-crt-effect/ . Source and compiled MSL/SPIR-V/DXIL variants are in the corresponding SDL source bundle.\n")

endif()
