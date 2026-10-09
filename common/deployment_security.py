"""Fail-closed entry points until all field and cloud links authenticate.

Timing profiles remain useful for host experiments. They do not authorize a
physical deployment or turn TCP identity declarations / LoRa CRC into trust.
"""

class DeploymentUnavailable(ValueError):
    pass


def require_lab_profile(profile, *, peer_mode=None, peer_key=None):
    if profile not in ('lab', 'simulation', 'deployment'):
        raise ValueError('unknown execution profile')
    if profile != 'deployment':return
    if peer_mode != 'hmac' or not isinstance(peer_key, bytes) or len(peer_key) < 32:
        raise DeploymentUnavailable('deployment requires explicit HMAC peer security and an out-of-band >=32-byte key')
    raise DeploymentUnavailable('deployment not ready: B/A, A/C, A/Server and E220 endpoints lack authenticated sessions; use lab/simulation for isolated experiments')
