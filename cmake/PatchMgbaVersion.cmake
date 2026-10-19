# mGBA 0.10.5 does not forward SKIP_GIT to its build-time version generator.
# Patch only this verified build rule; never infer a core revision from the
# containing application's Git repository. Original archives remain intact.
set(target "${SOURCE_DIR}/CMakeLists.txt")
file(SHA256 "${target}" observed)
set(original "df09980a09932d99b2752d0efd5f3629c25a4b3e99f5e05db539b6477afa8903")
file(READ "${target}" content)
set(needle "\t-DBINARY_NAME=\${BINARY_NAME}\n")
set(replacement "${needle}\t-DSKIP_GIT=ON\n")
if(observed STREQUAL original)
  string(REPLACE "${needle}" "${replacement}" patched "${content}")
  if(patched STREQUAL content)
    message(FATAL_ERROR "The verified mGBA version rule was not found")
  endif()
  file(WRITE "${target}" "${patched}")
else()
  # Verify an already-patched copy by reversing exactly our addition. This
  # accepts no unrelated modifications and makes repeated population safe.
  string(REPLACE "${replacement}" "${needle}" restored "${content}")
  string(SHA256 restored_hash "${restored}")
  if(NOT restored_hash STREQUAL original)
    message(FATAL_ERROR "mGBA CMakeLists.txt differs from the pinned source and local patch")
  endif()
endif()
