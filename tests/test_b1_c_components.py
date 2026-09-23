"""Compile and execute the vendored pure-C detector/scheduler on the host."""
import pathlib
import shutil
import subprocess

import pytest


def test_b1_c_components(tmp_path):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    root = pathlib.Path(__file__).resolve().parents[1]
    trust = root / "firmware/b1/components/sensor_trust"
    adaptive = root / "firmware/b1/components/adaptive_sense"
    binary = tmp_path / "b1_components"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(trust),
        "-I", str(adaptive), str(root / "tests/c_host/b1_components.c"),
        str(trust / "sensor_trust.c"), str(adaptive / "change_detector.c"),
        str(adaptive / "adaptive_scheduler.c"), "-lm", "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
