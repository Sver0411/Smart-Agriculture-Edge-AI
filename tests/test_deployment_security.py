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
