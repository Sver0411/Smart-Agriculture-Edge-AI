"""Compile real portable firmware delivery code, with injected durable storage."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_firmware_outbox_faults(tmp_path):
    cc = shutil.which('cc')
    if not cc: pytest.fail('C compiler required for firmware acceptance')
    binary = tmp_path/'outbox'
    subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I', str(ROOT/'firmware/b1/main'),
                    str(ROOT/'tests/c_host/b1_outbox_faults.c'),
                    str(ROOT/'firmware/b1/main/b1_outbox.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
