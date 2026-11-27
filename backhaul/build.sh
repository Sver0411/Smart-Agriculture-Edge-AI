#!/usr/bin/env bash
set -euo pipefail
if [[ $(uname -s) != Linux || $# != 2 ]]; then
    echo "Usage on Linux: bash backhaul/build.sh PINNED_SCHEDULER_CHECKOUT BUILD_DIR" >&2
    exit 2
fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
upstream=$(realpath -- "$1")
build=$(realpath -m -- "$2")
revision=1b3bea9f8933cf70713610fa550aa4ab670d71e4
if [[ $(git -C "$upstream" rev-parse HEAD) != "$revision" ]] ||
   ! git -C "$upstream" diff --quiet "$revision" -- scripts/build.sh CMakeLists.txt patches src; then
    echo "Expected unmodified IoT-MPQUIC-Scheduler build inputs at $revision" >&2
    exit 1
fi
IOT_BUILD_DIR="$build" bash "$upstream/scripts/build.sh"
mkdir -p "$build/bridge"
# Reuse the upstream configured targets, including its exact XQUIC patches and TLS build.
cmake -S "$upstream" -B "$build/app" -DCMAKE_PROJECT_TOP_LEVEL_INCLUDES="$here/register.cmake" \
    -DAGRI_BRIDGE_SOURCE="$here" -DAGRI_BRIDGE_OUTPUT="$build/bridge"
cmake --build "$build/app" --target agri-mpquic -j "${JOBS:-$(nproc)}"
