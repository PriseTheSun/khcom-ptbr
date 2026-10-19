include(FetchContent)
file(READ "${CMAKE_CURRENT_LIST_DIR}/../manifests/runtime-deps.json" KHCOM_DEPENDENCIES)
foreach(dependency mgba sdl)
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

set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST_LIBRARY OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SDL_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(sdl)

# Retain the selected upstream license texts beside diagnostic builds. Release
# packaging must additionally ship corresponding sources/relink materials.
set(notices "${CMAKE_BINARY_DIR}/third-party-notices.txt")
file(WRITE "${notices}" "KHCoM diagnostic dependencies; not a release compliance bundle.\n")
foreach(dependency mgba sdl)
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
