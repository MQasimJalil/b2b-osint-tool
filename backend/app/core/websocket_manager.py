"""
WebSocket Connection Manager
Handles WebSocket connections, disconnections, and message broadcasting
"""

from typing import Dict, List
from fastapi import WebSocket
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Store active connections grouped by user_id
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Store reverse mapping for quick lookup
        self.websocket_to_user: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: The WebSocket connection
            user_id: The user ID associated with this connection
        """
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = []

        self.active_connections[user_id].append(websocket)
        self.websocket_to_user[websocket] = user_id

        logger.info(f"WebSocket connected for user {user_id}. Total connections: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection

        Args:
            websocket: The WebSocket connection to remove
        """
        user_id = self.websocket_to_user.get(websocket)

        if user_id and user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)

            # Clean up empty user entries
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

            # Remove from reverse mapping
            if websocket in self.websocket_to_user:
                del self.websocket_to_user[websocket]

            logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_personal_message(self, message: dict, user_id: str):
        """
        Send message to a specific user (all their connections)

        Args:
            message: The message dictionary to send
            user_id: The target user ID
        """
        if user_id not in self.active_connections:
            logger.warning(f"No active connections for user {user_id}")
            return

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()

        dead_connections = []

        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection)

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected users

        Args:
            message: The message dictionary to broadcast
        """
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()

        dead_connections = []

        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id}: {e}")
                    dead_connections.append(connection)

        # Clean up dead connections
        for connection in dead_connections:
            self.disconnect(connection)

    async def send_to_team(self, message: dict, team_id: str, user_ids: List[str]):
        """
        Send message to all members of a team

        Args:
            message: The message dictionary to send
            team_id: The team ID (for logging)
            user_ids: List of user IDs in the team
        """
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()

        for user_id in user_ids:
            await self.send_personal_message(message, user_id)

        logger.info(f"Message sent to team {team_id} ({len(user_ids)} users)")

    def get_active_users(self) -> List[str]:
        """Get list of currently connected user IDs"""
        return list(self.active_connections.keys())

    def get_connection_count(self, user_id: str = None) -> int:
        """
        Get connection count

        Args:
            user_id: Optional user ID to get count for specific user

        Returns:
            Number of active connections
        """
        if user_id:
            return len(self.active_connections.get(user_id, []))

        return sum(len(connections) for connections in self.active_connections.values())


# Global instance
manager = ConnectionManager()
