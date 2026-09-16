"""Static configuration of Smart Agriculture Edge AI.

Everything is a plain module level constant on purpose: the configuration
surface is kept as small as possible.
"""

# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9100

# Each gateway listens on its own TCP port. Sensors, controllers and the peer
# gateway all connect to that single port; the message ``source`` field tells
# the gateway who is talking.
GATEWAY_PORTS = {"A1": 9201, "A2": 9202}

PEER_OF = {"A1": "A2", "A2": "A1"}

# Which sensor / controller node belongs to which gateway by default.
SENSOR_OF = {"A1": "B1", "A2": "B2"}
CONTROLLER_OF = {"A1": "C1", "A2": "C2"}

# Sensor node -> gateway, used as the default when a node is started alone.
GATEWAY_OF_SENSOR = {"B1": "A1", "B2": "A2"}
GATEWAY_OF_CONTROLLER = {"C1": "A1", "C2": "A2"}

# Sensor and controller of the same zone belong together: the soil probe B1
# drives the pump C1.  A gateway that takes over a foreign sensor therefore
# commands *that zone's* controller, not its own.
CONTROLLER_OF_SENSOR = {"B1": "C1", "B2": "C2"}
SENSOR_OF_CONTROLLER = {"C1": "B1", "C2": "B2"}

# A node tries its primary gateway first, then these fallback gateways in order.
FALLBACK_GATEWAYS = {"A1": ["A2"], "A2": ["A1"]}

DEFAULT_DB_PATH = "smart_agriculture.db"
GATEWAY_QUEUE_DB_TEMPLATE = "gateway_queue_{gateway_id}.db"

# --------------------------------------------------------------------------
# Timing (seconds)
# --------------------------------------------------------------------------

HEARTBEAT_INTERVAL = 3.0
HEARTBEAT_TIMEOUT = 10.0

SAMPLE_INTERVAL_SLOW = 5.0
SAMPLE_INTERVAL_FAST = 2.0

# A registered node is moved to OFFLINE when it stayed silent this long.
NODE_TIMEOUT = 15.0

# How often a controller tells its gateway "I am still here" (NODE_STATUS).
NODE_STATUS_INTERVAL = 5.0

SERVER_POLICY_INTERVAL = 10.0
SERVER_POLICY_FIRST_DELAY = 1.0

# A control command older than this is refused by the Safety Guard.
COMMAND_TTL = 10.0

# Control commands are simulated, not really executed: the controller waits
# ``duration * SIMULATION_TIME_SCALE`` seconds instead of the real duration.
SIMULATION_TIME_SCALE = 0.2

# --------------------------------------------------------------------------
# Reliability (v0.2)
# --------------------------------------------------------------------------

# Critical messages are acknowledged; without an ACK they are retried after
# ACK_TIMEOUT, at most MAX_RETRIES times.
ACK_TIMEOUT = 2.0
MAX_RETRIES = 3
RETRY_SCAN_INTERVAL = 0.2

ACKED_MESSAGE_TYPES = ("CONTROL_COMMAND", "NODE_REGISTER")

# --------------------------------------------------------------------------
# Gateway / node states
# --------------------------------------------------------------------------

# health of a node or a gateway
ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
UNKNOWN = "UNKNOWN"

# role of a gateway
ACTIVE = "ACTIVE"
STANDBY = "STANDBY"

# node types kept in the registry
SENSOR = "SENSOR"
CONTROLLER = "CONTROLLER"

# Ownership generation of a freshly started gateway.
INITIAL_GENERATION = 1

# --------------------------------------------------------------------------
# SensorTrust acceptance ranges
# --------------------------------------------------------------------------

SENSOR_RANGES = {
    "temperature": (-10.0, 60.0),
    "humidity": (0.0, 100.0),
    "soil_moisture": (0.0, 100.0),
    "light": (0.0, 120000.0),
}

# --------------------------------------------------------------------------
# Edge decision / server policy
# --------------------------------------------------------------------------

DEFAULT_POLICY = {
    "soil_moisture_threshold": 25.0,
    "temperature_threshold": 32.0,
    "irrigation_duration": 10,
    "ventilation_duration": 5,
}

# Version of the very first policy the cloud server ships.  A gateway ignores a
# policy whose ``policy_version`` is not newer than the one it already holds.
INITIAL_POLICY_VERSION = 1

# --------------------------------------------------------------------------
# Safety Guard limits
# --------------------------------------------------------------------------

MAX_DURATION = {"IRRIGATION": 30, "VENTILATION": 30}

# Minimum time between two commands of the same type.
COOLDOWN = {"IRRIGATION": 60.0, "VENTILATION": 30.0}


def gateway_queue_path(gateway_id: str) -> str:
    """Path of the store-and-forward SQLite file used by one gateway."""
    return GATEWAY_QUEUE_DB_TEMPLATE.format(gateway_id=gateway_id)
