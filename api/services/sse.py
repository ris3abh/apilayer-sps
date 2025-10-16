# api/services/sse.py
"""
Server-Sent Events (SSE) Manager

Manages real-time event streaming to frontend clients using SSE.
Handles connection management, broadcasting, and client lifecycle.

SSE is chosen over WebSockets for simplicity:
- One-way communication (server → client)
- Works over HTTP (no special protocol)
- Auto-reconnection built into browser
- Simpler to deploy (no WebSocket infrastructure needed)

References:
- MDN SSE Guide: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- FastAPI SSE: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from uuid import UUID
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """
    Manages SSE connections for real-time event streaming.
    
    Features:
    - Per-execution connection pools
    - Connection limit per user (prevents abuse)
    - Automatic cleanup on disconnect
    - Heartbeat to detect dead connections
    - Broadcast to all clients watching an execution
    """
    
    # Maximum concurrent connections per user
    MAX_CONNECTIONS_PER_USER = 3
    
    # Heartbeat interval (seconds)
    HEARTBEAT_INTERVAL = 30
    
    def __init__(self):
        # execution_id -> set of queues
        self.connections: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        
        # user_id -> count of connections
        self.user_connections: Dict[str, int] = defaultdict(int)
        
        # queue -> (execution_id, user_id) for cleanup
        self.queue_metadata: Dict[asyncio.Queue, tuple] = {}
        
        logger.info("SSE Connection Manager initialized")
    
    async def connect(
        self,
        execution_id: UUID,
        user_id: UUID,
        queue: asyncio.Queue
    ) -> bool:
        """
        Register a new SSE connection.
        
        Args:
            execution_id: UUID of the execution to stream
            user_id: UUID of the user connecting
            queue: AsyncIO queue for this connection
        
        Returns:
            True if connection accepted, False if limit exceeded
        """
        user_id_str = str(user_id)
        execution_id_str = str(execution_id)
        
        # Check connection limit
        if self.user_connections[user_id_str] >= self.MAX_CONNECTIONS_PER_USER:
            logger.warning(
                f"⚠️  Connection limit reached for user {user_id_str}: "
                f"{self.user_connections[user_id_str]}/{self.MAX_CONNECTIONS_PER_USER}"
            )
            return False
        
        # Add connection
        self.connections[execution_id_str].add(queue)
        self.user_connections[user_id_str] += 1
        self.queue_metadata[queue] = (execution_id_str, user_id_str)
        
        logger.info(
            f"✅ SSE connected: execution={execution_id_str[:8]}..., "
            f"user={user_id_str[:8]}..., "
            f"total_connections={len(self.connections[execution_id_str])}"
        )
        
        return True
    
    def disconnect(self, queue: asyncio.Queue):
        """
        Unregister an SSE connection.
        
        Args:
            queue: AsyncIO queue to disconnect
        """
        if queue not in self.queue_metadata:
            return
        
        execution_id_str, user_id_str = self.queue_metadata[queue]
        
        # Remove from connections
        if execution_id_str in self.connections:
            self.connections[execution_id_str].discard(queue)
            
            # Clean up empty execution pools
            if not self.connections[execution_id_str]:
                del self.connections[execution_id_str]
        
        # Update user connection count
        self.user_connections[user_id_str] -= 1
        if self.user_connections[user_id_str] <= 0:
            del self.user_connections[user_id_str]
        
        # Clean up metadata
        del self.queue_metadata[queue]
        
        logger.info(
            f"🔌 SSE disconnected: execution={execution_id_str[:8]}..., "
            f"user={user_id_str[:8]}..."
        )
    
    async def broadcast(
        self,
        execution_id: UUID,
        event_type: str,
        data: Dict[str, Any]
    ):
        """
        Broadcast an event to all clients watching an execution.
        
        Args:
            execution_id: UUID of the execution
            event_type: Type of event (e.g., "message", "status", "checkpoint")
            data: Event data to send
        """
        execution_id_str = str(execution_id)
        
        if execution_id_str not in self.connections:
            logger.debug(f"No SSE connections for execution {execution_id_str[:8]}...")
            return
        
        # Format SSE message
        message = self._format_sse_message(event_type, data)
        
        # Send to all connected clients
        dead_queues = []
        for queue in self.connections[execution_id_str]:
            try:
                await queue.put(message)
            except Exception as e:
                logger.error(f"Failed to send to queue: {e}")
                dead_queues.append(queue)
        
        # Clean up dead connections
        for queue in dead_queues:
            self.disconnect(queue)
        
        logger.debug(
            f"📡 Broadcast {event_type} to {len(self.connections[execution_id_str])} clients"
        )
    
    def _format_sse_message(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> str:
        """
        Format data as SSE message.
        
        SSE format:
        event: <event_type>
        data: <json_data>
        id: <message_id>
        
        Args:
            event_type: Event type
            data: Event data
        
        Returns:
            Formatted SSE message string
        """
        message_id = datetime.utcnow().isoformat()
        json_data = json.dumps(data)
        
        return f"event: {event_type}\ndata: {json_data}\nid: {message_id}\n\n"
    
    async def send_heartbeat(self, queue: asyncio.Queue):
        """
        Send heartbeat to keep connection alive.
        
        Args:
            queue: Queue to send heartbeat to
        """
        try:
            heartbeat = self._format_sse_message(
                "heartbeat",
                {"timestamp": datetime.utcnow().isoformat()}
            )
            await queue.put(heartbeat)
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
    
    def get_connection_count(self, execution_id: UUID) -> int:
        """
        Get number of active connections for an execution.
        
        Args:
            execution_id: UUID of the execution
        
        Returns:
            Number of active connections
        """
        execution_id_str = str(execution_id)
        return len(self.connections.get(execution_id_str, set()))
    
    def get_user_connection_count(self, user_id: UUID) -> int:
        """
        Get number of active connections for a user.
        
        Args:
            user_id: UUID of the user
        
        Returns:
            Number of active connections
        """
        return self.user_connections.get(str(user_id), 0)


# Global SSE manager instance
sse_manager = SSEConnectionManager()


def get_sse_manager() -> SSEConnectionManager:
    """
    Get the global SSE manager instance.
    
    Used as FastAPI dependency.
    """
    return sse_manager