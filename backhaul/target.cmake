file(READ "${CMAKE_SOURCE_DIR}/src/transport/path_affinity.c" affinity)
# Use the existing binding table as a ring for long-lived connections. Full stream
# identity checks and waiting for the previous occupant's close prevent slot aliasing.
string(REPLACE "sid / 4 >= IOT_MAX_RECORDS || !control->bindings[sid / 4].id"
               "sid / 4 >= UINT32_MAX || control->bindings[(sid / 4) % IOT_MAX_RECORDS].id != sid / 4 + 1"
               affinity "${affinity}")
string(REPLACE "&control->bindings[sid / 4]" "&control->bindings[(sid / 4) % IOT_MAX_RECORDS]"
               affinity "${affinity}")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/agri_affinity.c" CONTENT "${affinity}")
add_executable(agri-mpquic
    "${AGRI_BRIDGE_SOURCE}/endpoint.c" "${CMAKE_CURRENT_BINARY_DIR}/agri_affinity.c"
    src/transport/iot_wire.c src/gateway/iot_queue.c src/receiver/iot_receive.c
    src/scheduler/scheduler.c src/scheduler/proposed.c)
target_compile_features(agri-mpquic PRIVATE c_std_11)
target_compile_options(agri-mpquic PRIVATE -Wall -Wextra -Werror)
target_include_directories(agri-mpquic PRIVATE src src/transport)
target_include_directories(agri-mpquic SYSTEM PRIVATE "${XQUIC_SOURCE_DIR}/include" "${XQUIC_SOURCE_DIR}" "${SSL_INC_PATH}")
target_link_libraries(agri-mpquic PRIVATE xquic-static ${SSL_LIB_PATH} Threads::Threads m dl)
set_target_properties(agri-mpquic PROPERTIES LINKER_LANGUAGE CXX RUNTIME_OUTPUT_DIRECTORY "${AGRI_BRIDGE_OUTPUT}")
