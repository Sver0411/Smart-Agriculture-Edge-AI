from sensor_node.fault_notifier import FaultNotifier

def trust(state='HEALTHY',channel='light',flags=(),valid=True):
    return {'state':state,'usable_for_control':state=='HEALTHY' and valid,
            'channels':{channel:{'state':state,'valid':valid,'fault_flags':list(flags)}}}

def test_transition_fault_signature_reminder_and_recovery():
    n=FaultNotifier(reminder_s=60)
    assert n.update(trust(),0) is None
    assert n.update(trust('DEGRADED',flags=['SPIKE']),1)['notification']=='transition'
    for t in range(2,61):assert n.update(trust('DEGRADED',flags=['SPIKE']),t) is None
    assert n.update(trust('DEGRADED',flags=['SPIKE']),61)['notification']=='reminder'
    assert n.update(trust('FAULT',flags=['RANGE']),62)['alert_type']=='SENSOR_FAULT'
    assert n.update(trust('FAULT',channel='soil_moisture',flags=['RANGE']),63)['notification']=='transition'
    assert n.update(trust(),64)['alert_type']=='SENSOR_RECOVERED'
    assert n.update(trust(),65) is None

def test_initial_missing_before_fault_confirmation_notifies_once():
    n=FaultNotifier()
    assert n.update(trust(valid=False),0)['alert_type']=='SENSOR_DEGRADED'
    assert n.update(trust(valid=False),1) is None
    assert n.update(trust(),2)['notification']=='recovery'
