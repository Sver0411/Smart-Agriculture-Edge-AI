import asyncio
import json
import subprocess
import sys
from pathlib import Path
from experiments.metrics import Metrics
from experiments.runner import run_scenario
from simulation.network_faults import FrameFaults
from common.messages import Message,CONTROL_COMMAND


def test_unmeasured_is_not_observed_zero():
    m=Metrics();assert m.as_dict()['recovery_time']=={'status':'not measured','value':None}
    m.set('retries',0);assert m.as_dict()['retries']=={'status':'observed','value':0}


def test_normal_experiment_has_machine_verdict_and_evidence(tmp_path):
    summary=asyncio.run(run_scenario('normal',tmp_path/'run',seed=42,duration=0.2))
    assert summary['status']=='PASS'
    assert all(a['passed'] for a in summary['assertions'])
    manifest=json.loads((tmp_path/'run/manifest.json').read_text())
    assert manifest['input_mode']=='software-simulation'
    assert manifest['raw_sha256']
    events=(tmp_path/'run/raw/events.jsonl').read_text().splitlines()
    assert any(json.loads(e)['event']=='delivered' for e in events)


def test_fault_rule_replay_is_seeded_and_terminal_drop():
    class Writer:
        def write(self,_):raise AssertionError('drop must not write')
        async def drain(self):pass
    async def run():
        faults=FrameFaults([{'action':'drop','count':5,'probability':0.5,'match':{'type':CONTROL_COMMAND}}],seed=3)
        m=Message(type=CONTROL_COMMAND,source='A1',target='C1')
        return [await faults(Writer(),m) for _ in range(10)]
    assert asyncio.run(run())==asyncio.run(run())


def test_runner_failure_is_nonzero_and_preserves_failure(tmp_path):
    # Invalid output re-use is refused, so evidence is never silently overwritten.
    run=tmp_path/'run';run.mkdir()
    proc=subprocess.run([sys.executable,'-m','experiments.runner','--scenario','normal','--output',str(run)],capture_output=True,text=True,timeout=15)
    # A fresh child run is created beneath output; second invocation must fail.
    proc=subprocess.run([sys.executable,'-m','experiments.runner','--scenario','normal','--output',str(run)],capture_output=True,text=True,timeout=15)
    assert proc.returncode!=0


def test_gateway_recovery_metrics_include_pre_crash_incarnation(tmp_path):
    out=tmp_path/'recovery'
    summary=asyncio.run(run_scenario('gateway-recovery',out,seed=42,duration=0.2))
    assert summary['status']=='PASS'
    events=[json.loads(line) for line in (out/'raw/events.jsonl').read_text().splitlines()]
    commands={e['message']['message_id'] for e in events if e['event']=='sent'
              and e['message']['type']=='CONTROL_COMMAND' and e['message']['target'] in ('C1','C2')}
    metrics=json.loads((out/'results/metrics.json').read_text())
    assert metrics['control_commands']['value']>=len(commands)

import pytest

@pytest.mark.parametrize('scenario',['registration-race','persisted-ack-loss','controller-unavailable'])
def test_reliability_hardening_scenarios_have_nonvacuous_verdicts(scenario,tmp_path):
    out=tmp_path/scenario
    summary=asyncio.run(run_scenario(scenario,out,seed=42,duration=0.2))
    assert summary['status']=='PASS',json.dumps(summary,indent=2)
    assert len(summary['assertions'])>=8
    assert json.loads((out/'config.json').read_text())['runtime_overrides']['gateway']['server_receipt_timeout']==0.25


def test_external_adapter_has_no_ownership_startup_delay(tmp_path):
    from experiments.edgefaultlab import adapt
    spec=adapt({'processes':[],'links':[],'faults':[],'assertions':[]},Path(__file__).resolve().parents[1],tmp_path)
    assert all('--startup-delay' not in p['command'] for p in spec['processes'])
