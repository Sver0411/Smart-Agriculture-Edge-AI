import pytest
from common.deployment_security import DeploymentUnavailable
from gateway.gateway import Gateway
from server.server import Server
from controller_node.controller_node import ControllerNode
from gateway.peer_security import valid_nonce

@pytest.mark.parametrize('factory',[lambda:Gateway('A1',profile='deployment'),
 lambda:Gateway('A1',profile='deployment',peer_security_mode='hmac',peer_key=b'x'*32),
 lambda:Server(profile='deployment'),lambda:ControllerNode('C1',profile='deployment')])
def test_deployment_fails_before_opening_resources(factory):
    with pytest.raises(DeploymentUnavailable):factory()

@pytest.mark.parametrize('nonce',['x'*32,'A'*32,'0'*31,[],None,'é'*32])
def test_invalid_nonce_rejected(nonce):
    assert not valid_nonce(nonce)
    assert valid_nonce('a'*32)

def test_authenticated_deployment_unlocks_with_peer_and_field_keys(tmp_path):
    peer_key = b'p' * 32
    field_key = b'f' * 32
    g = Gateway('A1', profile='deployment', peer_security_mode='hmac', peer_key=peer_key, field_key=field_key, queue_path=str(tmp_path / 'gw.db'))
    s = Server(profile='deployment', peer_security_mode='hmac', peer_key=peer_key, field_key=field_key, db_path=str(tmp_path / 'srv.db'))
    c = ControllerNode('C1', profile='deployment', peer_security_mode='hmac', peer_key=peer_key, field_key=field_key, state_path=str(tmp_path / 'ctrl.db'))
    assert g.field_key == field_key and s.field_key == field_key and c.field_key == field_key
    g.offline_queue.close()
    s.db.close()

