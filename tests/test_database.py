"""SQLite persistence of the cloud server."""

from server.database import Database


def open_db() -> Database:
    return Database(":memory:").init_schema()


def test_sensor_data_is_stored():
    db = open_db()
    try:
        db.insert_sensor_data(
            gateway_id="A1",
            sensor_node_id="B1",
            record={
                "timestamp": 1_000.0,
                "temperature": 24.5,
                "humidity": 61.0,
                "soil_moisture": 22.3,
                "light": 850.0,
            },
            health_state="HEALTHY",
        )

        assert db.count("sensor_data") == 1
        row = db.recent_sensor_data(1)[0]
        assert row["gateway_id"] == "A1"
        assert row["sensor_node_id"] == "B1"
        assert row["soil_moisture"] == 22.3
        assert row["health_state"] == "HEALTHY"
    finally:
        db.close()


def test_controller_command_and_result_are_stored():
    db = open_db()
    try:
        db.insert_controller_command("A1", "C1", "cmd-1", "IRRIGATION", 10, 1_000.0)
        db.insert_controller_result(
            "A1", "cmd-1", "REJECTED", 1_002.0, controller_id="C1", command_type="IRRIGATION", reason="COOLDOWN"
        )

        assert db.count("controller_command") == 1
        assert db.count("controller_result") == 1
        result = db.recent_controller_results(1)[0]
        assert result["status"] == "REJECTED"
        assert result["reason"] == "COOLDOWN"
    finally:
        db.close()


def test_alert_and_heartbeat_are_stored():
    db = open_db()
    try:
        db.insert_gateway_heartbeat("A1", 1_000.0, peer_id="A2", peer_status="ONLINE")
        db.insert_alert("A1", 1_001.0, "SENSOR_FAULT", "soil_moisture out of range", sensor_node_id="B1")

        assert db.count("gateway_heartbeat") == 1
        assert db.count("alert") == 1
    finally:
        db.close()
