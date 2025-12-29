"""
WebSocket connection manager for MCP Banking Server.
Handles real-time transaction notifications.
"""

from fastapi import WebSocket
from typing import Dict, List, Set
import json
import asyncio


class ConnectionManager:
    """
    Manages WebSocket connections for real-time transaction updates.
    
    Supports multiple clients per account with automatic cleanup on disconnect.
    """
    
    def __init__(self):
        # Map of account_number -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, account_number: str) -> None:
        """
        Accept a new WebSocket connection and register it for an account.
        
        Args:
            websocket: The WebSocket connection to register
            account_number: The account number to subscribe to
        """
        await websocket.accept()
        
        async with self._lock:
            if account_number not in self.active_connections:
                self.active_connections[account_number] = set()
            self.active_connections[account_number].add(websocket)
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to transaction updates for account {account_number}",
            "account_number": account_number
        })
    
    async def disconnect(self, websocket: WebSocket, account_number: str) -> None:
        """
        Remove a WebSocket connection from the registry.
        
        Args:
            websocket: The WebSocket connection to remove
            account_number: The account number to unsubscribe from
        """
        async with self._lock:
            if account_number in self.active_connections:
                self.active_connections[account_number].discard(websocket)
                
                # Clean up empty sets
                if not self.active_connections[account_number]:
                    del self.active_connections[account_number]
    
    async def broadcast_transaction(
        self,
        account_number: str,
        transaction_data: dict
    ) -> None:
        """
        Broadcast a transaction notification to all connected clients for an account.
        
        Args:
            account_number: The account number to broadcast to
            transaction_data: The transaction data to send
        """
        async with self._lock:
            connections = self.active_connections.get(account_number, set()).copy()
        
        if not connections:
            return
        
        message = {
            "type": "transaction",
            "data": transaction_data
        }
        
        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if account_number in self.active_connections:
                        self.active_connections[account_number].discard(ws)
    
    def get_connection_count(self, account_number: str) -> int:
        """Get the number of active connections for an account."""
        return len(self.active_connections.get(account_number, set()))
    
    def get_total_connections(self) -> int:
        """Get the total number of active connections."""
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager instance
manager = ConnectionManager()
