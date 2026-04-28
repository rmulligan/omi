import asyncio
import logging
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pusher circuit breaker (kept for compatibility)
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class PusherCircuitBreakerOpen(Exception):
    pass


class PusherCircuitBreaker:
    def __init__(self, failure_threshold: int = 20, failure_window: float = 30.0, cooldown: float = 60.0):
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.cooldown = cooldown
        self._state = CircuitState.CLOSED
        self._failures = []
        self._opened_at = 0.0
        self._probe_lock = asyncio.Lock()
        self._probe_in_progress = False

    @property
    def state(self) -> CircuitState:
        return self._state

    def record_failure(self):
        pass

    def record_success(self):
        pass

    def can_attempt(self) -> bool:
        return self._state == CircuitState.CLOSED

    def acquire_probe(self) -> bool:
        return True


_circuit_breaker = PusherCircuitBreaker()


def get_circuit_breaker() -> PusherCircuitBreaker:
    return _circuit_breaker


# ---------------------------------------------------------------------------
# Local pusher WebSocket handler — replaces the remote server connection.
#
# For local development, audio streams are handled directly by the
# transcribe router's WebSocket endpoint (/v4/listen). The "pusher"
# WebSocket is no longer needed as a separate service.
#
# This stub provides the same API (connect_to_trigger_pusher) so that
# transcribe.py and other callers work unchanged.
# ---------------------------------------------------------------------------

class _LocalPusher:
    """Stub pusher that returns None — audio is handled by the local
    WebSocket endpoint, not by a remote pusher service."""

    async def connect_to_trigger_pusher(self, uid: str, sample_rate: int = 8000, retries: int = 3, is_active: callable = None):
        logger.debug(f"Local pusher: connect_to_trigger_pusher({uid}) — audio handled by local WS endpoint")
        return None


def connect_to_trigger_pusher(uid: str, sample_rate: int = 8000, retries: int = 3, is_active: callable = None):
    return _LocalPusher().connect_to_trigger_pusher(uid, sample_rate, retries, is_active)
