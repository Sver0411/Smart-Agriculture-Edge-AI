"""Gateway behavior characterized before AR-1; keep the observable boundary."""
import asyncio
import sqlite3
from copy import deepcopy

import pytest

from common.messages import ALERT, Message, SENSOR_DATA
from gateway.gateway import Gateway


def test_record_and_legacy_sequence_order_are_preserved(monkeypatch):
    async def run():
        g = Gateway('A1')
        g.ingress_boot = 'gateway-boot'
        monkeypatch.setattr('gateway.gateway.time.monotonic', lambda: 12.0)
        original = {'data': {'soil_moisture': 10, 'temperature': 25}, 'boot_id': 'b',
                    'health_state': 'HEALTHY', 'sampling': {'interval_s': 20}}
        m = Message(type=SENSOR_DATA, source='B1', target='A1', sequence=5,
                    timestamp=100, payload=deepcopy(original))
        m._gateway_ingress = ('gateway-boot', 10.0, 200.0)
        try:
            await g._process_sensor_message(m)
            upload = g.upload_queue.get_nowait()
            assert upload.payload['record'] == {
                'soil_moisture': 10, 'temperature': 25,
                'control_trust': {'IRRIGATION': True, 'VENTILATION': True},
                'trusted_channels': ['soil_moisture', 'temperature'],
                'timestamp': 100, 'received_at': 200.0,
                'gateway_received_monotonic': 10.0, 'gateway_decision_monotonic': 12.0,
                'gateway_boot_id': 'gateway-boot', 'gateway_queue_wait_ms': 2000.0,
                'boot_id': 'b', 'health_state': 'HEALTHY', 'sampling': {'interval_s': 20},
                'usable_for_control': True, 'gateway_id': 'A1', 'sensor_node_id': 'B1'}
            command, retry = g.command_queue.get_nowait()
            assert command.target == 'C1' and not retry
            assert command.payload['gateway_generation'] == 1
            assert m.payload == original
            for seq in [5, 4]:
                duplicate = Message(type=SENSOR_DATA, source='B1', target='A1', sequence=seq,
                                    payload=deepcopy(original))
                await g._process_sensor_message(duplicate)
                assert not g.upload_queue.get_nowait().payload['record']['usable_for_control']
            assert g.command_queue.empty()
            assert g.metrics.get('sensor_messages') == 3
            assert g.metrics.get('reordered_or_duplicate_samples') == 2
            assert g.metrics.get('sensor_control_skipped') == 2
        finally:
            g.offline_queue.close()
    asyncio.run(run())


def test_invalid_data_does_not_consume_legacy_sequence():
    async def run():
        g = Gateway('A1')
        try:
            await g._process_sensor_message(Message(type=SENSOR_DATA, source='B1', target='A1',
                sequence=5, payload={'boot_id': 'b', 'data': []}))
            assert g.sequences.latest == {} and g.upload_queue.empty()
            await g._process_sensor_message(Message(type=SENSOR_DATA, source='B1', target='A1',
                sequence=5, payload={'boot_id': 'b', 'data': {'soil_moisture': 10}}))
            assert g.command_queue.get_nowait()[0].target == 'C1'
        finally:
            g.offline_queue.close()
    asyncio.run(run())


@pytest.mark.parametrize('source,expected', [('B1', 'C1'), ('B2', 'C2')])
def test_takeover_uses_fixed_zone_and_checks_live_authority(source, expected):
    async def run():
        g = Gateway('A2')
        g._takeover()
        try:
            def message():
                return Message(type=SENSOR_DATA, source=source, target='A2',
                               payload={'data': {'soil_moisture': 10}})
            await g._process_sensor_message(message())
            assert g.command_queue.get_nowait()[0].target == expected
            g.ownership.role = 'STANDBY'
            await g._process_sensor_message(message())
            assert g.command_queue.empty()
            assert g.metrics.get('decision_calls') == 1
            assert g.upload_queue.qsize() >= 2
        finally:
            g.offline_queue.close()
    asyncio.run(run())


def test_alert_payload_identity_and_malformed_reasons_stay_compatible():
    async def run():
        g = Gateway('A1')
        m = Message(type=ALERT, source='B1', target='A1', message_id='alert',
                    payload={'data': {'temperature': 25}, 'health_state': 'FAULT',
                             'reasons': [7], 'severity': 'CRITICAL'})
        try:
            await g._process_sensor_message(m)
            upload = g.upload_queue.get_nowait()
            assert upload.message_id == 'alert' and upload.type == ALERT
            assert upload.payload == {
                'alert_type': 'SENSOR_FAULT', 'health': {}, 'health_score': None,
                'fault_flags': [], 'data': {'temperature': 25}, 'fault_signature': None,
                'notification': None, 'sensor_node_id': 'B1', 'health_state': 'FAULT',
                'severity': 'CRITICAL', 'message': 'malformed sensor fault evidence'}
            assert g.command_queue.empty()
        finally:
            g.offline_queue.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['sqlite', 'ack-loss'])
def test_durable_failure_and_retry_keep_commit_ack_and_decision_order(tmp_path, monkeypatch, failure):
    # Use the existing on-wire contract fixture, not another reliability model.
    from test_b1_gateway_receipts import sample
    async def run():
        g = Gateway('A1', queue_path=str(tmp_path/'outbox.db'))
        g.sensor_boots['B1'] = 'device-boot'
        g.connections['B1'] = object()
        m = sample(); m.payload['data']['temperature'] = 36
        original = deepcopy(m.to_dict())
        events = []
        admit = g.offline_queue.admit_sensor
        decide = g.decider.decide
        def commit(*args):
            events.append('admit')
            if failure == 'sqlite' and events.count('admit') == 1:
                raise sqlite3.OperationalError('injected failure')
            return admit(*args)
        async def ack(writer, message):
            events.append('ack')
            assert g.offline_queue.count() == 1
            if failure == 'ack-loss' and events.count('ack') == 1:
                raise BrokenPipeError('lost ACK after commit')
        def decision(*args, **kwargs):
            events.append('decide')
            return decide(*args, **kwargs)
        monkeypatch.setattr(g.offline_queue, 'admit_sensor', commit)
        monkeypatch.setattr(g.decider, 'decide', decision)
        monkeypatch.setattr('gateway.gateway.send_message', ack)
        try:
            if failure == 'ack-loss':
                with pytest.raises(BrokenPipeError):
                    await g._process_sensor_message(m)
            else:
                await g._process_sensor_message(m)
                assert events == ['admit'] and g.offline_queue.count() == 0
                assert g.sequences.latest == {}
            assert g.command_queue.empty()
            await g._process_sensor_message(deepcopy(m))
            assert m.to_dict() == original
            if failure == 'sqlite':
                assert events == ['admit', 'admit', 'ack', 'decide']
                assert g.command_queue.get_nowait()[0].target == 'C1'
            else:
                assert events == ['admit', 'ack', 'admit', 'ack']
                assert g.command_queue.empty()
            assert g.offline_queue.count() == 1
        finally:
            g.offline_queue.close()
    asyncio.run(run())
