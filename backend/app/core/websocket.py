from uuid import UUID

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """Sockets per conversation. Turns broadcast to whoever is connected *now*."""

    def __init__(self):
        self.active_connections: dict[UUID, list[WebSocket]] = {}

    async def connect(self, conversation_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(conversation_id, []).append(websocket)

    def disconnect(self, conversation_id: UUID, websocket: WebSocket):
        connections = self.active_connections.get(conversation_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                del self.active_connections[conversation_id]

    async def send_to_conversation(self, message: dict, conversation_id: UUID):
        # Iterate over a copy: a dead socket is dropped instead of raising into
        # the turn (a closed tab must never break the reply being written).
        for connection in list(self.active_connections.get(conversation_id, [])):
            try:
                await connection.send_json(message)
            except Exception:
                logger.info("Dropping dead websocket | conversation={}", conversation_id)
                self.disconnect(conversation_id, connection)


manager = ConnectionManager()
