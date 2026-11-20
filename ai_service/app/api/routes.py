"""
AI Service API Routes
Endpoints for predictions, anomaly detection, risk scoring, and model management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import init_database, get_database, Collections
from app.core.logging import get_logger
from app.models.ai import (
    ModelType, ModelStatus, DataSource, PredictionType,
    PredictRequest, PredictResponse,
    AnomalyRequest, AnomalyResponse,
    RiskScoreRequest, RiskScoreResponse,
    RetrainRequest, RetrainResponse,
    WeeklyReportResponse, HealthResponse,
    AIModelInDB, ModelMetadataInDB,
)
from app.services.inference import get_inference_service
from app.services.model_trainer import train_all_models
from app.services.data_generator import generate_and_save_synthetic_data, SyntheticDataGenerator, SyntheticDataConfig
from app.services.retraining import get_retraining_scheduler, RetrainingScheduler
from app.models.ai import ModelType, DataSource

logger = get_logger(__name__)

router = APIRouter()


# ============================================
# Health Check
# ============================================

@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check():
    """Check AI service health."""
    db = get_database()
    inference = get_inference_service()
    
    # Check database
    db_status = "healthy"
    try:
        await db.command("ping")
    except Exception:
        db_status = "unhealthy"
    
    # Check models loaded
    models_loaded = len(inference.model_cache)
    
    # Get last training time
    last_training = None
    cursor = db[Collections.AI_MODELS].find({"status": ModelStatus.READY}).sort("created_at", -1).limit(1)
    async for doc in cursor:
        last_training = doc.get("created_at")
    
    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        models_loaded=models_loaded,
        last_training=last_training,
        database=db_status,
        mqtt="connected",  # Would check MQTT connection
    )


# ============================================
# Predictions
# ============================================

@router.post("/predict", response_model=PredictResponse, summary="Get threshold breach predictions")
async def predict(request: PredictRequest):
    """
    Get AI predictions for threshold breaches.
    
    - **zone_id**: Zone to predict for
    - **horizon_minutes**: Prediction horizon (5-1440 minutes)
    - **parameters**: Specific parameters to predict (optional, default all)
    """
    inference = get_inference_service()
    result = await inference.predict_threshold_breach(request)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI model not available or insufficient data"
        )
    
    return result


# ============================================
# Anomaly Detection
# ============================================

@router.post("/anomaly", response_model=AnomalyResponse, summary="Detect anomalies")
async def detect_anomaly(request: AnomalyRequest):
    """
    Detect anomalies in current measurements.
    
    - **zone_id**: Zone ID
    - **measurements**: Dictionary of parameter -> value
    - **timestamp**: Measurement timestamp (optional, defaults to now)
    """
    inference = get_inference_service()
    result = await inference.detect_anomalies(request)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI model not available"
        )
    
    return result


# ============================================
# Risk Scoring
# ============================================

@router.get("/risk/{zone_id}", response_model=RiskScoreResponse, summary="Get zone risk score")
async def get_risk_score(zone_id: str):
    """
    Get dynamic risk score for a zone.
    
    Risk score (0-100) based on:
    - Parameter anomaly scores
    - Threshold proximity
    - Trend directions
    - Historical alert frequency
    - AI prediction confidence
    """
    inference = get_inference_service()
    request = RiskScoreRequest(zone_id=zone_id)
    result = await inference.calculate_risk_score(request)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Insufficient data for risk calculation"
        )
    
    return result


# ============================================
# Model Retraining
# ============================================

@router.post("/retrain", response_model=RetrainResponse, summary="Trigger model retraining")
async def retrain(
    request: RetrainRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger model retraining (admin only).
    
    - **model_type**: Specific model to retrain (None = all)
    - **force**: Force retrain even if recent model exists
    - **data_source**: Data source for training
    """
    # Run training in background
    background_tasks.add_task(
        _run_training,
        request.model_type,
        request.force,
        request.data_source,
    )
    
    return RetrainResponse(
        model_type=request.model_type or ModelType.ISOLATION_FOREST,
        status=ModelStatus.TRAINING,
        message="Retraining started in background",
        training_samples=0,
        metrics={},
        model_version="pending",
        started_at=datetime.now(timezone.utc),
    )


async def _run_training(model_type: Optional[ModelType], force: bool, data_source: DataSource):
    """Background task for model training."""
    try:
        logger.info("background_training_started", model_type=model_type, force=force)
        result = await train_all_models(
            zone_id=None,
            parameter=None,
            data_source=data_source,
            force=force,
        )
        logger.info("background_training_completed", result=result)
    except Exception as e:
        logger.error("background_training_failed", error=str(e))


@router.get("/models", summary="List trained models")
async def list_models(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    status: Optional[ModelStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List trained models with filters."""
    db = get_database()
    
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    if status:
        query["status"] = status.value
    
    cursor = db[Collections.AI_MODELS].find(query).sort("created_at", -1).skip(offset).limit(limit)
    models = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        models.append(doc)
    
    return {"models": models, "total": len(models)}


@router.get("/models/{model_id}", summary="Get model details")
async def get_model(model_id: str):
    """Get model details by ID."""
    from bson import ObjectId
    db = get_database()
    
    doc = await db[Collections.AI_MODELS].find_one({"_id": ObjectId(model_id)})
    if not doc:
        raise HTTPException(404, "Model not found")
    
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/models/{model_id}/activate", summary="Activate a model")
async def activate_model(model_id: str):
    """Set a model as active (deactivates others of same type/zone/parameter)."""
    from bson import ObjectId
    db = get_database()
    
    model_doc = await db[Collections.AI_MODELS].find_one({"_id": ObjectId(model_id)})
    if not model_doc:
        raise HTTPException(404, "Model not found")
    
    # Deactivate others
    await db[Collections.AI_MODELS].update_many(
        {
            "model_type": model_doc["model_type"],
            "zone_id": model_doc["zone_id"],
            "parameter": model_doc["parameter"],
            "_id": {"$ne": ObjectId(model_id)},
        },
        {"$set": {"is_active": False, "deprecated_at": datetime.now(timezone.utc)}}
    )
    
    # Activate this one
    await db[Collections.AI_MODELS].update_one(
        {"_id": ObjectId(model_id)},
        {"$set": {"is_active": True, "activated_at": datetime.now(timezone.utc)}}
    )
    
    # Clear inference cache
    inference = get_inference_service()
    cache_key = f"{model_doc['model_type']}:{model_doc['zone_id']}:{model_doc['parameter']}"
    inference.model_cache.pop(cache_key, None)
    
    return {"message": "Model activated", "model_id": model_id}


# ============================================
# Retraining Scheduler
# ============================================

@router.get("/retraining/jobs", summary="List scheduled retraining jobs")
async def list_retraining_jobs():
    """List all scheduled retraining jobs."""
    scheduler = get_retraining_scheduler()
    jobs = scheduler.get_jobs()
    return {"jobs": jobs}


@router.post("/retraining/jobs", summary="Add scheduled retraining job")
async def add_retraining_job(
    job_id: str = Query(..., min_length=1, max_length=100),
    schedule_type: str = Query("interval", pattern="^(interval|cron)$"),
    hours: int = Query(24, ge=1, le=168),
    hour: int = Query(3, ge=0, le=23),
    minute: int = Query(0, ge=0, le=59),
    model_type: Optional[ModelType] = Query(None),
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    data_source: DataSource = Query(DataSource.MIXED),
    force: bool = Query(False),
):
    """Add a scheduled retraining job."""
    scheduler = get_retraining_scheduler()
    
    if schedule_type == "interval":
        scheduler.add_interval_job(
            job_id=job_id,
            hours=hours,
            model_type=model_type,
            zone_id=zone_id,
            parameter=parameter,
            data_source=data_source,
            force=force,
        )
    else:
        scheduler.add_cron_job(
            job_id=job_id,
            hour=hour,
            minute=minute,
            model_type=model_type,
            zone_id=zone_id,
            parameter=parameter,
            data_source=data_source,
            force=force,
        )
    
    return {"message": "Retraining job added", "job_id": job_id}


@router.delete("/retraining/jobs/{job_id}", summary="Remove scheduled retraining job")
async def remove_retraining_job(job_id: str):
    """Remove a scheduled retraining job."""
    scheduler = get_retraining_scheduler()
    success = scheduler.remove_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Retraining job removed", "job_id": job_id}


@router.post("/retraining/trigger", summary="Manually trigger retraining")
async def trigger_manual_retrain(
    model_type: Optional[ModelType] = Query(None),
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    data_source: DataSource = Query(DataSource.MIXED),
    force: bool = Query(True),
):
    """Manually trigger retraining (for admin use)."""
    scheduler = get_retraining_scheduler()
    result = await scheduler.trigger_manual_retrain(
        model_type=model_type,
        zone_id=zone_id,
        parameter=parameter,
        data_source=data_source,
        force=force,
    )
    return result


# ============================================
# Weekly Report
# ============================================

@router.get("/report/weekly", response_model=WeeklyReportResponse, summary="Get weekly AI report")
async def weekly_report():
    """Get weekly AI analysis report."""
    inference = get_inference_service()
    report = await inference.get_weekly_report()
    return report


# ============================================
# Data Management
# ============================================

@router.post("/data/generate-synthetic", summary="Generate synthetic training data")
async def generate_synthetic_data(
    background_tasks: BackgroundTasks,
    days: int = Query(365, ge=30, le=730),
    sample_rate_minutes: int = Query(10, ge=1, le=60),
    anomaly_ratio: float = Query(0.05, ge=0.01, le=0.2),
):
    """Generate synthetic training data (background task)."""
    background_tasks.add_task(
        _generate_synthetic_data_task,
        days, sample_rate_minutes, anomaly_ratio
    )
    return {"message": "Synthetic data generation started in background"}


async def _generate_synthetic_data_task(days: int, sample_rate: int, anomaly_ratio: float):
    """Background task for synthetic data generation."""
    try:
        config = SyntheticDataConfig(
            days=days,
            sample_rate_minutes=sample_rate,
            anomaly_ratio=anomaly_ratio,
        )
        generator = SyntheticDataGenerator(config)
        samples = generator.generate_all()
        
        # Save to database
        db = get_database()
        if samples:
            await db[Collections.TRAINING_DATA].insert_many(
                [s.model_dump(by_alias=True) for s in samples]
            )
        logger.info("synthetic_data_generated_and_saved", count=len(samples))
    except Exception as e:
        logger.error("synthetic_data_generation_failed", error=str(e))


@router.post("/data/clear-training", summary="Clear training data")
async def clear_training_data(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    synthetic_only: bool = Query(True),
):
    """Clear training data (use with caution)."""
    db = get_database()
    
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    if synthetic_only:
        query["is_synthetic"] = True
    
    result = await db[Collections.TRAINING_DATA].delete_many(query)
    
    return {"deleted_count": result.deleted_count}


# ============================================
# Model Comparison
# ============================================

@router.get("/compare", summary="Compare model performance")
async def compare_models(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
):
    """Compare performance of all trained models."""
    db = get_database()
    
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    
    cursor = db[Collections.MODEL_METADATA].find(query).sort("created_at", -1)
    
    comparison = {}
    async for doc in cursor:
        model_type = doc["model_type"]
        if model_type not in comparison:
            comparison[model_type] = {
                "latest_version": doc["version"],
                "metrics": doc.get("metrics", {}),
                "training_duration": doc.get("training_duration_seconds", 0),
                "data_stats": doc.get("data_stats", {}),
                "created_at": doc["created_at"],
            }
    
    # Add recommendation
    best_model = None
    best_f1 = 0
    for model_type, data in comparison.items():
        f1 = data["metrics"].get("f1", 0)
        if f1 > best_f1:
            best_f1 = f1
            best_model = model_type
    
    return {
        "comparison": comparison,
        "recommended_model": best_model,
        "best_f1": best_f1,
    }


# ============================================
# Prediction History
# ============================================

@router.get("/predictions/history", summary="Get prediction history")
async def get_prediction_history(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    prediction_type: Optional[PredictionType] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get historical predictions with validation status."""
    db = get_database()
    
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    if prediction_type:
        query["prediction_type"] = prediction_type.value
    if start or end:
        query["created_at"] = {}
        if start:
            query["created_at"]["$gte"] = start
        if end:
            query["created_at"]["$lte"] = end
    
    cursor = db[Collections.AI_PREDICTIONS].find(query).sort("created_at", -1).skip(offset).limit(limit)
    predictions = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        predictions.append(doc)
    
    return {"predictions": predictions}


@router.get("/risk/history", summary="Get risk score history")
async def get_risk_history(
    zone_id: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get historical risk scores."""
    db = get_database()
    
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if start or end:
        query["created_at"] = {}
        if start:
            query["created_at"]["$gte"] = start
        if end:
            query["created_at"]["$lte"] = end
    
    cursor = db[Collections.RISK_SCORES].find(query).sort("created_at", -1).skip(offset).limit(limit)
    scores = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        scores.append(doc)
    
    return {"risk_scores": scores}