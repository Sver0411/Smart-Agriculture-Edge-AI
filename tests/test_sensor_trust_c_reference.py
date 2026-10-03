"""Host-only reference equivalence on shared five-fault fixtures; no FFI."""
import pathlib
import shutil
import subprocess
import pytest
from common.settings import node_settings
from sensor_node.sensor_trust import ChannelTrust


def test_python_reference_matches_frozen_c_core_on_fault_and_recovery_trace(tmp_path):
    cc=shutil.which('cc')
    if not cc:pytest.skip('host C compiler unavailable')
    root=pathlib.Path(__file__).resolve().parents[1]
    core=root/'firmware/b1/components/sensor_trust'
    source=tmp_path/'parity.c'
    source.write_text('''
#include <stdio.h>
#include "sensor_trust.h"
int main(void) {
 sensor_trust_config_t c; sensor_trust_default_config(&c);
 c.min_value=-10;c.max_value=60;c.stuck_window=3;c.stuck_epsilon=0.01f;
 c.drift_window=3;c.drift_threshold=0.1f;c.spike_threshold=5;c.missing_limit=3;
 sensor_trust_t ctx;sensor_trust_init(&ctx,&c);
 float value;unsigned long long ts;int valid;
 while(scanf("%f %llu %d", &value,&ts,&valid)==3) {
  sensor_sample_t sample={.value=value,.timestamp_ms=ts,.valid=valid!=0};
  sensor_health_result_t r=sensor_trust_update(&ctx,&sample);
  printf("%d %u\\n",r.health_score,r.fault_flags);
 }
 return 0;
}
''')
    binary=tmp_path/'parity'
    subprocess.run([cc,'-std=c11','-Wall','-Werror','-I',str(core),str(source),str(core/'sensor_trust.c'),'-lm','-o',str(binary)],check=True)
    trace=[(25,True),(25,True),(25,True),(35,True),(25,True),(100,True),
           (0,False),(0,False),(0,False),(20,True),(21,True),(22,True),(23,True),(24,True),(24,True)]
    raw=''.join(f'{value} {i*1000} {int(valid)}\n' for i,(value,valid) in enumerate(trace))
    rows=subprocess.check_output([str(binary)],input=raw,text=True).splitlines()
    cfg={**node_settings()['trust_channels']['temperature'],'stuck_window':3,'drift_window':3,'drift_threshold':0.1}
    ref=ChannelTrust(cfg);order=['RANGE','STUCK','SPIKE','DRIFT','MISSING']
    for i,((value,valid),line) in enumerate(zip(trace,rows)):
        score,mask=map(int,line.split());r=ref.update(value,i,valid)
        assert r['health_score']==score
        assert sum(1<<order.index(f) for f in r['fault_flags'])==mask
