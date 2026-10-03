from experiments.edgefaultlab import adapt
from common.settings import load_settings


def test_external_adapter_configures_all_seven_roles_and_dynamic_ports(tmp_path):
    template={'name':'test','links':[{'name':'gateways_to_server','listen':'127.0.0.1:9100','upstream':'127.0.0.1:9400'},
             {'name':'nodes_to_gateway_a1','listen':'127.0.0.1:9201','upstream':'127.0.0.1:9301'}],
             'processes':[{'name':'gateway_a2','command':['python3','-m','gateway.gateway','--id','A2','--port','9202','--peer-port','9201']},
                          {'name':'sensor_b1','command':['python3','-m','sensor_node.sensor_node','--id','B1','--gateway','A1']}],
             'faults':[{'at':10,'action':'process_kill','process':'gateway_a1'}],
             'assertions':[{'assert':'eventually','after':10,'within':25,'match':{'type':'SENSOR_DATA'}}]}
    result=adapt(template,tmp_path,tmp_path/'out')
    cfg=load_settings(tmp_path/'out/config.json')
    assert cfg['system']['GATEWAY_PORTS']['A1']!=cfg['system']['GATEWAY_PORTS']['A2']
    assert result['faults'][0]['at']==2
    assert any(p['name']=='sensor_b2' for p in result['processes'])
    assert any(p['name']=='controller_c2' for p in result['processes'])
    assert any(a.get('match',{}).get('source')=='B1' for a in result['assertions'])
    sensor=next(p for p in result['processes'] if p['name']=='sensor_b1')
    assert '--startup-delay' in sensor['command'] and sensor['env']['SMART_AGRICULTURE_CONFIG']
