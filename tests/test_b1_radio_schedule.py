from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def test_portable_radio_deadlines_with_sanitizers(tmp_path):
    exe=tmp_path/'schedule'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I',str(ROOT/'firmware/b1/main'),str(ROOT/'tests/c_host/b1_radio_schedule.c'),
        str(ROOT/'firmware/b1/main/b1_radio_schedule.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
