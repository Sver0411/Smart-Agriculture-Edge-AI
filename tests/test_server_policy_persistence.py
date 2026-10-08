import asyncio
import sqlite3
import pytest
from server.server import Server
from common.state_store import StateStore
from gateway.edge_decision import EdgeDecider
from server.database import Database
from common import config


def test_updates_broadcast_restart_and_reorder(tmp_path,monkeypatch):
    async def scenario():
        path=str(tmp_path/'s.db');s=Server(port=0,db_path=path,policy_version=100)
        await s.start();messages=[]
        async def send(w,m):messages.append(m)
        monkeypatch.setattr('server.server.send_message',send)
        s.clients['A1']=FakeWriter()
        await s._broadcast_policy();await s._broadcast_policy()
        assert [m.payload['policy_version'] for m in messages]==[100,100]
        d=EdgeDecider(store=StateStore(tmp_path/'g.db'))
        assert d.update_policy(messages[-1].payload)[0]
        assert not s.update_policy(config.DEFAULT_POLICY)
        await s.stop();s=Server(port=0,db_path=path);await s.start()
        try:
            assert s.policy_available and s.policy_version==100
            assert s.update_policy({'soil_moisture_threshold':18})
            assert s.policy_version==101
            d=EdgeDecider(store=StateStore(tmp_path/'g.db'))
            assert d.update_policy({**s.policy,'policy_version':101})[0]
            assert not d.update_policy(messages[0].payload)[0]
        finally:await s.stop()
        s=Server(port=0,db_path=path);await s.start()
        try:
            d=EdgeDecider(store=StateStore(tmp_path/'g.db'))
            assert s.policy_version==d.policy_version==101
            assert s.policy==d.policy
        finally:await s.stop()
    asyncio.run(scenario())


class FakeWriter:
    def close(self):pass


def test_failed_write_preserves_live_and_durable_head(tmp_path,monkeypatch):
    async def scenario():
        s=Server(port=0,db_path=str(tmp_path/'s.db'));await s.start()
        def fail(*a):raise sqlite3.OperationalError('disk full')
        monkeypatch.setattr(s.db,'update_policy',fail)
        with pytest.raises(sqlite3.Error):s.update_policy({'soil_moisture_threshold':18})
        assert s.policy_version==1 and s.policy==config.DEFAULT_POLICY
        await s.stop()
        s=Server(port=0,db_path=str(tmp_path/'s.db'));await s.start()
        assert s.policy_version==1
        await s.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize('damage',['old_schema','deleted_head','checksum','version'])
def test_unrecoverable_publication_state_fails_closed(tmp_path,damage,monkeypatch):
    async def scenario():
        path=str(tmp_path/'s.db')
        if damage=='old_schema':
            db=Database(path);db.init_schema();db.close()
        else:
            s=Server(port=0,db_path=path,policy_version=100);await s.start();await s.stop()
            with sqlite3.connect(path) as conn:
                if damage=='deleted_head':conn.execute('DELETE FROM server_policy')
                elif damage=='checksum':conn.execute("UPDATE server_policy SET checksum='bad'")
                else:conn.execute('UPDATE server_policy SET version=-1')
        s=Server(port=0,db_path=path);await s.start();sent=[]
        async def send(w,m):sent.append(m)
        monkeypatch.setattr('server.server.send_message',send)
        s.clients['A1']=FakeWriter()
        assert not s.policy_available
        with pytest.raises(ValueError):s.update_policy({'soil_moisture_threshold':18})
        await s._broadcast_policy();assert sent==[]
        await s.stop()
    asyncio.run(scenario())


def test_two_publishers_cannot_allocate_same_version(tmp_path):
    async def scenario():
        path=str(tmp_path/'s.db');a=Server(port=0,db_path=path);b=Server(port=0,db_path=path)
        await a.start();await b.start()
        assert a.update_policy({'soil_moisture_threshold':18})
        with pytest.raises(ValueError):b.update_policy({'soil_moisture_threshold':19})
        assert b.policy_version==1
        await a.stop();await b.stop()
    asyncio.run(scenario())
