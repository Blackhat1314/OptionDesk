"""
WebSocket Connection Manager
==============================
Manages all frontend WebSocket connections and broadcasts
real-time market data from Dhan feed to connected clients.
"""

import asyncio
import json
import time
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import orjson



class ConnectionManager:
    """Manages WebSocket connections from the React frontend."""

    def __init__(self):
        # active_connections: {client_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # subscriptions: {client_id: Set[str]}  (channels like "option_chain:NIFTY")
        self.subscriptions: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        async with self._lock:
            self.active_connections[client_id] = websocket
            self.subscriptions[client_id] = set()

    async def disconnect(self, client_id: str):
        async with self._lock:
            self.active_connections.pop(client_id, None)
            self.subscriptions.pop(client_id, None)

    def subscribe(self, client_id: str, channel: str):
        if client_id in self.subscriptions:
            self.subscriptions[client_id].add(channel)

    def unsubscribe(self, client_id: str, channel: str):
        if client_id in self.subscriptions:
            self.subscriptions[client_id].discard(channel)

    async def send_to_client(self, client_id: str, message: Dict):
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_text(orjson.dumps(message).decode())
            except Exception as e:
                await self.disconnect(client_id)

    async def broadcast(self, message: Dict, channel: Optional[str] = None):
        """Broadcast to all clients subscribed to a channel, or all if channel=None."""
        if not self.active_connections:
            return

        msg_bytes = orjson.dumps(message).decode()
        dead_clients = []

        for client_id, ws in list(self.active_connections.items()):
            # Check channel subscription
            if channel and channel not in self.subscriptions.get(client_id, set()):
                continue
            try:
                await ws.send_text(msg_bytes)
            except Exception:
                dead_clients.append(client_id)

        for cid in dead_clients:
            await self.disconnect(cid)

    async def broadcast_market_update(self, update_type: str, data: Any, symbol: str = "NIFTY"):
        """Broadcast a typed market update to subscribed clients."""
        message = {
            "type": update_type,
            "data": data,
            "symbol": symbol,
            "timestamp": time.time(),
        }
        channel = f"{update_type}:{symbol}"
        await self.broadcast(message, channel=None)  # broadcast to all for now

    def get_connection_count(self) -> int:
        return len(self.active_connections)


# ─── Market State Store ───────────────────────────────────────────────────────

class MarketStateStore:
    """
    In-memory store for the latest market state.
    Acts as a cache so new WebSocket connections get immediately populated data.
    """

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any):
        async with self._lock:
            self._state[key] = value

    async def get(self, key: str) -> Optional[Any]:
        return self._state.get(key)

    async def get_all(self) -> Dict[str, Any]:
        return dict(self._state)

    def get_sync(self, key: str) -> Optional[Any]:
        return self._state.get(key)

    def set_sync(self, key: str, value: Any):
        self._state[key] = value


# ─── Singletons ───────────────────────────────────────────────────────────────

_manager: Optional[ConnectionManager] = None
_state_store: Optional[MarketStateStore] = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


def get_market_state() -> MarketStateStore:
    global _state_store
    if _state_store is None:
        _state_store = MarketStateStore()
    return _state_store
