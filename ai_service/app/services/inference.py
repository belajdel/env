"""
Inference Service
Real-time predictions, anomaly detection, and risk scoring using trained models.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai import (
    ModelType, ModelStatus, PredictionType,
    PredictRequest, PredictResponse, PredictionResult,
    AnomalyRequest, AnomalyResponse, AnomalyResult,
    RiskScoreRequest, RiskScoreResponse, RiskFactors,
    AIModelInDB, AIPredictionInDB, RiskScoreInDB,
    WeeklyReportResponse,
    ZONE_PARAMETER_CONFIGS, PARAMETER_UNITS, PARAMETER_RANGES, DEFAULT_THRESHOLDS
)
from app.core.database import get_database, Collections
from app.services.model_trainer import ModelTrainer

logger = get_logger(__name__)


@dataclass
class LoadedModel:
    """Container for loaded model artifacts."""
    model: Any
    scaler: Any
    metadata: Dict
    model_type: ModelType
    version: str


class InferenceService:
    """
    Handles real-time AI inference:
    - Threshold breach predictions
    - Anomaly detection
    - Zone risk scoring
    """
    
    def __init__(self):
        self.model_cache: Dict[str, LoadedModel] = {}
        self.trainer = ModelTrainer()
        self._cache_lock = asyncio.Lock()
    
    def _get_cache_key(self, model_type: ModelType, zone_id: str, parameter: str) -> str:
        return f"{model_type.value}:{zone_id}:{parameter}"
    
    async def get_active_model(
        self, 
        model_type: ModelType, 
        zone_id: str = "global", 
        parameter: str = "all"
    ) -> Optional[LoadedModel]:
        """Get active model from cache or database."""
        cache_key = self._get_cache_key(model_type, zone_id, parameter)
        
        # Check cache
        if cache_key in self.model_cache:
            return self.model_cache[cache_key]
        
        # Load from database
        db = get_database()
        model_doc = await db[Collections.AI_MODELS].find_one({
            "model_type": model_type.value,
            "zone_id": zone_id,
            "parameter": parameter,
            "is_active": True,
            "status": ModelStatus.READY,
        }, sort=[("activated_at", -1)])
        
        if not model_doc:
            # Try global model
            if zone_id != "global":
                return await self.get_active_model(model_type, "global", parameter)
            return None
        
        # Load model artifacts
        try:
            model, scaler, metadata = self.trainer.load_model(
                model_type, zone_id, parameter, model_doc["version"]
            )
            
            loaded = LoadedModel(
                model=model,
                scaler=scaler,
                metadata=metadata,
                model_type=model_type,
                version=model_doc["version"],
            )
            
            # Cache it
            async with self._cache_lock:
                self.model_cache[cache_key] = loaded
            
            return loaded
            
        except Exception as e:
            logger.error("model_load_failed", model_type=model_type.value, error=str(e))
            return None
    
    async def predict_threshold_breach(
        self, 
        request: PredictRequest
    ) -> Optional[PredictResponse]:
        """Predict threshold breaches for a zone."""
        # Use Isolation Forest as primary prediction model
        model = await self.get_active_model(ModelType.ISOLATION_FOREST, request.zone_id, "all")
        
        if not model:
            logger.warning("no_active_model_for_prediction", zone_id=request.zone_id)
            return None
        
        # Get recent measurements for the zone
        db = get_database()
        recent_measurements = await self._get_recent_measurements(request.zone_id, request.horizon_minutes)
        
        if not recent_measurements:
            logger.warning("no_recent_measurements", zone_id=request.zone_id)
            return None
        
        # Build features for prediction
        features_list = []
        for param in request.parameters or list(recent_measurements.keys()):
            if param not in recent_measurements:
                continue
            
            features = self._build_prediction_features(recent_measurements, param, request.zone_id)
            if features:
                features_list.append((param, features))
        
        if not features_list:
            return None
        
        # Make predictions
        predictions = []
        for param, features in features_list:
            try:
                pred = self._predict_parameter(model, features, param, request.zone_id, request.horizon_minutes)
                if pred:
                    predictions.append(pred)
            except Exception as e:
                logger.error("prediction_failed", parameter=param, error=str(e))
        
        # Save predictions to database
        await self._save_predictions(request.zone_id, predictions, model.model_type, model.version)
        
        return PredictResponse(
            zone_id=request.zone_id,
            horizon_minutes=request.horizon_minutes,
            predictions=predictions,
            model_type=model.model_type,
            model_version=model.version,
        )
    
    def _predict_parameter(
        self,
        loaded_model: LoadedModel,
        features: Dict[str, float],
        parameter: str,
        zone_id: str,
        horizon_minutes: int
    ) -> Optional[PredictionResult]:
        """Predict for a single parameter."""
        model = loaded_model.model
        scaler = loaded_model.scaler
        
        # Prepare feature vector
        feature_names = loaded_model.metadata.get("parameters", [])
        if not feature_names:
            return None
        
        X = np.array([[features.get(f, 0) for f in feature_names]])
        X_scaled = scaler.transform(X)
        
        # Get anomaly score
        if loaded_model.model_type == ModelType.ISOLATION_FOREST:
            score = model.decision_function(X_scaled)[0]
            # Convert to 0-1 (more negative = more anomalous)
            anomaly_score = 1 / (1 + np.exp(score))
        else:
            # For neural models, use reconstruction error
            reconstructed = model.predict(X_scaled, verbose=0)
            mse = np.mean(np.square(X_scaled - reconstructed))
            anomaly_score = min(mse / 10, 1.0)  # Normalize
        
        # Get current value
        current_value = features.get(f"value_{parameter}", 0)
        
        # Predict future value using simple trend extrapolation
        trend = features.get(f"{parameter}_trend_1h", 0)
        predicted_value = current_value + trend * (horizon_minutes / 60)
        
        # Clamp to valid range
        min_val, max_val = PARAMETER_RANGES.get(parameter, (0, 100))
        predicted_value = np.clip(predicted_value, min_val, max_val)
        
        # Determine breach risk
        thresholds = DEFAULT_THRESHOLDS.get(parameter, {})
        breach_risk = "low"
        time_to_breach = None
        
        if "critical_max" in thresholds and predicted_value > thresholds["critical_max"]:
            breach_risk = "critical"
            # Estimate time based on trend
            if trend > 0:
                time_to_breach = f"{(thresholds['critical_max'] - current_value) / trend * 60:.0f} min"
        elif "critical_min" in thresholds and predicted_value < thresholds["critical_min"]:
            breach_risk = "critical"
            if trend < 0:
                time_to_breach = f"{(current_value - thresholds['critical_min']) / abs(trend) * 60:.0f} min"
        elif "warning_max" in thresholds and predicted_value > thresholds["warning_max"]:
            breach_risk = "high"
        elif "warning_min" in thresholds and predicted_value < thresholds["warning_min"]:
            breach_risk = "high"
        elif anomaly_score > 0.7:
            breach_risk = "medium"
        
        # Confidence based on anomaly score and data quality
        confidence = max(0.5, 1 - anomaly_score)
        
        return PredictionResult(
            parameter=parameter,
            predicted_value=round(predicted_value, 2),
            unit=PARAMETER_UNITS.get(parameter, ""),
            confidence=round(confidence, 2),
            breach_risk=breach_risk,
            time_to_breach=time_to_breach,
            current_value=round(current_value, 2),
            threshold_warning=thresholds.get("warning_max") or thresholds.get("warning_min"),
            threshold_critical=thresholds.get("critical_max") or thresholds.get("critical_min"),
        )
    
    async def detect_anomalies(
        self, 
        request: AnomalyRequest
    ) -> Optional[AnomalyResponse]:
        """Detect anomalies in current measurements."""
        # Use Isolation Forest for anomaly detection
        loaded_model = await self.get_active_model(ModelType.ISOLATION_FOREST, request.zone_id, "all")
        
        if not loaded_model:
            return None
        
        # Build features from measurements
        features = self._build_features_from_measurements(request.measurements, request.zone_id)
        
        # Prepare feature vector
        feature_names = loaded_model.metadata.get("parameters", [])
        if not feature_names:
            return None
        
        X = np.array([[features.get(f, 0) for f in feature_names]])
        X_scaled = loaded_model.scaler.transform(X)
        
        # Get anomaly scores per parameter (using individual parameter models would be better)
        # For now, use overall anomaly score
        if loaded_model.model_type == ModelType.ISOLATION_FOREST:
            overall_score = loaded_model.model.decision_function(X_scaled)[0]
            anomaly_score = 1 / (1 + np.exp(overall_score))
        else:
            reconstructed = loaded_model.model.predict(X_scaled, verbose=0)
            mse = np.mean(np.square(X_scaled - reconstructed))
            anomaly_score = min(mse / 10, 1.0)
        
        # Per-parameter anomaly detection (simplified)
        anomalies = []
        for param, value in request.measurements.items():
            param_score = self._calculate_param_anomaly_score(param, value, request.zone_id)
            is_anomaly = param_score > 0.7
            
            thresholds = DEFAULT_THRESHOLDS.get(param, {})
            expected_range = None
            if "warning_min" in thresholds and "warning_max" in thresholds:
                expected_range = [thresholds["warning_min"], thresholds["warning_max"]]
            
            anomalies.append(AnomalyResult(
                parameter=param,
                value=value,
                anomaly_score=round(param_score, 3),
                is_anomaly=is_anomaly,
                expected_range=expected_range,
                contribution=param_score if is_anomaly else None,
            ))
        
        overall = max([a.anomaly_score for a in anomalies]) if anomalies else 0
        
        return AnomalyResponse(
            zone_id=request.zone_id,
            timestamp=request.timestamp,
            anomalies=anomalies,
            overall_anomaly_score=round(overall, 3),
            model_type=loaded_model.model_type,
            model_version=loaded_model.version,
        )
    
    def _calculate_param_anomaly_score(self, param: str, value: float, zone_id: str) -> float:
        """Calculate anomaly score for a single parameter."""
        # Simple threshold-based scoring
        thresholds = DEFAULT_THRESHOLDS.get(param, {})
        min_val, max_val = PARAMETER_RANGES.get(param, (0, 100))
        
        score = 0.0
        
        # Critical threshold breach
        if "critical_max" in thresholds and value > thresholds["critical_max"]:
            score = 1.0
        elif "critical_min" in thresholds and value < thresholds["critical_min"]:
            score = 1.0
        # Warning threshold breach
        elif "warning_max" in thresholds and value > thresholds["warning_max"]:
            score = 0.8
        elif "warning_min" in thresholds and value < thresholds["warning_min"]:
            score = 0.8
        # Proximity to thresholds
        elif "warning_max" in thresholds:
            proximity = (value - thresholds["warning_max"]) / (thresholds.get("critical_max", thresholds["warning_max"]) - thresholds["warning_max"])
            score = max(0, min(0.7, proximity))
        elif "warning_min" in thresholds:
            proximity = (thresholds["warning_min"] - value) / (thresholds["warning_min"] - thresholds.get("critical_min", thresholds["warning_min"]))
            score = max(0, min(0.7, proximity))
        # Statistical anomaly (simplified)
        else:
            # Normalize to 0-1 range
            normalized = (value - min_val) / (max_val - min_val) if max_val > min_val else 0.5
            # Anomaly if far from center
            score = 2 * abs(normalized - 0.5)
        
        return min(1.0, max(0.0, score))
    
    async def calculate_risk_score(
        self, 
        request: RiskScoreRequest
    ) -> Optional[RiskScoreResponse]:
        """Calculate dynamic risk score for a zone."""
        zone_id = request.zone_id
        db = get_database()
        
        # Get recent data
        recent = await self._get_recent_measurements(zone_id, 24 * 60)  # 24 hours
        if not recent:
            return None
        
        # Get active alerts
        alerts_cursor = db[Collections.ALERTS].find({
            "zone_id": zone_id,
            "status": {"$in": ["open", "acknowledged"]},
            "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=24)}
        })
        active_alerts = await alerts_cursor.to_list(100)
        
        # Calculate factors
        factors = RiskFactors()
        
        # 1. Parameter anomalies
        for param, measurements in recent.items():
            if measurements:
                latest = measurements[-1]
                anomaly_score = self._calculate_param_anomaly_score(param, latest["value"], zone_id)
                factors.parameter_anomalies[param] = round(anomaly_score, 3)
        
        # 2. Threshold proximity
        for param, measurements in recent.items():
            if measurements:
                latest = measurements[-1]
                thresholds = DEFAULT_THRESHOLDS.get(param, {})
                value = latest["value"]
                
                proximity = 0.0
                if "critical_max" in thresholds and value > thresholds["warning_max"]:
                    proximity = min(1.0, (value - thresholds["warning_max"]) / 
                                   (thresholds["critical_max"] - thresholds["warning_max"]))
                elif "critical_min" in thresholds and value < thresholds["warning_min"]:
                    proximity = min(1.0, (thresholds["warning_min"] - value) / 
                                   (thresholds["warning_min"] - thresholds["critical_min"]))
                factors.threshold_proximity[param] = round(proximity, 3)
        
        # 3. Trend direction
        for param, measurements in recent.items():
            if len(measurements) >= 6:  # 1 hour
                values = [m["value"] for m in measurements[-6:]]
                trend = np.polyfit(range(len(values)), values, 1)[0]
                if trend > 0.1:
                    factors.trend_direction[param] = "increasing"
                elif trend < -0.1:
                    factors.trend_direction[param] = "decreasing"
                else:
                    factors.trend_direction[param] = "stable"
        
        # 4. Historical alert frequency
        alert_count = len(active_alerts)
        factors.historical_alert_frequency = round(alert_count / 24, 2)  # per hour
        
        # 5. AI prediction confidence (if available)
        # This would come from recent predictions
        factors.ai_prediction_confidence = 0.8  # Placeholder
        
        # Calculate overall risk score (0-100)
        score = self._calculate_overall_risk(factors, alert_count)
        level = self._score_to_level(score)
        
        # Get active model info
        model = await self.get_active_model(ModelType.ISOLATION_FOREST, zone_id, "all")
        model_type = model.model_type if model else ModelType.ISOLATION_FOREST
        model_version = model.version if model else "unknown"
        
        # Save risk score
        risk_doc = RiskScoreInDB(
            zone_id=zone_id,
            score=score,
            level=level,
            factors=factors.model_dump(),
            model_type=model_type,
            model_version=model_version,
        )
        await db[Collections.RISK_SCORES].insert_one(risk_doc.model_dump(by_alias=True))
        
        return RiskScoreResponse(
            zone_id=zone_id,
            score=score,
            level=level,
            factors=factors,
            model_type=model_type,
            model_version=model_version,
        )
    
    def _calculate_overall_risk(self, factors: RiskFactors, alert_count: int) -> int:
        """Calculate overall risk score from factors."""
        score = 0
        
        # Parameter anomalies (max 40 points)
        if factors.parameter_anomalies:
            max_anomaly = max(factors.parameter_anomalies.values())
            score += int(max_anomaly * 40)
        
        # Threshold proximity (max 30 points)
        if factors.threshold_proximity:
            max_proximity = max(factors.threshold_proximity.values())
            score += int(max_proximity * 30)
        
        # Trend direction (max 15 points)
        increasing_count = sum(1 for v in factors.trend_direction.values() if v == "increasing")
        if increasing_count > 0:
            score += min(15, increasing_count * 5)
        
        # Alert frequency (max 10 points)
        score += min(10, int(factors.historical_alert_frequency * 2))
        
        # AI confidence (max 5 points) - lower confidence = higher risk
        if factors.ai_prediction_confidence:
            score += int((1 - factors.ai_prediction_confidence) * 5)
        
        return min(100, score)
    
    def _score_to_level(self, score: int) -> str:
        """Convert numeric score to risk level."""
        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 30:
            return "medium"
        else:
            return "low"
    
    async def _get_recent_measurements(
        self, 
        zone_id: str, 
        minutes: int
    ) -> Dict[str, List[Dict]]:
        """Get recent measurements grouped by parameter."""
        db = get_database()
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        
        cursor = db[Collections.MEASUREMENTS].find({
            "metadata.zone_id": zone_id,
            "timestamp": {"$gte": since},
        }).sort("timestamp", 1)
        
        measurements = {}
        async for doc in cursor:
            param = doc["metadata"]["parameter"]
            if param not in measurements:
                measurements[param] = []
            measurements[param].append({
                "value": doc["value"],
                "timestamp": doc["timestamp"],
                "unit": doc["unit"],
            })
        
        return measurements
    
    def _build_prediction_features(
        self, 
        measurements: Dict[str, List[Dict]], 
        target_param: str, 
        zone_id: str
    ) -> Optional[Dict[str, float]]:
        """Build feature vector for prediction."""
        features = {}
        
        # Current values for all parameters
        for param, ms in measurements.items():
            if ms:
                features[f"value_{param}"] = ms[-1]["value"]
        
        # Rolling statistics for target parameter
        target_ms = measurements.get(target_param, [])
        if len(target_ms) >= 6:
            values = [m["value"] for m in target_ms[-6:]]
            features[f"{target_param}_mean_1h"] = np.mean(values)
            features[f"{target_param}_std_1h"] = np.std(values)
            features[f"{target_param}_min_1h"] = np.min(values)
            features[f"{target_param}_max_1h"] = np.max(values)
            features[f"{target_param}_trend_1h"] = values[-1] - values[0] if len(values) > 1 else 0
        
        # Time features
        now = datetime.now(timezone.utc)
        features["hour_of_day"] = now.hour + now.minute / 60
        features["day_of_week"] = now.weekday()
        features["is_weekend"] = 1 if now.weekday() >= 5 else 0
        features["hour_sin"] = np.sin(2 * np.pi * features["hour_of_day"] / 24)
        features["hour_cos"] = np.cos(2 * np.pi * features["hour_of_day"] / 24)
        features["doy_sin"] = np.sin(2 * np.pi * now.timetuple().tm_yday / 365)
        features["doy_cos"] = np.cos(2 * np.pi * now.timetuple().tm_yday / 365)
        
        # Threshold proximity
        thresholds = DEFAULT_THRESHOLDS.get(target_param, {})
        if target_ms:
            current = target_ms[-1]["value"]
            if "warning_max" in thresholds:
                features["proximity_warning_max"] = (current - thresholds["warning_max"]) / \
                    (thresholds.get("critical_max", thresholds["warning_max"]) - thresholds["warning_max"])
            if "warning_min" in thresholds:
                features["proximity_warning_min"] = (thresholds["warning_min"] - current) / \
                    (thresholds["warning_min"] - thresholds.get("critical_min", thresholds["warning_min"]))
        
        # Cross-parameter features
        for param in ["temperature", "humidity", "pm25", "pm10"]:
            if param != target_param and param in measurements and measurements[param]:
                features[f"cross_{param}"] = measurements[param][-1]["value"]
        
        return features if features else None
    
    def _build_features_from_measurements(
        self, 
        measurements: Dict[str, float], 
        zone_id: str
    ) -> Dict[str, float]:
        """Build feature vector from current measurements."""
        features = {}
        
        # Current values
        for param, value in measurements.items():
            features[f"value_{param}"] = value
        
        # Time features
        now = datetime.now(timezone.utc)
        features["hour_of_day"] = now.hour + now.minute / 60
        features["day_of_week"] = now.weekday()
        features["is_weekend"] = 1 if now.weekday() >= 5 else 0
        features["hour_sin"] = np.sin(2 * np.pi * features["hour_of_day"] / 24)
        features["hour_cos"] = np.cos(2 * np.pi * features["hour_of_day"] / 24)
        features["doy_sin"] = np.sin(2 * np.pi * now.timetuple().tm_yday / 365)
        features["doy_cos"] = np.cos(2 * np.pi * now.timetuple().tm_yday / 365)
        
        return features
    
    async def _save_predictions(
        self, 
        zone_id: str, 
        predictions: List[PredictionResult], 
        model_type: ModelType, 
        model_version: str
    ) -> None:
        """Save predictions to database."""
        db = get_database()
        now = datetime.now(timezone.utc)
        
        docs = []
        for pred in predictions:
            doc = AIPredictionInDB(
                zone_id=zone_id,
                parameter=pred.parameter,
                prediction_type=PredictionType.THRESHOLD_BREACH,
                horizon_minutes=60,  # Default
                predicted_value=pred.predicted_value,
                confidence=pred.confidence,
                breach_risk=pred.breach_risk,
                time_to_breach=pred.time_to_breach,
                current_value=pred.current_value,
                model_type=model_type,
                model_version=model_version,
            )
            docs.append(doc.model_dump(by_alias=True))
        
        if docs:
            await db[Collections.AI_PREDICTIONS].insert_many(docs)
    
    async def get_weekly_report(self) -> Dict[str, Any]:
        """Generate weekly AI analysis report."""
        db = get_database()
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        
        # Get data for the week
        zones_data = {}
        all_predictions = []
        all_risk_scores = []
        
        for zone_id in ZONE_PARAMETER_CONFIGS.keys():
            # Predictions
            pred_cursor = db[Collections.AI_PREDICTIONS].find({
                "zone_id": zone_id,
                "created_at": {"$gte": week_start},
            })
            predictions = await pred_cursor.to_list(1000)
            all_predictions.extend(predictions)
            
            # Risk scores
            risk_cursor = db[Collections.RISK_SCORES].find({
                "zone_id": zone_id,
                "created_at": {"$gte": week_start},
            })
            risk_scores = await risk_cursor.to_list(1000)
            all_risk_scores.extend(risk_scores)
            
            # Summarize zone
            zones_data[zone_id] = {
                "predictions_count": len(predictions),
                "avg_confidence": np.mean([p.get("confidence", 0) for p in predictions]) if predictions else 0,
                "breach_risk_distribution": self._count_risk_levels(predictions),
                "avg_risk_score": np.mean([r.get("score", 0) for r in risk_scores]) if risk_scores else 0,
                "max_risk_score": max([r.get("score", 0) for r in risk_scores]) if risk_scores else 0,
                "risk_level_distribution": self._count_risk_levels_risk(risk_scores),
            }
        
        # Model performance
        model_performance = await self._get_model_performance()
        
        # Recommendations
        recommendations = self._generate_recommendations(zones_data, all_predictions, all_risk_scores)
        
        return WeeklyReportResponse(
            week_start=week_start,
            week_end=now,
            zones=zones_data,
            summary={
                "total_predictions": len(all_predictions),
                "total_zones_monitored": len(zones_data),
                "critical_alerts_predicted": sum(1 for p in all_predictions if p.get("breach_risk") == "critical"),
                "zones_at_high_risk": sum(1 for z in zones_data.values() if z.get("avg_risk_score", 0) > 60),
            },
            model_performance=model_performance,
            recommendations=recommendations,
        ).model_dump()
    
    def _count_risk_levels(self, predictions: List[Dict]) -> Dict[str, int]:
        counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for p in predictions:
            risk = p.get("breach_risk", "low")
            if risk in counts:
                counts[risk] += 1
        return counts
    
    def _count_risk_levels_risk(self, risk_scores: List[Dict]) -> Dict[str, int]:
        counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for r in risk_scores:
            level = r.get("level", "low")
            if level in counts:
                counts[level] += 1
        return counts
    
    async def _get_model_performance(self) -> Dict[str, Dict[str, float]]:
        """Get model performance metrics from metadata."""
        db = get_database()
        cursor = db[Collections.MODEL_METADATA].find().sort("created_at", -1).limit(10)
        
        performance = {}
        async for doc in cursor:
            model_type = doc["model_type"]
            if model_type not in performance:
                performance[model_type] = doc.get("metrics", {})
        return performance
    
    def _generate_recommendations(
        self, 
        zones_data: Dict, 
        predictions: List, 
        risk_scores: List
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # High risk zones
        high_risk_zones = [z for z, d in zones_data.items() if d.get("avg_risk_score", 0) > 60]
        if high_risk_zones:
            recommendations.append(f"Zones at elevated risk: {', '.join(high_risk_zones)}. Increase monitoring frequency.")
        
        # Critical predictions
        critical_preds = sum(1 for p in predictions if p.get("breach_risk") == "critical")
        if critical_preds > 0:
            recommendations.append(f"{critical_preds} critical threshold breaches predicted. Review alert rules and prepare response plans.")
        
        # Model performance
        # Would add model-specific recommendations here
        
        if not recommendations:
            recommendations.append("All zones operating within normal parameters. Continue routine monitoring.")
        
        return recommendations


# Global instance
_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Get singleton InferenceService instance."""
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service