from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def test_production_registration_with_sanitizers(tmp_path):
    binary=tmp_path/"registration"
    subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-deprecated-declarations","-fsanitize=address,undefined",
        "-I",str(ROOT/"firmware/b1/main"),"-I",str(ROOT/"third_party/cjson"),
        str(ROOT/"tests/c_host/b1_registration.c"),str(ROOT/"firmware/b1/main/b1_registration.c"),
        str(ROOT/"third_party/cjson/cJSON.c"),"-lm","-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
