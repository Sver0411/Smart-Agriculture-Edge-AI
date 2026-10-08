"""Real C algorithm/RTC-format oracle; no board current or RTC hardware claim."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
CASES=[f'continuity-{m}' for m in ('healthy','event','range','missing','stuck','drift','spike')]+['unknown-time','sequence','epoch','truncated','bit-corruption','version','profile','state-capacity','clock-overflow','lease']
def build(exe):
    main=ROOT/'firmware/b1/main';trust=ROOT/'firmware/b1/components/sensor_trust';adaptive=ROOT/'firmware/b1/components/adaptive_sense';radio=ROOT/'firmware/b1/components/agri_lora'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DB1_HOST_TEST','-DCONFIG_B1_LAB_MODE=1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(main),'-I',str(trust),'-I',str(adaptive),'-I',str(radio),str(ROOT/'tests/c_host/b1_snapshot.c'),str(main/'b1_snapshot.c'),str(main/'b1_policy.c'),str(trust/'sensor_trust.c'),str(adaptive/'change_detector.c'),str(adaptive/'adaptive_scheduler.c'),str(radio/'agri_lora.c'),'-lm','-o',str(exe)],check=True)
def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'config.json').write_text(json.dumps({'seed':42,'driver':'actual C SensorTrust/AdaptiveSense/B1 policy','cases':CASES,'sample_interval_ms':1000,'snapshot_schema':1,'units':{'time':'logical algorithm ms','bytes':'serialized snapshot bytes'},'hardware_RTC':False,'measured_power':False},indent=2)+'\n')
    summaries=[]
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'snapshot';build(exe)
        for case in CASES:
            result=subprocess.run([str(exe),case],env={**os.environ,'B1_SNAPSHOT_TRACE':'1'},capture_output=True,text=True)
            (output/(case+'.jsonl')).write_text(result.stdout)
            (output/(case+'.stderr.log')).write_text(result.stderr)
            record=json.loads(result.stdout.splitlines()[-1]) if result.returncode==0 else {}
            summaries.append({'case':case,'status':'PASS' if result.returncode==0 else 'FAIL','returncode':result.returncode,**record})
    (output/'summary.json').write_text(json.dumps({'total':len(summaries),'passed':sum(s['status']=='PASS' for s in summaries),'runs':summaries,'python':platform.python_version(),'C':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]},indent=2)+'\n')
    return 0 if all(s['status']=='PASS' for s in summaries) else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();raise SystemExit(run(a.output))
