from pathlib import Path
import shutil
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
def test_ack_ordering(tmp_path):
    main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense'
    binary=tmp_path/'ordering';cc=shutil.which('cc')
    if not cc:pytest.fail('C compiler required')
    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1','-pthread','-fsanitize=address,undefined',
        '-I',str(ROOT/'third_party/cjson'),'-I',str(ROOT/'tests/c_host/stubs'),'-I',str(main),'-I',str(trust),'-I',str(adaptive),
        str(ROOT/'tests/c_host/b1_ack_ordering.c'),str(main/'b1_policy.c'),str(main/'b1_queue.c'),str(main/'b1_telemetry.c'),str(main/'b1_outbox.c'),
        str(trust/'sensor_trust.c'),str(adaptive/'adaptive_scheduler.c'),str(adaptive/'change_detector.c'),
        str(ROOT/'third_party/cjson/cJSON.c'),'-lm','-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
