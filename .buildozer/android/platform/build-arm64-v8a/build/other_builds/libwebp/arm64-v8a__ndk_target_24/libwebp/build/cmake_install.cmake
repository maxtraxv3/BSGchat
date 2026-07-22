# Install script for directory: /home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/installation")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "0")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objdump")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/src/libwebpdecoder.pc")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/src/libwebp.pc")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/src/demux/libwebpdemux.pc")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/dwebp")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/dwebp")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/cwebp")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/cwebp")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/src/mux/libwebpmux.pc")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/img2webp")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/img2webp")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/webpinfo")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpinfo")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/webpmux")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webpmux")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/get_disto")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/get_disto")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/bin" TYPE EXECUTABLE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/webp_quality")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/bin/webp_quality")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE STATIC_LIBRARY FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/libcpufeatures.a")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/libwebpdecoder.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdecoder.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/webp" TYPE FILE FILES
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/decode.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/types.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/libwebp.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebp.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/webp" TYPE FILE FILES
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/decode.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/encode.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/types.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/libwebpdemux.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpdemux.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/webp" TYPE FILE FILES
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/decode.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/demux.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/mux_types.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/types.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so")
    file(RPATH_CHECK
         FILE "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so"
         RPATH "")
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/libwebpmux.so")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/home/maxtrax/.buildozer/android/platform/android-ndk-r26b/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libwebpmux.so")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/webp" TYPE FILE FILES
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/mux.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/mux_types.h"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/src/webp/types.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/share/WebP/cmake/WebPTargets.cmake")
    file(DIFFERENT _cmake_export_file_changed FILES
         "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/share/WebP/cmake/WebPTargets.cmake"
         "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/CMakeFiles/Export/3dd5097d708f2adcdf4871ccc089782a/WebPTargets.cmake")
    if(_cmake_export_file_changed)
      file(GLOB _cmake_old_config_files "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/share/WebP/cmake/WebPTargets-*.cmake")
      if(_cmake_old_config_files)
        string(REPLACE ";" ", " _cmake_old_config_files_text "${_cmake_old_config_files}")
        message(STATUS "Old export file \"$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/share/WebP/cmake/WebPTargets.cmake\" will be replaced.  Removing files [${_cmake_old_config_files_text}].")
        unset(_cmake_old_config_files_text)
        file(REMOVE ${_cmake_old_config_files})
      endif()
      unset(_cmake_old_config_files)
    endif()
    unset(_cmake_export_file_changed)
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/WebP/cmake" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/CMakeFiles/Export/3dd5097d708f2adcdf4871ccc089782a/WebPTargets.cmake")
  if(CMAKE_INSTALL_CONFIG_NAME MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
    file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/WebP/cmake" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/CMakeFiles/Export/3dd5097d708f2adcdf4871ccc089782a/WebPTargets-release.cmake")
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/WebP/cmake" TYPE FILE FILES
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/WebPConfigVersion.cmake"
    "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/WebPConfig.cmake"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/cwebp.1")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/dwebp.1")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/img2webp.1")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/vwebp.1")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/webpmux.1")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "doc" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/share/man/man1" TYPE FILE FILES "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/man/webpinfo.1")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
if(CMAKE_INSTALL_COMPONENT)
  if(CMAKE_INSTALL_COMPONENT MATCHES "^[a-zA-Z0-9_.+-]+$")
    set(CMAKE_INSTALL_MANIFEST "install_manifest_${CMAKE_INSTALL_COMPONENT}.txt")
  else()
    string(MD5 CMAKE_INST_COMP_HASH "${CMAKE_INSTALL_COMPONENT}")
    set(CMAKE_INSTALL_MANIFEST "install_manifest_${CMAKE_INST_COMP_HASH}.txt")
    unset(CMAKE_INST_COMP_HASH)
  endif()
else()
  set(CMAKE_INSTALL_MANIFEST "install_manifest.txt")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/home/maxtrax/Projects/e2e-asciline-chat2/.buildozer/android/platform/build-arm64-v8a/build/other_builds/libwebp/arm64-v8a__ndk_target_24/libwebp/build/${CMAKE_INSTALL_MANIFEST}"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
