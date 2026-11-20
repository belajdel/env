"""
Model Training Service
Trains and evaluates Isolation Forest, Autoencoder, and LSTM models for anomaly detection.
"""

import os
import json
import joblib
import warnings
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, classification_report
)
from scipy import stats

# TensorFlow/Keras for LSTM and Autoencoder
try:
    import tensorflow as tf
    from tensorflow.keras import layers, models, callbacks, optimizers
    from tensorflow.keras.models import Model, load_model
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai import (
    ModelType, ModelStatus, DataSource, ModelType, 
    AIModelInDB, ModelMetadataInDB, TrainingDataInDB,
    ZONE_PARAMETER_CONFIGS, PARAMETER_RANGES
)
from app.core.database import get_database, Collections

logger = get_logger(__name__)

warnings.filterwarnings("ignore", category=UserWarning)


@dataclass
class TrainingResult:
    """Result of model training."""
    model_type: ModelType
    model: Any
    scaler: Any
    metrics: Dict[str, float]
    feature_importance: Optional[Dict[str, float]]
    training_duration: float
    version: str


class ModelTrainer:
    """
    Trains and compares multiple anomaly detection models.
    
    Models:
    1. Isolation Forest - tree-based, good for multivariate anomalies
    2. Autoencoder - neural network, learns compressed representations
    3. LSTM - recurrent network, captures temporal patterns
    """
    
    def __init__(self, model_dir: str = None):
        self.model_dir = Path(model_dir or settings.MODEL_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.random_state = settings.RANDOM_STATE
        
    def prepare_data(
        self, 
        zone_id: str = None, 
        parameter: str = None,
        data_source: DataSource = DataSource.MIXED,
        limit: int = None
    ) -> Tuple[np.ndarray, np.ndarray, List[str], pd.DataFrame]:
        """Load and prepare training data from MongoDB."""
        db = get_database()
        
        # Build query
        query = {"is_synthetic": data_source == DataSource.SYNTHETIC}
        if data_source == DataSource.MIXED:
            query = {}
        elif data_source == DataSource.REAL:
            query = {"is_synthetic": False}
            
        if zone_id:
            query["zone_id"] = zone_id
        if parameter:
            query["parameter"] = parameter
        
        # Fetch data
        cursor = db[Collections.TRAINING_DATA].find(query).sort("timestamp", 1)
        if limit:
            cursor = cursor.limit(limit)
        
        docs = list(cursor)
        if not docs:
            raise ValueError(f"No training data found for query: {query}")
        
        df = pd.DataFrame(docs)
        logger.info("training_data_loaded", rows=len(df), zones=df['zone_id'].nunique(), parameters=df['parameter'].nunique())
        
        # Extract features and labels
        feature_cols = [c for c in df.columns if c not in [
            '_id', 'zone_id', 'parameter', 'timestamp', 'label', 'is_synthetic', 'created_at'
        ]]
        
        X = df[feature_cols].values
        y = df['label'].values
        
        # Handle missing values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        return X, y, feature_cols, df
    
    def train_isolation_forest(
        self, 
        X: np.ndarray, 
        y: np.ndarray,
        contamination: float = 0.05
    ) -> TrainingResult:
        """Train Isolation Forest model."""
        start_time = datetime.now(timezone.utc)
        
        # Scale features
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Train model
        model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples='auto',
            random_state=self.random_state,
            n_jobs=-1,
            verbose=0,
        )
        
        # Fit on normal data only (semi-supervised)
        X_normal = X_scaled[y == 0]
        if len(X_normal) < 100:
            X_normal = X_scaled  # Fallback to all data
            
        model.fit(X_normal)
        
        # Predict on all data
        y_pred = model.predict(X_scaled)
        y_pred_binary = (y_pred == -1).astype(int)  # -1 = anomaly
        
        # Calculate metrics
        metrics = self._calculate_metrics(y, y_pred_binary, model.decision_function(X_scaled))
        
        # Feature importance (using permutation importance approximation)
        feature_importance = self._get_if_feature_importance(model, X_scaled, feature_cols=None)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        version = self._generate_version(ModelType.ISOLATION_FOREST)
        
        return TrainingResult(
            model_type=ModelType.ISOLATION_FOREST,
            model=model,
            scaler=scaler,
            metrics=metrics,
            feature_importance=feature_importance,
            training_duration=duration,
            version=version,
        )
    
    def _get_if_feature_importance(
        self, 
        model: IsolationForest, 
        X: np.ndarray,
        feature_cols: List[str] = None
    ) -> Dict[str, float]:
        """Approximate feature importance for Isolation Forest."""
        # Use mean depth as proxy for importance
        n_features = X.shape[1]
        importances = np.zeros(n_features)
        
        for estimator in model.estimators_:
            # Get feature split counts
            tree = estimator.tree_
            for i in range(tree.node_count):
                if tree.feature[i] >= 0:
                    importances[tree.feature[i]] += 1
        
        importances = importances / importances.sum() if importances.sum() > 0 else np.ones(n_features) / n_features
        
        if feature_cols:
            return dict(zip(feature_cols, importances.tolist()))
        return {f"feature_{i}": float(v) for i, v in enumerate(importances)}
    
    def train_autoencoder(
        self, 
        X: np.ndarray, 
        y: np.ndarray,
        encoding_dim: int = None,
        epochs: int = 50,
        batch_size: int = 256
    ) -> TrainingResult:
        """Train Autoencoder for anomaly detection."""
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow not available. Cannot train Autoencoder.")
        
        start_time = datetime.now(timezone.utc)
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Use only normal data for training
        X_normal = X_scaled[y == 0]
        if len(X_normal) < 100:
            X_normal = X_scaled
        
        input_dim = X_scaled.shape[1]
        if encoding_dim is None:
            encoding_dim = max(input_dim // 4, 8)
        
        # Build autoencoder
        input_layer = layers.Input(shape=(input_dim,))
        
        # Encoder
        encoded = layers.Dense(input_dim // 2, activation='relu')(input_layer)
        encoded = layers.Dropout(0.2)(encoded)
        encoded = layers.Dense(encoding_dim, activation='relu')(encoded)
        
        # Decoder
        decoded = layers.Dense(input_dim // 2, activation='relu')(encoded)
        decoded = layers.Dropout(0.2)(decoded)
        decoded = layers.Dense(input_dim, activation='linear')(decoded)
        
        autoencoder = Model(input_layer, decoded)
        encoder = Model(input_layer, encoded)
        
        autoencoder.compile(
            optimizer=optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        # Callbacks
        early_stop = callbacks.EarlyStopping(
            monitor='val_loss', patience=10, restore_best_weights=True
        )
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor='val_loss', factor=0.5, patience=5, min_lr=1e-6
        )
        
        # Train
        history = autoencoder.fit(
            X_normal, X_normal,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.2,
            callbacks=[early_stop, reduce_lr],
            verbose=0,
            shuffle=True,
        )
        
        # Calculate reconstruction errors
        X_reconstructed = autoencoder.predict(X_scaled, verbose=0)
        mse = np.mean(np.square(X_scaled - X_reconstructed), axis=1)
        
        # Determine threshold (95th percentile of normal data)
        normal_mse = mse[y == 0]
        threshold = np.percentile(normal_mse, 95) if len(normal_mse) > 0 else np.percentile(mse, 95)
        
        # Predict anomalies
        y_pred = (mse > threshold).astype(int)
        
        # Calculate metrics
        metrics = self._calculate_metrics(y, y_pred, -mse)  # Negative MSE as "score"
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        version = self._generate_version(ModelType.AUTOENCODER)
        
        # Store threshold in model for later use
        autoencoder.threshold = threshold
        autoencoder.encoder = encoder
        
        return TrainingResult(
            model_type=ModelType.AUTOENCODER,
            model=autoencoder,
            scaler=scaler,
            metrics=metrics,
            feature_importance=None,  # Not directly available for AE
            training_duration=duration,
            version=version,
        )
    
    def train_lstm(
        self, 
        X: np.ndarray, 
        y: np.ndarray,
        sequence_length: int = 24,  # 4 hours at 10-min intervals
        epochs: int = 30,
        batch_size: int = 128
    ) -> TrainingResult:
        """Train LSTM for sequence-based anomaly detection."""
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow not available. Cannot train LSTM.")
        
        start_time = datetime.now(timezone.utc)
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Create sequences
        X_seq, y_seq = self._create_sequences(X_scaled, y, sequence_length)
        
        if len(X_seq) < 100:
            raise ValueError(f"Not enough sequences for LSTM training: {len(X_seq)}")
        
        # Use only normal sequences for training
        normal_mask = y_seq == 0
        X_normal = X_seq[normal_mask]
        if len(X_normal) < 50:
            X_normal = X_seq
        
        input_shape = (sequence_length, X_scaled.shape[1])
        
        # Build LSTM autoencoder
        inputs = layers.Input(shape=input_shape)
        
        # Encoder
        encoded = layers.LSTM(64, return_sequences=True)(inputs)
        encoded = layers.Dropout(0.2)(encoded)
        encoded = layers.LSTM(32, return_sequences=False)(encoded)
        
        # Decoder
        decoded = layers.RepeatVector(sequence_length)(encoded)
        decoded = layers.LSTM(32, return_sequences=True)(decoded)
        decoded = layers.Dropout(0.2)(decoded)
        decoded = layers.LSTM(64, return_sequences=True)(decoded)
        decoded = layers.TimeDistributed(layers.Dense(X_scaled.shape[1]))(decoded)
        
        model = Model(inputs, decoded)
        
        model.compile(
            optimizer=optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        # Callbacks
        early_stop = callbacks.EarlyStopping(
            monitor='val_loss', patience=8, restore_best_weights=True
        )
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor='val_loss', factor=0.5, patience=4, min_lr=1e-6
        )
        
        # Train
        history = model.fit(
            X_normal, X_normal,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.2,
            callbacks=[early_stop, reduce_lr],
            verbose=0,
            shuffle=True,
        )
        
        # Calculate reconstruction errors on all sequences
        X_reconstructed = model.predict(X_seq, verbose=0)
        mse = np.mean(np.square(X_seq - X_reconstructed), axis=(1, 2))
        
        # Determine threshold
        normal_mse = mse[y_seq == 0]
        threshold = np.percentile(normal_mse, 95) if len(normal_mse) > 0 else np.percentile(mse, 95)
        
        # Predict
        y_pred = (mse > threshold).astype(int)
        
        # Calculate metrics
        metrics = self._calculate_metrics(y_seq, y_pred, -mse)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        version = self._generate_version(ModelType.LSTM)
        
        model.threshold = threshold
        
        return TrainingResult(
            model_type=ModelType.LSTM,
            model=model,
            scaler=scaler,
            metrics=metrics,
            feature_importance=None,
            training_duration=duration,
            version=version,
        )
    
    def _create_sequences(
        self, 
        X: np.ndarray, 
        y: np.ndarray, 
        sequence_length: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create sliding window sequences."""
        n_samples = len(X) - sequence_length + 1
        if n_samples <= 0:
            return np.array([]), np.array([])
        
        X_seq = np.zeros((n_samples, sequence_length, X.shape[1]))
        y_seq = np.zeros(n_samples)
        
        for i in range(n_samples):
            X_seq[i] = X[i:i+sequence_length]
            # Label is 1 if any sample in sequence is anomaly
            y_seq[i] = 1 if np.any(y[i:i+sequence_length] == 1) else 0
        
        return X_seq, y_seq
    
    def _calculate_metrics(
        self, 
        y_true: np.ndarray, 
        y_pred: np.ndarray, 
        scores: np.ndarray
    ) -> Dict[str, float]:
        """Calculate evaluation metrics."""
        metrics = {}
        
        # Basic metrics
        metrics['precision'] = float(precision_score(y_true, y_pred, zero_division=0))
        metrics['recall'] = float(recall_score(y_true, y_pred, zero_division=0))
        metrics['f1'] = float(f1_score(y_true, y_pred, zero_division=0))
        
        # ROC AUC (if scores available)
        try:
            if len(np.unique(y_true)) > 1:
                metrics['roc_auc'] = float(roc_auc_score(y_true, -scores))  # Negative because lower score = more anomalous
            else:
                metrics['roc_auc'] = 0.5
        except Exception:
            metrics['roc_auc'] = 0.5
        
        # Confusion matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        metrics['true_negatives'] = int(tn)
        metrics['false_positives'] = int(fp)
        metrics['false_negatives'] = int(fn)
        metrics['true_positives'] = int(tp)
        
        # Rates
        metrics['false_positive_rate'] = float(fp / (fp + tn)) if (fp + tn) > 0 else 0
        metrics['false_negative_rate'] = float(fn / (fn + tp)) if (fn + tp) > 0 else 0
        
        return metrics
    
    def _generate_version(self, model_type: ModelType) -> str:
        """Generate model version string."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{model_type.value}_v{timestamp}"
    
    def save_model(self, result: TrainingResult, zone_id: str = "global", parameter: str = "all") -> str:
        """Save model artifacts to disk."""
        model_path = self.model_dir / f"{result.model_type.value}_{zone_id}_{parameter}_{result.version}"
        model_path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        if result.model_type == ModelType.ISOLATION_FOREST:
            joblib.dump(result.model, model_path / "model.joblib")
        elif result.model_type in [ModelType.AUTOENCODER, ModelType.LSTM]:
            result.model.save(model_path / "model.keras")
        
        # Save scaler
        joblib.dump(result.scaler, model_path / "scaler.joblib")
        
        # Save metadata
        metadata = {
            "model_type": result.model_type.value,
            "version": result.version,
            "zone_id": zone_id,
            "parameter": parameter,
            "metrics": result.metrics,
            "feature_importance": result.feature_importance,
            "training_duration": result.training_duration,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        with open(model_path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info("model_saved", path=str(model_path), model_type=result.model_type.value)
        return str(model_path)
    
    def load_model(self, model_type: ModelType, zone_id: str = "global", parameter: str = "all", version: str = None) -> Tuple[Any, Any, Dict]:
        """Load model artifacts from disk."""
        if version:
            model_path = self.model_dir / f"{model_type.value}_{zone_id}_{parameter}_{version}"
        else:
            # Find latest version
            pattern = f"{model_type.value}_{zone_id}_{parameter}_*"
            matches = list(self.model_dir.glob(pattern))
            if not matches:
                raise FileNotFoundError(f"No model found for {model_type.value} {zone_id} {parameter}")
            model_path = max(matches, key=lambda p: p.stat().st_mtime)
        
        # Load model
        if model_type == ModelType.ISOLATION_FOREST:
            model = joblib.load(model_path / "model.joblib")
        elif model_type in [ModelType.AUTOENCODER, ModelType.LSTM]:
            model = load_model(model_path / "model.keras")
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Load scaler
        scaler = joblib.load(model_path / "scaler.joblib")
        
        # Load metadata
        with open(model_path / "metadata.json", "r") as f:
            metadata = json.load(f)
        
        return model, scaler, metadata


async def train_all_models(
    zone_id: str = None,
    parameter: str = None,
    data_source: DataSource = DataSource.MIXED,
    force: bool = False
) -> Dict[str, Any]:
    """Train all model types and select best."""
    trainer = ModelTrainer()
    db = get_database()
    
    results = {}
    
    # Check if recent model exists
    if not force:
        existing = await db[Collections.AI_MODELS].find_one({
            "zone_id": zone_id or "global",
            "parameter": parameter or "all",
            "status": ModelStatus.READY,
            "is_active": True,
        }, sort=[("created_at", -1)])
        
        if existing:
            last_training = existing.get("created_at")
            if last_training and (datetime.now(timezone.utc) - last_training).total_seconds() < settings.MODEL_RETRAIN_INTERVAL_HOURS * 3600:
                logger.info("recent_model_exists_skipping", model_id=str(existing["_id"]))
                return {"status": "skipped", "model_id": str(existing["_id"])}
    
    # Prepare data
    try:
        X, y, feature_cols, df = trainer.prepare_data(zone_id, parameter, data_source)
    except ValueError as e:
        logger.warning("no_training_data", error=str(e))
        # Generate synthetic data
        from app.services.data_generator import SyntheticDataGenerator, SyntheticDataConfig
        generator = SyntheticDataGenerator(SyntheticDataConfig(
            zones=[zone_id] if zone_id else settings.SYNTHETIC_DATA_CONFIG.zones,
            parameters=[parameter] if parameter else settings.SYNTHETIC_DATA_CONFIG.parameters,
        ))
        samples = generator.generate_all()
        
        # Save to database
        if samples:
            await db[Collections.TRAINING_DATA].insert_many([s.model_dump(by_alias=True) for s in samples])
        
        X, y, feature_cols, df = trainer.prepare_data(zone_id, parameter, DataSource.SYNTHETIC)
    
    logger.info("training_data_prepared", n_samples=len(X), n_features=X.shape[1], anomaly_rate=y.mean())
    
    # Train models
    model_types = [ModelType.ISOLATION_FOREST]
    if TF_AVAILABLE:
        model_types.extend([ModelType.AUTOENCODER, ModelType.LSTM])
    
    best_model = None
    best_f1 = 0
    
    for model_type in model_types:
        try:
            logger.info("training_model", model_type=model_type.value)
            
            if model_type == ModelType.ISOLATION_FOREST:
                result = trainer.train_isolation_forest(X, y)
            elif model_type == ModelType.AUTOENCODER:
                result = trainer.train_autoencoder(X, y)
            elif model_type == ModelType.LSTM:
                result = trainer.train_lstm(X, y)
            
            # Save model
            model_path = trainer.save_model(result, zone_id or "global", parameter or "all")
            
            # Save to database
            model_doc = AIModelInDB(
                model_type=result.model_type,
                version=result.version,
                status=ModelStatus.READY,
                is_active=False,  # Will activate best one
                parameters=feature_cols,
                hyperparameters={},
                metrics=result.metrics,
                training_samples=len(X),
                data_source=data_source,
                model_path=model_path,
                scaler_path=str(Path(model_path) / "scaler.joblib"),
            )
            
            await db[Collections.AI_MODELS].insert_one(model_doc.model_dump(by_alias=True))
            
            # Save metadata
            meta_doc = ModelMetadataInDB(
                model_type=result.model_type,
                version=result.version,
                training_config={"zone_id": zone_id, "parameter": parameter, "data_source": data_source.value},
                data_stats={"n_samples": len(X), "n_features": X.shape[1], "anomaly_rate": float(y.mean())},
                metrics=result.metrics,
                feature_importance=result.feature_importance,
                training_duration_seconds=result.training_duration,
            )
            
            await db[Collections.MODEL_METADATA].insert_one(meta_doc.model_dump(by_alias=True))
            
            results[model_type.value] = {
                "metrics": result.metrics,
                "duration": result.training_duration,
                "version": result.version,
                "path": model_path,
            }
            
            # Track best model
            if result.metrics.get('f1', 0) > best_f1:
                best_f1 = result.metrics['f1']
                best_model = result.model_type
            
            logger.info("model_trained", 
                        model_type=model_type.value, 
                        f1=result.metrics['f1'], 
                        precision=result.metrics['precision'],
                        recall=result.metrics['recall'])
            
        except Exception as e:
            logger.error("model_training_failed", model_type=model_type.value, error=str(e))
            results[model_type.value] = {"error": str(e)}
    
    # Activate best model
    if best_model:
        await db[Collections.AI_MODELS].update_one(
            {"model_type": best_model, "zone_id": zone_id or "global", "parameter": parameter or "all", "version": results[best_model.value]["version"]},
            {"$set": {"is_active": True, "activated_at": datetime.now(timezone.utc)}}
        )
        
        logger.info("best_model_activated", model_type=best_model.value, f1=best_f1)
    
    return {
        "status": "completed",
        "results": results,
        "best_model": best_model.value if best_model else None,
        "best_f1": best_f1,
    }


if __name__ == "__main__":
    import asyncio
    asyncio.run(train_all_models())