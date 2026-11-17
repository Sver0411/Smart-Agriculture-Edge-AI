"""Deployment profile authentication validation for peer and field links."""


class DeploymentUnavailable(ValueError):
    pass


def valid_key(key):
    return isinstance(key, bytes) and len(key) >= 32


def require_lab_profile(profile, *, peer_mode=None, peer_key=None, field_key=None):
    if profile not in ("lab", "simulation", "deployment"):
        raise ValueError("unknown execution profile")
    if profile != "deployment":
        return
    if peer_mode != "hmac" or not valid_key(peer_key):
        raise DeploymentUnavailable(
            "deployment requires explicit HMAC peer security and an out-of-band >=32-byte key"
        )
    if not valid_key(field_key):
        raise DeploymentUnavailable(
            "deployment requires an out-of-band >=32-byte field_key for authenticated B/A/C and E220 links"
        )
