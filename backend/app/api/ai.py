"""
AI Service Proxy API Routes
Proxies requests to AI service with authentication and RBAC.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional

from app.core.config import settings
from app.services.rbac import get_rbac_service, Permission
from app.services.ai_client import get_ai_client
from app.services.audit import get_audit_service
from app.models.ai import (
    AIPredictRequest, AIPredictResponse,
    AIAnomalyRequest, AIAnomalyResponse,
    AIRiskResponse, AIRetrainRequest, AIRetrainResponse,
    AIWeeklyReportResponse, MODEL_TYPES, PREDICTION_TYPES
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/predict", response_model=AIPredictResponse, summary="Get threshold breach predictions")
async def predict(
    request: AIPredictRequest,
    ai_client=Depends(get_ai_client),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Get AI predictions for threshold breaches."""
    # rbac.check_permission(token_data.role, Permission.AI_PREDICT, request.zone_id)
    
    result = await ai_client.predict(request.zone_id, request.horizon_minutes, request.parameters)
    if not result:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="ai_predict",
        resource_type="ai_prediction",
        resource_id=request.zone_id,
        details={"horizon_minutes": request.horizon_minutes, "parameters": request.parameters},
    )
    
    return result


@router.post("/anomaly", response_model=AIAnomalyResponse, summary="Detect anomalies")
async def anomaly(
    request: AIAnomalyRequest,
    ai_client=Depends(get_ai_client),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Detect anomalies in measurements."""
    # rbac.check_permission(token_data.role, Permission.AI_ANOMALY, request.zone_id)
    
    result = await ai_client.anomaly(request.zone_id, request.measurements, request.timestamp)
    if not result:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    return result


@router.get("/risk/{zone_id}", response_model=AIRiskResponse, summary="Get zone risk score")
async def risk(
    zone_id: str,
    ai_client=Depends(get_ai_client),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Get dynamic risk score for a zone."""
    # rbac.check_permission(token_data.role, Permission.AI_RISK, zone_id)
    
    result = await ai_client.risk(zone_id)
    if not result:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    return result


@router.post("/retrain", response_model=AIRetrainResponse, summary="Trigger model retraining")
async def retrain(
    request: AIRetrainRequest,
    ai_client=Depends(get_ai_client),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Trigger AI model retraining (admin only)."""
    # Check admin permission
    # if token_data.role != "admin":
    #     raise HTTPException(403, "Admin required")
    # rbac.check_permission(token_data.role, Permission.AI_RETRAIN)
    
    result = await ai_client.retrain(request.model_type, request.force)
    if not result:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="ai_retrain",
        resource_type="ai_model",
        resource_id=request.model_type or "all",
        details={"force": request.force},
    )
    
    return result


@router.get("/report/weekly", response_model=AIWeeklyReportResponse, summary="Get weekly AI report")
async def weekly_report(
    ai_client=Depends(get_ai_client),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Get weekly AI analysis report."""
    # rbac.check_permission(token_data.role, Permission.AI_REPORT)
    
    result = await ai_client.weekly_report()
    if not result:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    return result


@router.get("/health", summary="Check AI service health")
async def ai_health(
    ai_client=Depends(get_ai_client),
):
    """Check AI service health."""
    healthy = await ai_client.health_check()
    return {
        "healthy": healthy,
        "enabled": ai_client.enabled,
        "url": ai_client.base_url,
        "circuit_breaker": ai_client.get_status(),
    }


@router.get("/models/list", summary="List available model types")
async def list_models():
    return {"model_types": MODEL_TYPES, "prediction_types": PREDICTION_TYPES}