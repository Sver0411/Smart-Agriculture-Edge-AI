from pathlib import Path
import asyncio
import pytest
from experiments.phase123_integration import CASES,basic_case,build,ownership_probe
from experiments.runner import run_scenario
@pytest.fixture(scope='module')
def bridge(tmp_path_factory):
    exe=tmp_path_factory.mktemp('bridge')/'b1';build(exe);return exe
@pytest.mark.parametrize('case',[x for x in CASES if x not in ('failover-freshness','recovery-fencing','server-replay','asymmetric-partition')])
def test_c_snapshot_high_radio_pipeline(tmp_path,bridge,case):
    result=asyncio.run(basic_case(case,tmp_path/case,42,bridge))
    assert result['status']=='PASS' and result['assertions']

def test_actual_asymmetric_heartbeat_loss(tmp_path):
    result=asyncio.run(run_scenario('normal',tmp_path/'asymmetric',42,duration=3,transport='simulated-lora',extra_fault_rules=[{'action':'drop','count':10000,'match':{'type':'HEARTBEAT','source':'A1','target':'A2'}}]))
    assert result['status']=='PASS'
    states=result['observations']['gateway_states']
    assert states['A1']['role']=='STANDBY' and states['A2']['generation']>=2

def test_restored_history_vs_fresh_control_after_takeover(tmp_path,bridge):
    assertions=asyncio.run(ownership_probe(tmp_path/'history',bridge))
    assert len(assertions)==3 and all(a['passed'] for a in assertions)
