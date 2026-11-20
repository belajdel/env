"""
Measurements API Routes
Historical data queries with aggregation support.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.models.measurement import (
    MeasurementPublic, MeasurementQuery, MeasurementAggregate, 
    MeasurementStats, VALID_PARAMETERS
)
from app.core.logging import get_logger

router = APIRouter(prefix="/measurements", tags=["measurements"])

logger = get_logger(__name__)


@router.get("", response_model=List[MeasurementPublic], summary="Get measurement history")
async def get_measurements(
    zone_id: str = Query(..., description="Zone ID"),
    parameter: str = Query(..., description="Parameter name"),
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
    aggregate: bool = Query(False, description="Return 1-minute aggregates"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),  # Placeholder for auth
):
    """Get historical measurements for a zone/parameter."""
    # Validate parameter
    if parameter not in VALID_PARAMETERS:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {parameter}")
    
    # Validate time range
    if start >= end:
        raise HTTPException(status_code=400, detail="Start must be before end")
    
    if end - start > timedelta(days=365):
        raise HTTPException(status_code=400, detail="Time range too large (max 365 days)")
    
    # Check zone access (placeholder)
    # rbac.check_permission(token_data.role, Permission.MEASUREMENT_READ, zone_id)
    
    collection = Collections.MEASUREMENTS_1MIN if aggregate else Collections.MEASUREMENTS
    
    cursor = db[collection].find({
        "metadata.zone_id": zone_id,
        "metadata.parameter": parameter,
        "timestamp": {"$gte": start, "$lte": end},
    }).sort("timestamp", 1).skip(offset).limit(limit)
    
    measurements = []
    async for doc in cursor:
        # Convert to public model
        from app.models.measurement import MeasurementInDB
        m = MeasurementInDB(**doc)
        measurements.append(MeasurementPublic.from_db(m))
    
    return measurements


@router.get("/stats", response_model=MeasurementStats, summary="Get measurement statistics")
async def get_measurement_stats(
    zone_id: str = Query(..., description="Zone ID"),
    parameter: str = Query(..., description="Parameter name"),
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get statistical summary of measurements."""
    if parameter not in VALID_PARAMETERS:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {parameter}")
    
    if start >= end:
        raise HTTPException(status_code=400, detail="Start must be before end")
    
    # Use aggregation pipeline for percentiles
    pipeline = [
        {"$match": {
            "metadata.zone_id": zone_id,
            "metadata.parameter": parameter,
            "timestamp": {"$gte": start, "$lte": end},
        }},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "min": {"$min": "$value"},
            "max": {"$max": "$value"},
            "avg": {"$avg": "$value"},
            "std": {"$stdDevPop": "$value"},
            "values": {"$push": "$value"},
            "unit": {"$first": "$unit"},
        }},
    ]
    
    result = await db[Collections.MEASUREMENTS].aggregate(pipeline).to_list(1)
    
    if not result or result[0]["count"] == 0:
        raise HTTPException(status_code=404, detail="No data found for the given range")
    
    data = result[0]
    values = sorted(data["values"])
    
    def percentile(p: float) -> float:
        if not values:
            return 0.0
        k = (len(values) - 1) * p
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if f == c:
            return values[f]
        return values[f] + (k - f) * (values[c] - values[f])
    
    return MeasurementStats(
        zone_id=zone_id,
        parameter=parameter,
        unit=data["unit"],
        count=data["count"],
        min=data["min"],
        max=data["max"],
        avg=data["avg"],
        std=data.get("std", 0.0),
        percentile_25=percentile(0.25),
        percentile_50=percentile(0.50),
        percentile_75=percentile(0.75),
        percentile_95=percentile(0.95),
        percentile_99=percentile(0.99),
        start=start,
        end=end,
    )


@router.get("/latest", response_model=List[MeasurementPublic], summary="Get latest measurements for all parameters in a zone")
async def get_latest_measurements(
    zone_id: str = Query(..., description="Zone ID"),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get latest measurement for each parameter in a zone."""
    # rbac.check_permission(token_data.role, Permission.MEASUREMENT_READ, zone_id)
    
    # Aggregate to get latest per parameter
    pipeline = [
        {"$match": {"metadata.zone_id": zone_id}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$metadata.parameter",
            "doc": {"$first": "$$ROOT"},
        }},
    ]
    
    results = await db[Collections.MEASUREMENTS].aggregate(pipeline).to_list(100)
    
    measurements = []
    for item in results:
        from app.models.measurement import MeasurementInDB
        m = MeasurementInDB(**item["doc"])
        measurements.append(MeasurementPublic.from_db(m))
    
    return measurements


@router.get("/aggregates", response_model=List[MeasurementAggregate], summary="Get 1-minute aggregates")
async def get_aggregates(
    zone_id: str = Query(..., description="Zone ID"),
    parameter: str = Query(..., description="Parameter name"),
    start: datetime = Query(..., description="Start timestamp (ISO 8601)"),
    end: datetime = Query(..., description="End timestamp (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get pre-computed 1-minute aggregates."""
    if parameter not in VALID_PARAMETERS:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {parameter}")
    
    if start >= end:
        raise HTTPException(status_code=400, detail="Start must be before end")
    
    cursor = db[Collections.MEASUREMENTS_1MIN].find({
        "metadata.zone_id": zone_id,
        "metadata.parameter": parameter,
        "timestamp": {"$gte": start, "$lte": end},
    }).sort("timestamp", 1).skip(offset).limit(limit)
    
    aggregates = []
    async for doc in cursor:
        aggregates.append(MeasurementAggregate(
            zone_id=doc["metadata"]["zone_id"],
            parameter=doc["metadata"]["parameter"],
            unit=doc["unit"],
            count=doc["count"],
            min=doc["min"],
            max=doc["max"],
            avg=doc["avg"],
            std=doc.get("std"),
            timestamp=doc["timestamp"],
        ))
    
    return aggregates