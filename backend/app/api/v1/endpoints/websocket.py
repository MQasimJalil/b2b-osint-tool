"""
WebSocket endpoint for real-time updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from fastapi.responses import JSONResponse
from app.core.websocket_manager import manager
from app.core.security import decode_token
from app.schemas.websocket import WebSocketMessage
import logging
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time updates

    Client connects with: ws://localhost:8000/api/v1/ws?token=<jwt_token>

    Messages are automatically pushed to clients when:
    - Jobs start, update progress, complete, or fail
    - Companies are updated or enriched
    - Email drafts are generated or sent
    - Notifications are created
    - Other users perform actions on shared resources
    """
    try:
        # Verify JWT token
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")

            if not user_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        except Exception as e:
            logger.error(f"WebSocket authentication failed: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Connect the WebSocket
        await manager.connect(websocket, user_id)

        try:
            # Send connection success message
            await websocket.send_json({
                "event": "connected",
                "data": {
                    "user_id": user_id,
                    "message": "WebSocket connected successfully"
                }
            })

            # Keep connection alive and listen for messages
            while True:
                # Receive messages from client (for heartbeat/ping)
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                    # Handle ping/pong for keep-alive
                    if data == "ping":
                        await websocket.send_text("pong")

                except asyncio.TimeoutError:
                    # Send heartbeat every 30 seconds
                    await websocket.send_json({
                        "event": "heartbeat",
                        "data": {"status": "alive"}
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user_id}")

        finally:
            manager.disconnect(websocket)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass


@router.get("/ws/status")
async def websocket_status():
    """
    Get WebSocket server status

    Returns:
        Active connections count and connected users
    """
    return {
        "status": "online",
        "active_connections": manager.get_connection_count(),
        "connected_users": len(manager.get_active_users())
    }


@router.get("/ws/test/{user_id}")
async def test_websocket_message(user_id: str):
    """
    Test endpoint to send a test message to a specific user
    (Development only - remove in production)
    """
    test_message = {
        "event": "notification",
        "data": {
            "id": "test-123",
            "type": "info",
            "title": "Test Notification",
            "message": "This is a test WebSocket message"
        }
    }

    await manager.send_personal_message(test_message, user_id)

    return {"status": "sent", "user_id": user_id}
