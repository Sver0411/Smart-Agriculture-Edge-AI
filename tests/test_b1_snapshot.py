"""Real C algorithm restore oracle, including sanitizer-checked hostile snapshots."""
from pathlib import Path
import json
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
CASES=[f'continuity-{m}' for m in ('healthy','event','range','missing','stuck','drift','spike')]+['unknown-time','sequence','epoch','truncated','bit-corruption','version','profile','state-capacity','clock-overflow','lease','counter-max','config-null']
@pytest.fixture(scope='module')
def snapshot_exe(tmp_path_factory):
    exe=tmp_path_factory.mktemp('snapshot')/'restore';main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense';radio=ROOT/'firmware/b1/components/agri_lora'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1','-fsanitize=address,undefined','-fno-omit-frame-pointer',
      '-I',str(main),'-I',str(trust),'-I',str(adaptive),'-I',str(radio),str(ROOT/'tests/c_host/b1_snapshot.c'),str(main/'b1_snapshot.c'),str(main/'b1_policy.c'),str(trust/'sensor_trust.c'),str(adaptive/'change_detector.c'),str(adaptive/'adaptive_scheduler.c'),str(radio/'agri_lora.c'),'-lm','-o',str(exe)],check=True)
    return exe
@pytest.mark.parametrize('case',CASES)
def test_real_algorithm_snapshot(snapshot_exe,case):
    result=subprocess.run([str(snapshot_exe),case],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    record=json.loads(result.stdout.splitlines()[-1])
    if case.startswith('continuity-'):assert record['observations']==400 and record['snapshot_bytes']<=6000
    else:assert record['status']=='PASS'
