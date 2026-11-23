cmake_minimum_required(VERSION 3.21)
project(HiFineThumbnail LANGUAGES CXX)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "Build the thumbnail provider for 64-bit Windows.")
endif()
if(NOT HIFINE_HEIF_DLL MATCHES "^[a-zA-Z0-9._-]+[.]dll$")
  message(FATAL_ERROR "Set HIFINE_HEIF_DLL to the libheif DLL filename in the application bundle.")
endif()

# Only the C API declarations are needed. The actual decoder ships with pillow-heif.
set(include_dir "${CMAKE_CURRENT_BINARY_DIR}/include")
file(MAKE_DIRECTORY "${include_dir}/libheif")
set(header_url "https://raw.githubusercontent.com/strukturag/libheif/v1.17.6/libheif")
file(DOWNLOAD "${header_url}/heif.h" "${include_dir}/libheif/heif.h"
  EXPECTED_HASH SHA256=eab07972c403d536841447d6d1c3e30396cf251e8a6e62367479f7840c599fba TLS_VERIFY ON)
file(DOWNLOAD "${header_url}/heif_version.h.in" "${include_dir}/libheif/heif_version.h.in"
  EXPECTED_HASH SHA256=9aec4a30c9e0bbe7b09145020b0ca07256ce4986a068a3119c80902835db8e30 TLS_VERIFY ON)
set(PROJECT_VERSION_MAJOR 1)
set(PROJECT_VERSION_MINOR 17)
set(PROJECT_VERSION_PATCH 6)
configure_file("${include_dir}/libheif/heif_version.h.in" "${include_dir}/libheif/heif_version.h" @ONLY)

add_library(HiFineThumbnail SHARED provider.cpp provider.def)
target_include_directories(HiFineThumbnail PRIVATE "${include_dir}")
target_compile_definitions(HiFineThumbnail PRIVATE HIFINE_HEIF_DLL=L"${HIFINE_HEIF_DLL}" UNICODE _UNICODE NOMINMAX)
target_compile_features(HiFineThumbnail PRIVATE cxx_std_17)
target_link_libraries(HiFineThumbnail PRIVATE gdi32 ole32 uuid)
set_property(TARGET HiFineThumbnail PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

option(HIFINE_THUMBNAIL_TEST "Build the stream-based COM smoke test" OFF)
if(HIFINE_THUMBNAIL_TEST)
  add_executable(thumbnail_smoke ../../../tests/windows/thumbnail_smoke.cpp)
  target_compile_definitions(thumbnail_smoke PRIVATE UNICODE _UNICODE)
  target_link_libraries(thumbnail_smoke PRIVATE gdi32 ole32 shlwapi uuid)
  target_compile_features(thumbnail_smoke PRIVATE cxx_std_17)
endif()
