"""Store-and-forward on the gateway, deduplication on the server.

Together these two give the "the farm keeps working when the uplink is gone"
property: a gateway never throws history away, and the server never stores the
same upload twice when the queue is replayed.
"""

import pytest
import asyncio
import socket

from common.messages import SENSOR_DATA, PERSISTED_ACK, Message
from gateway.gateway import Gateway
from server.server import Server
from gateway.offline_queue import OfflineQueue
from server.database import Database
from server.dedup import Deduplicator


def upload(node_id: str = "B1", message_id: str | None = None) -> Message:
    message = Message(
        type=SENSOR_DATA,
        source="A1",
        target="SERVER",
        payload={"record": {"sensor_node_id": node_id, "soil_moisture": 20.0}},
    )
    if message_id:
        message.message_id = message_id
    return message


@pytest.fixture
def queue(tmp_path):
    q = OfflineQueue(str(tmp_path / "queue.db")).connect()
    yield q
    q.close()


# --------------------------------------------------------------------------
# OfflineQueue
# --------------------------------------------------------------------------


def test_an_empty_queue_holds_nothing(queue):
    assert queue.count() == 0
    assert queue.peek() == []


def test_enqueue_keeps_the_original_message_id(queue):
    """The server deduplicates on message_id, so it must survive the queue."""
    message = upload(message_id="abc123")
    queue.enqueue(message)

    stored = queue.peek()[0][1]
    assert stored.message_id == "abc123"
    assert stored.type == SENSOR_DATA
    assert stored.payload["record"]["sensor_node_id"] == "B1"


def test_the_queue_is_a_fifo(queue):
    for name in ("B1", "B2", "B1"):
        queue.enqueue(upload(name))

    assert [m.payload["record"]["sensor_node_id"] for _, m in queue.peek()] == ["B1", "B2", "B1"]
    assert queue.enqueued == 3


def test_replay_deletes_only_the_delivered_message(queue):
    queue.enqueue(upload("B1"))
    queue.enqueue(upload("B2"))

    first = queue.peek(limit=1)[0][0]
    queue.bump_retry(first)
    queue.delete(first)

    assert queue.count() == 1
    assert queue.replayed == 1
    assert queue.peek()[0][1].payload["record"]["sensor_node_id"] == "B2"


def test_peek_respects_its_limit(queue):
    for _ in range(5):
        queue.enqueue(upload())
    assert len(queue.peek(limit=2)) == 2
    assert len(queue.peek(limit=100)) == 5


def test_the_queue_survives_a_reopen(tmp_path):
    """It is a file, not a list: what was queued is still there after a crash."""
    path = str(tmp_path / "queue.db")
    first = OfflineQueue(path)
    first.enqueue(upload("B1", message_id="keep-me"))
    first.close()

    second = OfflineQueue(path).connect()
    try:
        assert second.count() == 1
        assert second.peek()[0][1].message_id == "keep-me"
    finally:
        second.close()


def test_bump_retry_is_counted_per_message(queue):
    queue.enqueue(upload())
    queue_id = queue.peek()[0][0]
    queue.bump_retry(queue_id)
    queue.bump_retry(queue_id)
    # still queued - a failed replay must not lose the message
    assert queue.count() == 1


def test_len_matches_count(queue):
    queue.enqueue(upload())
    assert len(queue) == queue.count() == 1


def test_gateway_drains_all_250_queued_messages_in_order(tmp_path, monkeypatch, capsys):
    gateway = Gateway("A1", queue_path=str(tmp_path / "gateway.db"))
    expected = [f"queued-{i:03}" for i in range(250)]
    for message_id in expected:
        gateway.offline_queue.enqueue(upload(message_id=message_id))
    delivered = []

    async def fake_send(writer, message):
        delivered.append(message.message_id)
        gateway._handle_persisted_ack(Message(type=PERSISTED_ACK, source="SERVER", target="A1",
            payload={"ack_message_id": message.message_id, "persisted": True}), writer)

    monkeypatch.setattr("gateway.gateway.send_message", fake_send)
    gateway.server_writer = object()
    try:
        asyncio.run(gateway._flush_offline_queue())
        assert delivered == expected
        assert gateway.offline_queue.count() == 0
        assert gateway.offline_queue.replayed == 250
        assert gateway.metrics.get("queue_replayed") == 250
        assert "offline queue empty" in capsys.readouterr().out
    finally:
        gateway.offline_queue.close()


def test_gateway_replay_failure_keeps_all_unsent_messages(tmp_path, monkeypatch, capsys):
    path = str(tmp_path / "gateway.db")
    gateway = Gateway("A1", queue_path=path)
    expected = [f"queued-{i:03}" for i in range(250)]
    for message_id in expected:
        gateway.offline_queue.enqueue(upload(message_id=message_id))
    delivered = []

    async def fail_after_130(writer, message):
        if len(delivered) == 130:
            raise BrokenPipeError("simulated server disconnect")
        delivered.append(message.message_id)
        gateway._handle_persisted_ack(Message(type=PERSISTED_ACK, source="SERVER", target="A1",
            payload={"ack_message_id": message.message_id, "persisted": True}), writer)

    monkeypatch.setattr("gateway.gateway.send_message", fail_after_130)
    gateway.server_writer = object()
    try:
        asyncio.run(gateway._flush_offline_queue())
        assert delivered == expected[:130]
        assert gateway.offline_queue.count() == 120
        assert gateway.offline_queue.replayed == 130
        assert [message.message_id for _, message in gateway.offline_queue.peek(limit=250)] == expected[130:]
        assert "offline queue empty" not in capsys.readouterr().out

        async def send_rest(writer, message):
            delivered.append(message.message_id)
            gateway._handle_persisted_ack(Message(type=PERSISTED_ACK, source="SERVER", target="A1",
            payload={"ack_message_id": message.message_id, "persisted": True}), writer)

        monkeypatch.setattr("gateway.gateway.send_message", send_rest)
        gateway.server_writer = object()
        asyncio.run(gateway._flush_offline_queue())
        assert delivered == expected
        assert gateway.offline_queue.count() == 0
        assert gateway.offline_queue.replayed == 250
        assert "offline queue empty" in capsys.readouterr().out
    finally:
        gateway.offline_queue.close()


def test_server_reconnect_drains_250_without_a_new_upload(tmp_path):
    """The server connection itself must trigger replay; no sensor task runs."""
    def free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    async def scenario():
        port = free_port()
        server = Server(port=port, db_path=str(tmp_path / "server.db"))
        gateway = Gateway("A1", server_port=port,
                          queue_path=str(tmp_path / "gateway.db"))
        expected = [f"reconnect-{i:03}" for i in range(250)]
        for message_id in expected:
            gateway.offline_queue.enqueue(upload(message_id=message_id))
        await server.start()
        task = asyncio.create_task(gateway.task_server_policy())
        try:
            for _ in range(200):
                if server.db.count("sensor_data") == 250 and gateway.offline_queue.count() == 0:
                    break
                await asyncio.sleep(0.025)
            assert gateway.offline_queue.count() == 0
            assert gateway.metrics.get("queue_replayed") == 250
            ids = [row[0] for row in server.db.conn.execute(
                "SELECT message_id FROM sensor_data ORDER BY id")]
            assert ids == expected
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            gateway.offline_queue.close()
            await server.stop()

    asyncio.run(scenario())


def test_an_in_memory_queue_works_without_a_path():
    q = OfflineQueue().connect()
    try:
        q.enqueue(upload())
        assert q.count() == 1
    finally:
        q.close()


# --------------------------------------------------------------------------
# Deduplicator
# --------------------------------------------------------------------------


def test_the_first_copy_of_a_message_is_new():
    db = Database(":memory:").connect()
    try:
        dedup = Deduplicator(db.conn)
        assert dedup.is_new("msg-1")
        assert dedup.processed == 1
        assert dedup.ignored == 0
    finally:
        db.close()


def test_a_replayed_message_is_ignored():
    db = Database(":memory:").connect()
    try:
        dedup = Deduplicator(db.conn)
        assert dedup.is_new("msg-1")
        assert not dedup.is_new("msg-1")
        assert dedup.ignored == 1
    finally:
        db.close()


def test_different_ids_are_both_processed():
    db = Database(":memory:").connect()
    try:
        dedup = Deduplicator(db.conn)
        assert dedup.is_new("a")
        assert dedup.is_new("b")
        assert dedup.processed == 2
    finally:
        db.close()


def test_a_message_without_an_id_is_never_deduplicated():
    """Nothing to key on, so it must not be silently dropped."""
    db = Database(":memory:").connect()
    try:
        dedup = Deduplicator(db.conn)
        assert dedup.is_new(None)
        assert dedup.is_new(None)
    finally:
        db.close()


def test_processed_ids_are_persisted_and_countable():
    db = Database(":memory:").connect()
    try:
        dedup = Deduplicator(db.conn)
        dedup.is_new("a")
        dedup.is_new("a")
        dedup.is_new("b")
        assert db.count("processed_message") == 2
    finally:
        db.close()
