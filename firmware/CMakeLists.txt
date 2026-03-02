cmake_minimum_required(VERSION 3.17)

# --- Pico SDK ---
# Use PICO_SDK_PATH if set; otherwise fetch from GitHub.
if (DEFINED ENV{PICO_SDK_PATH} AND (NOT PICO_SDK_PATH))
    set(PICO_SDK_PATH $ENV{PICO_SDK_PATH})
endif()

if (NOT PICO_SDK_PATH)
    include(FetchContent)
    FetchContent_Declare(
        pico_sdk
        GIT_REPOSITORY https://github.com/raspberrypi/pico-sdk.git
        GIT_TAG        2.2.0
        GIT_SUBMODULES lib/tinyusb
        GIT_SUBMODULES_RECURSE FALSE
    )
    message(STATUS "Downloading Raspberry Pi Pico SDK...")
    FetchContent_Populate(pico_sdk)
    set(PICO_SDK_PATH ${pico_sdk_SOURCE_DIR})
endif()

set(PICO_BOARD pico2 CACHE STRING "Target board")

include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(riscyv02_firmware C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# --- Firmware ---
add_executable(riscyv02_firmware main.c)

target_link_libraries(riscyv02_firmware
    pico_stdlib
    pico_multicore
)

pico_enable_stdio_usb(riscyv02_firmware 1)
pico_enable_stdio_uart(riscyv02_firmware 0)

target_compile_definitions(riscyv02_firmware PRIVATE
    PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=3000
)

pico_add_extra_outputs(riscyv02_firmware)
