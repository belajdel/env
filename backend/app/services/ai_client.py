"""
AI Service Client
HTTP client for communicating with the AI service with timeout and fallback.
"""

import asyncio
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai import (
    AIPredictionPublic, RiskScorePublic, AIPredictResponse, 
    AIAnomalyResponse, AIRiskResponse, AIRetrainResponse, AIWeeklyReportResponse,
    AIPredictRequest, AIAnomalyRequest, AIRetrainRequest
)

logger = get_logger(__name__)


class AIClient:
    """Client for AI service with timeout, retry, and fallback."""
    
    def __init__(self):
        self.base_url = settings.AI_SERVICE_URL.rstrip("/")
        self.timeout = settings.AI_SERVICE_TIMEOUT_MS / 1000.0
        self.enabled = settings.AI_SERVICE_ENABLED
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breaker_failures = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_threshold = 5
        self._circuit_breaker_reset_timeout = 60  # seconds
        self._last_failure_time: Optional[datetime] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows requests."""
        if not self._circuit_breaker_open:
            return True
        
        # Check if reset timeout has passed
        if self._last_failure_time:
            elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
            if elapsed > self._circuit_breaker_reset_timeout:
                self._circuit_breaker_open = False
                self._circuit_breaker_failures = 0
                logger.info("ai_circuit_breaker_reset")
                return True
        
        return False
    
    def _record_success(self) -> None:
        """Record successful request."""
        self._circuit_breaker_failures = 0
        self._circuit_breaker_open = False
    
    def _record_failure(self) -> None:
        """Record failed request."""
        self._circuit_breaker_failures += 1
        self._last_failure_time = datetime.now(timezone.utc)
        
        if self._circuit_breaker_failures >= self._circuit_breaker_threshold:
            self._circuit_breaker_open = True
            logger.warning("ai_circuit_breaker_opened", failures=self._circuit_breaker_failures)
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Make HTTP request with circuit breaker."""
        if not self.enabled:
            return None
        
        if not self._check_circuit_breaker():
            logger.debug("ai_circuit_breaker_open_skip")
            return None
        
        client = await self._get_client()
        
        try:
            response = await client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            self._record_success()
            return response.json()
        except httpx.TimeoutException:
            self._record_failure()
            logger.warning("ai_request_timeout", endpoint=endpoint)
            return None
        except httpx.HTTPStatusError as e:
            self._record_failure()
            logger.warning("ai_request_http_error", endpoint=endpoint, status=e.response.status_code)
            return None
        except Exception as e:
            self._record_failure()
            logger.warning("ai_request_error", endpoint=endpoint, error=str(e))
            return None
    
    # ============================================
    # AI Service Endpoints
    # ============================================
    
    async def predict(
        self, zone_id: str, horizon_minutes: int = 30, 
        parameters: List[str] = None
    ) -> Optional[AIPredictResponse]:
        """Call POST /predict endpoint."""
        request = AIPredictRequest(
            zone_id=zone_id,
            horizon_minutes=horizon_minutes,
            parameters=parameters,
        )
        
        result = await self._request("POST", "/predict", json=request.model_dump(mode="json"))
        if result:
            return AIPredictResponse(**result)
        return None
    
    async def predict_single(self, zone_id: str, parameter: str, value: float) -> Optional[AIPredictionPublic]:
        """Predict threshold breach for a single parameter."""
        result = await self.predict(zone_id, horizon_minutes=30, parameters=[parameter])
        if result and parameter in result.predictions:
            return result.predictions[parameter]
        return None
    
    async def anomaly(
        self, zone_id: str, measurements: Dict[str, float], timestamp: datetime
    ) -> Optional[AIAnomalyResponse]:
        """Call POST /anomaly endpoint."""
        request = AIAnomalyRequest(
            zone_id=zone_id,
            measurements=measurements,
            timestamp=timestamp,
        )
        
        result = await self._request("POST", "/anomaly", json=request.model_dump(mode="json"))
        if result:
            return AIAnomalyResponse(**result)
        return None
    
    async def risk(self, zone_id: str) -> Optional[AIRiskResponse]:
        """Call GET /risk/{zone_id} endpoint."""
        result = await self._request("GET", f"/risk/{zone_id}")
        if result:
            return AIRiskResponse(**result)
        return None
    
    async def retrain(self, model_type: str = None, force: bool = False) -> Optional[AIRetrainResponse]:
        """Call POST /retrain endpoint."""
        request = AIRetrainRequest(model_type=model_type, force=force)
        
        result = await self._request("POST", "/retrain", json=request.model_dump(mode="json"))
        if result:
            return AIRetrainResponse(**result)
        return None
    
    async def weekly_report(self) -> Optional[AIWeeklyReportResponse]:
        """Call GET /report/weekly endpoint."""
        result = await self._request("GET", "/report/weekly")
        if result:
            return AIWeeklyReportResponse(**result)
        return None
    
    async def health_check(self) -> bool:
        """Check AI service health."""
        if not self.enabled:
            return False
        
        client = await self._get_client()
        try:
            response = await client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get client status."""
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout,
            "circuit_breaker_open": self._circuit_breaker_open,
            "circuit_breaker_failures": self._circuit_breaker_failures,
            "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
        }


_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AIClient instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client