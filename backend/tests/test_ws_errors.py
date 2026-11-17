"""WebSocket command errors say which command they answer (client undoes exactly that)."""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.ws as ws_module
from app.services.turns.runner import QueueFullError

CONV, USER = uuid4(), uuid4()


class FakeRunner:
    async def stop(self, conversation_id):
        return False

    async def confirm(self, conversation_id, confirmation_id, decision, feedback=""):
        return False

    async def submit(self, conversation_id, user_id, payload, client_id=None):
        raise QueueFullError("5 messages are already waiting in this conversation.")

    async def dequeue(self, conversation_id, turn_id):
        return False

    def snapshot(self, conversation_id):
        return {"conversation_id": str(conversation_id), "current": None, "queued": []}


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _query):
        return type("R", (), {"scalar_one_or_none": lambda self: CONV})()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(ws_module, "decode_access_token", lambda token: USER)
    monkeypatch.setattr(ws_module, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(ws_module, "turn_runner", FakeRunner())
    app = FastAPI()
    app.include_router(ws_module.router)
    return TestClient(app)


def test_rejected_commands_echo_their_type_and_ids(client):
    with client.websocket_connect(f"/ws/{CONV}?token=t") as ws:
        assert ws.receive_json()["type"] == "turn_state"

        ws.send_json({"content": "hi", "client_id": "c-1"})
        assert ws.receive_json() == {"type": "error", "detail": "5 messages are already waiting in this conversation.",
                                     "command": "send", "client_id": "c-1"}

        ws.send_json({"type": "confirm", "confirmation_id": "k-9", "decision": "approve"})
        error = ws.receive_json()
        assert error["command"] == "confirm" and error["confirmation_id"] == "k-9" and "client_id" not in error

        ws.send_json({"type": "stop"})
        assert ws.receive_json() == {"type": "error", "detail": "Nothing is running.", "command": "stop"}

        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["command"] == "bogus"

        ws.send_text("not json")
        assert ws.receive_json()["command"] == "unknown"
