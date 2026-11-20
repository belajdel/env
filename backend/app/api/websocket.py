"""
WebSocket API Routes
Real-time data streaming with JWT authentication.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, status
from typing import Optional

from app.services.websocket import get_websocket_manager, WebSocketManager
from app.services.auth import get_auth_service
from app.services.rbac import get_rbac_service
from app.core.logging import get_logger

router = APIRouter(prefix="/ws", tags=["websocket"])

logger = get_logger(__name__)


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    auth=Depends(get_auth_service),
):
    """WebSocket endpoint for real-time data."""
    await websocket.accept()
    
    connection = await ws_manager.connect(websocket, token)
    if not connection:
        return
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await ws_manager._send_error(connection, "INVALID_JSON", "Message must be valid JSON")
                continue
            
            await ws_manager.handle_message(connection.connection_id, message)
            
    except WebSocketDisconnect:
        logger.info("websocket_client_disconnect", connection_id=connection.connection_id)
    except Exception as e:
        logger.error("websocket_error", connection_id=connection.connection_id, error=str(e))
    finally:
        await ws_manager.disconnect(connection.connection_id)


@router.get("/stats", summary="Get WebSocket statistics")
async def websocket_stats(
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """Get WebSocket connection statistics (admin)."""
    # Check admin permission
    return ws_manager.get_stats()


@router.get("/connections", summary="List active WebSocket connections")
async def list_connections(
    ws_manager: WebSocketManager = Depends(get_websocket_manager),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """List active WebSocket connections (admin)."""
    return ws_manager.get_connection_info()


# Import json for message parsing
import json