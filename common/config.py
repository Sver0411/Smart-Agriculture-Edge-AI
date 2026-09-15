"""Static configuration of the v0.1 system.

Everything is a plain module level constant on purpose: v0.1 keeps the
configuration surface as small as possible.
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

# Which sensor / controller node belongs to which gateway.
SENSOR_OF = {"A1": "B1", "A2": "B2"}
CONTROLLER_OF = {"A1": "C1", "A2": "C2"}

# Sensor node -> gateway, used as the default when a node is started alone.
GATEWAY_OF_SENSOR = {"B1": "A1", "B2": "A2"}
GATEWAY_OF_CONTROLLER = {"C1": "A1", "C2": "A2"}

DEFAULT_DB_PATH = "smart_agriculture.db"

# --------------------------------------------------------------------------
# Timing (seconds)
# --------------------------------------------------------------------------

HEARTBEAT_INTERVAL = 3.0
HEARTBEAT_TIMEOUT = 10.0

SAMPLE_INTERVAL_SLOW = 5.0
SAMPLE_INTERVAL_FAST = 2.0

SERVER_POLICY_INTERVAL = 10.0
SERVER_POLICY_FIRST_DELAY = 1.0

# A control command older than this is refused by the Safety Guard.
COMMAND_TTL = 10.0

# Control commands are simulated, not really executed: the controller waits
# ``duration * SIMULATION_TIME_SCALE`` seconds instead of the real duration.
SIMULATION_TIME_SCALE = 0.2

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

# What the cloud server pushes down to the gateways every
# SERVER_POLICY_INTERVAL seconds.
SERVER_POLICY = dict(DEFAULT_POLICY)

# --------------------------------------------------------------------------
# Safety Guard limits
# --------------------------------------------------------------------------

MAX_DURATION = {"IRRIGATION": 30, "VENTILATION": 30}

# Minimum time between two commands of the same type.
COOLDOWN = {"IRRIGATION": 60.0, "VENTILATION": 30.0}
