from sensor_node.adaptive_sense import AdaptiveSense

TRUST={'state':'HEALTHY','usable_for_control':True}

def test_intent_does_not_advance_python_baseline():
    b=AdaptiveSense();b.update({'temperature':25,'humidity':60},TRUST,10)
    assert b.core._last_upload_t is None

def test_late_ack_uses_acquisition_time_and_never_rolls_back():
    b=AdaptiveSense();b.update({'temperature':25,'humidity':60},TRUST,100)
    assert b.mark_reported({'temperature':36,'humidity':60},TRUST,timestamp=20,sequence=2)
    assert not b.mark_reported({'temperature':25,'humidity':60},TRUST,timestamp=10,sequence=1)
    assert b.core._last_upload_t==20 and b.relevance.reported['temperature']==36
    assert not b.mark_reported({'temperature':25},TRUST,timestamp=20,sequence=2)
