"""Compile the real B1 policy, queue admission and telemetry sink on the host.

The cJSON/FreeRTOS sink stubs test dispatch, not RF or serialization. Compare
state/next interval/event/upload at every sample, using identical float32 inputs.
"""
import math
from pathlib import Path
import shutil
import struct
import subprocess
import pytest
from common.settings import node_settings
from sensor_node.adaptive_sense import AdaptiveSense
from sensor_node.sensor_trust import SensorTrust
from scripts.generate_b1_profiles import generate, TARGET

ROOT = Path(__file__).resolve().parents[1]

def f32(v):return struct.unpack('f',struct.pack('f',v))[0]

@pytest.fixture(scope='module', params=['simulation','lab','deployment'])
def c_policy(request, tmp_path_factory):
    cc=shutil.which('cc')
    if not cc:pytest.fail('C compiler required for upload parity acceptance')
    base=ROOT/'firmware/b1';main=base/'main';trust=base/'components/sensor_trust';adaptive=base/'components/adaptive_sense'
    binary=tmp_path_factory.mktemp('upload-parity')/request.param
    subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-DB1_HOST_TEST',f'-DCONFIG_B1_{request.param.upper()}_MODE=1',
        '-I',str(ROOT/'third_party/cjson'),'-I',str(ROOT/'tests/c_host/stubs'),'-I',str(main),'-I',str(trust),'-I',str(adaptive),
        str(ROOT/'tests/c_host/b1_policy_trace.c'),str(main/'b1_policy.c'),str(main/'b1_queue.c'),str(main/'b1_telemetry.c'),str(main/'b1_outbox.c'),str(ROOT/'third_party/cjson/cJSON.c'),
        str(trust/'sensor_trust.c'),str(adaptive/'adaptive_scheduler.c'),str(adaptive/'change_detector.c'),'-lm','-o',str(binary)],check=True)
    return request.param,binary

CASES=['stable','slow_drift','sudden_change','event_onset','event_recovery','sensor_fault','periodic_heartbeat','large_delta']

def trace(case, settings):
    dt=settings['sampling']['min_interval']
    heartbeat=settings['adaptive']['upload']['heartbeat_s']
    points=[]
    for i in range(100):
        temp=25+(i%2)*.04;hum=60+(i%2)*.2;valid=True
        if case=='slow_drift':temp+=i*.025
        if case in ('sudden_change','event_onset','event_recovery') and 5<=i<30:temp+=2
        if case=='sensor_fault' and 5<=i<15:temp=150
        if case=='sensor_fault' and 20<=i<30:valid=False
        if case=='large_delta' and i>=5:hum+=5
        t=i*dt
        if case=='periodic_heartbeat':t=i*heartbeat/8
        points.append((t, f32(temp),f32(hum),valid))
    return points

@pytest.mark.parametrize('case',CASES)
def test_python_c_upload_decision_parity(c_policy, case):
    profile,binary=c_policy
    settings=node_settings(profile,physical=True)
    samples=trace(case,settings)
    raw=''.join(f'{round(t*1000)} {temp:.9g} {hum:.9g} {int(valid)}\n' for t,temp,hum,valid in samples)
    lines=subprocess.check_output([str(binary)],input=raw,text=True).splitlines()
    trust=SensorTrust(settings['trust_channels']);scheduler=AdaptiveSense(settings=settings)
    uploads=[];events=[];states=[];sent=0
    assert len(lines)==len(samples)
    for (t,temp,hum,valid),line in zip(samples,lines):
        sample={'temperature':temp,'humidity':hum}
        health=trust.update(sample,t,valid={'temperature':valid,'humidity':valid})
        decision=scheduler.update(sample,health,t)
        state,ms,event,upload,admitted,enqueued,network,health_state,score,reason_mask=line.split()
        assert state==decision['state'],(profile,case,t,line,decision)
        assert int(ms)==pytest.approx(decision['interval_s']*1000,abs=1)
        assert bool(int(event))==decision['detected_event'],(profile,case,t,line,decision)
        assert bool(int(upload))==decision['upload_requested'],(profile,case,t,line,decision)
        names=['FIRST_SAMPLE','EVENT_ONSET','EVENT_RECOVERY','STATE_CHANGE','INTERVAL_CHANGE',
               'PERIODIC_HEARTBEAT','MEANINGFUL_DELTA','HEALTH_CHANGE','SENSOR_FAULT','SENSOR_RECOVERY',
               'CONTROL_THRESHOLD_CROSSING','CONTROL_MARGIN_ENTRY']
        assert {name for i,name in enumerate(names) if int(reason_mask)&(1<<i)}==set(decision['upload_reasons'])
        if decision['upload_requested']:scheduler.mark_reported(sample,health)
        assert bool(int(admitted))==decision['upload_requested']
        sent+=decision['upload_requested']
        assert int(enqueued)==int(network)==sent
        if decision['score'] is None:assert math.isnan(float(score))
        else:assert float(score)==pytest.approx(decision['score'],abs=0.002)
        uploads.append(decision['upload_requested']);events.append(decision['detected_event']);states.append(state)
    assert uploads[0]
    if case=='stable':assert sent<len(samples)/2
    if case=='sensor_fault':assert uploads[5] and not uploads[7] and uploads[20] and not uploads[21] and uploads[30]
    if case in ('sudden_change','event_onset','event_recovery'):
        assert uploads[5] and states[5]=='ALERT'
        assert any(events)
        onset=events.index(True);assert uploads[onset]
        recovery=next(i for i in range(onset+1,len(events)) if not events[i]);assert uploads[recovery]


def test_generated_profile_header_is_current():
    assert TARGET.read_text()==generate()

def test_healthy_temperature_crossing_is_not_hidden_by_unrelated_humidity_fault(c_policy):
    profile,binary=c_policy;cfg=node_settings(profile,physical=True);dt=cfg['sampling']['min_interval']
    samples=[(i*dt,f32(temp),f32(150)) for i,temp in enumerate((31.9,32.1,32.2))]
    raw=''.join(f'{round(t*1000)} {temp:.9g} {hum:.9g} 1\n' for t,temp,hum in samples)
    rows=subprocess.check_output([str(binary)],input=raw,text=True).splitlines()
    trust=SensorTrust(cfg['trust_channels']);b=AdaptiveSense(settings=cfg)
    for i,((t,temp,hum),line) in enumerate(zip(samples,rows)):
        sample={'temperature':temp,'humidity':hum};health=trust.update(sample,t);d=b.update(sample,health,t)
        mask=int(line.split()[-1])
        assert bool(int(line.split()[3]))==d['upload_requested']
        assert bool(mask&(1<<10))==('CONTROL_THRESHOLD_CROSSING' in d['upload_reasons'])
        if i==1:assert d['upload_reasons']==['CONTROL_THRESHOLD_CROSSING']
        if d['upload_requested']:b.mark_reported(sample,health)

def test_physical_temperature_crossing_parity_and_failed_admission(c_policy):
    profile,binary=c_policy;cfg=node_settings(profile,physical=True)
    dt=cfg['sampling']['min_interval']
    samples=[(i*dt,f32(t),f32(60+i*.03),True) for i,t in enumerate((31.9,32.1,32.15,31.9,32.0,32.1))]
    raw=''.join(f'{round(t*1000)} {temp:.9g} {hum:.9g} 1\n' for t,temp,hum,_ in samples)
    rows=subprocess.check_output([str(binary),'--reject-second'],input=raw,text=True).splitlines()
    trust=SensorTrust(cfg['trust_channels']);scheduler=AdaptiveSense(settings=cfg)
    for i,((t,temp,hum,_),line) in enumerate(zip(samples,rows)):
        sample={'temperature':temp,'humidity':hum};health=trust.update(sample,t)
        decision=scheduler.update(sample,health,t)
        state,ms,event,upload,admitted,enqueued,network,health_state,score,mask=line.split()
        assert state==decision['state'] and int(ms)==pytest.approx(decision['interval_s']*1000,abs=1)
        assert bool(int(event))==decision['detected_event'] and bool(int(upload))==decision['upload_requested']
        crossing='CONTROL_THRESHOLD_CROSSING' in decision['upload_reasons']
        assert bool(int(mask)&(1<<10))==crossing
        if i in (1,2,3,5):assert crossing and decision['upload_requested']
        if i==1:assert not int(admitted)  # queue rejection cannot advance control baseline
        if int(admitted):scheduler.mark_reported(sample,health)

@pytest.fixture(scope='module')
def c_core(tmp_path_factory):
    adaptive=ROOT/'firmware/b1/components/adaptive_sense';binary=tmp_path_factory.mktemp('core-parity')/'trace'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(adaptive),
        str(ROOT/'tests/c_host/adaptive_trace.c'),str(adaptive/'change_detector.c'),str(adaptive/'adaptive_scheduler.c'),
        '-lm','-o',str(binary)],check=True)
    return binary


def core_config(cfg):
    a=cfg['adaptive'];rows=[]
    for c in a['channels'].values():rows.append(f'{int(c["use"])} {c["noise_floor"]}')
    rows.append(' '.join(str(v) for v in [*a['analyzer'].values(),cfg['sampling']['min_interval'],a['event_threshold'],a['event_min_duration_s']]))
    rows.append(' '.join(str(v) for v in [*cfg['sampling'].values(),a['stable_threshold'],a['active_threshold'],a['hysteresis_fraction']]))
    for name,ladder in a['ladders'].items():rows.append(f'{len(ladder)} {a["ladder_confirmations"][name]} '+' '.join(map(str,ladder)))
    up=a['upload'];rows.append(' '.join(str(int(up[k])) for k in ('upload_first_sample','on_event','on_state_change','on_interval_change'))+f' {up["heartbeat_s"]} {up["delta_threshold"]}')
    return '\n'.join(rows)+'\n'

@pytest.mark.parametrize('profile',['simulation','lab','deployment'])
@pytest.mark.parametrize('case',CASES)
def test_four_channel_core_upload_parity(c_core,profile,case):
    from sensor_node.adaptive_scheduler import AdaptiveScheduler
    cfg=node_settings(profile);scheduler=AdaptiveScheduler(cfg)
    samples=[]
    for i,(t,temp,hum,valid) in enumerate(trace(case,cfg)):
        values=[temp,hum,f32(40+(i%2)*.1),f32(800+(i%2)*2)]
        mask=15 if valid else 0
        if case=='large_delta' and i>=5:values[2]=45  # soil channel index 2
        samples.append((t,values,mask))
    raw=core_config(cfg)+''.join(f'{t} '+ ' '.join(f'{v:.9g}' for v in values)+f' {mask}\n' for t,values,mask in samples)
    rows=subprocess.check_output([str(c_core)],input=raw,text=True).splitlines()
    assert len(rows)==len(samples)
    for (t,values,mask),line in zip(samples,rows):
        d=scheduler.update(t,{name:value for i,(name,value) in enumerate(zip(cfg['adaptive']['channels'],values)) if mask&(1<<i)})
        state,interval,event,upload=line.split()
        assert ('STABLE','ACTIVE','ALERT')[int(state)]==d.state
        assert float(interval)==pytest.approx(d.interval_s)
        assert bool(int(event))==d.detected_event
        assert bool(int(upload))==d.upload_requested


def test_core_missing_channel_cannot_create_delta_against_unuploaded_zero(c_core):
    from sensor_node.adaptive_scheduler import AdaptiveScheduler
    cfg=node_settings('simulation');cfg['adaptive'].update(stable_threshold=100,active_threshold=200)
    cfg['adaptive']['upload'].update(on_interval_change=False,on_state_change=False,on_event=False,heartbeat_s=0)
    raw=core_config(cfg)+'0 25 60 40 800 1\n5 25 60 40 800 3\n'
    rows=subprocess.check_output([str(c_core)],input=raw,text=True).splitlines()
    assert [bool(int(line.split()[-1])) for line in rows]==[True,False]
    core=AdaptiveScheduler(cfg)
    assert core.update(0,{'temperature':25}).upload_requested
    assert not core.update(5,{'temperature':25,'humidity':60}).upload_requested
