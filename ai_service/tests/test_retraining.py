"""
Tests for Retraining Scheduler
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.services.retraining import RetrainingScheduler, RetrainingJob
from app.models.ai import ModelType, DataSource


class TestRetrainingScheduler:
    """Test retraining scheduler functionality."""

    @pytest.fixture
    def scheduler(self):
        """Create scheduler instance."""
        sched = RetrainingScheduler()
        yield sched
        # Cleanup
        sched.stop()

    def test_start_stop(self, scheduler):
        """Test scheduler start and stop."""
        assert scheduler._running == False
        
        scheduler.start()
        assert scheduler._running == True
        
        scheduler.stop()
        assert scheduler._running == False

    def test_add_interval_job(self, scheduler):
        """Test adding interval-based job."""
        scheduler.add_interval_job(
            job_id="test_interval",
            hours=6,
            model_type=ModelType.ISOLATION_FOREST,
            zone_id="prod-01",
            parameter="temperature",
            data_source=DataSource.SYNTHETIC,
            force=True,
        )
        
        assert "test_interval" in scheduler.jobs
        job = scheduler.jobs["test_interval"]
        assert job.job_id == "test_interval"
        assert job.model_type == ModelType.ISOLATION_FOREST
        assert job.zone_id == "prod-01"
        assert job.parameter == "temperature"
        assert job.data_source == DataSource.SYNTHETIC
        assert job.force == True
        assert isinstance(job.trigger, IntervalTrigger)

    def test_add_cron_job(self, scheduler):
        """Test adding cron-based job."""
        scheduler.add_cron_job(
            job_id="test_cron",
            hour=3,
            minute=30,
            model_type=ModelType.AUTOENCODER,
            zone_id="global",
            parameter="all",
            data_source=DataSource.MIXED,
            force=False,
        )
        
        assert "test_cron" in scheduler.jobs
        job = scheduler.jobs["test_cron"]
        assert job.job_id == "test_cron"
        assert job.model_type == ModelType.AUTOENCODER
        assert job.zone_id == "global"
        assert isinstance(job.trigger, CronTrigger)

    def test_remove_job(self, scheduler):
        """Test removing job."""
        scheduler.add_interval_job(job_id="test_remove", hours=12)
        assert "test_remove" in scheduler.jobs
        
        result = scheduler.remove_job("test_remove")
        assert result == True
        assert "test_remove" not in scheduler.jobs
        
        # Remove non-existent job
        result = scheduler.remove_job("nonexistent")
        assert result == False

    def test_get_jobs(self, scheduler):
        """Test getting job status."""
        scheduler.add_interval_job(job_id="job1", hours=6)
        scheduler.add_cron_job(job_id="job2", hour=4)
        
        jobs = scheduler.get_jobs()
        
        assert "job1" in jobs
        assert "job2" in jobs
        assert jobs["job1"]["model_type"] == "isolation_forest"
        assert jobs["job1"]["interval_hours"] == 6  # Will be in trigger str
        assert jobs["job2"]["cron_hour"] == 4

    def test_duplicate_job_id(self, scheduler):
        """Test that duplicate job IDs replace existing."""
        scheduler.add_interval_job(job_id="duplicate", hours=6)
        assert len(scheduler.jobs) == 1
        
        scheduler.add_interval_job(job_id="duplicate", hours=12)
        assert len(scheduler.jobs) == 1
        assert scheduler.jobs["duplicate"].trigger.interval_length == 12

    @pytest.mark.asyncio
    async def test_trigger_manual_retrain(self, scheduler, mock_db):
        """Test manual retraining trigger."""
        with patch("app.services.retraining.train_all_models") as mock_train:
            mock_train.return_value = {
                "status": "completed",
                "results": {"isolation_forest": {"f1": 0.85}},
                "best_model": "isolation_forest",
                "best_f1": 0.85,
            }
            
            result = await scheduler.trigger_manual_retrain(
                model_type=ModelType.ISOLATION_FOREST,
                zone_id="prod-01",
                parameter="temperature",
                data_source=DataSource.SYNTHETIC,
                force=True,
            )
            
            assert result["status"] == "completed"
            assert result["best_model"] == "isolation_forest"
            mock_train.assert_called_once_with(
                zone_id="prod-01",
                parameter="temperature",
                data_source=DataSource.SYNTHETIC,
                force=True,
            )

    @pytest.mark.asyncio
    async def test_run_training_job_success(self, scheduler, mock_db):
        """Test successful training job execution."""
        job = RetrainingJob(
            job_id="test_job",
            model_type=ModelType.ISOLATION_FOREST,
            zone_id="prod-01",
            parameter="temperature",
            data_source=DataSource.SYNTHETIC,
            trigger=IntervalTrigger(hours=24),
            force=False,
        )
        
        with patch("app.services.retraining.train_all_models") as mock_train:
            mock_train.return_value = {
                "status": "completed",
                "best_model": "isolation_forest",
                "best_f1": 0.85,
            }
            
            await scheduler._run_training_job(job)
            
            mock_train.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_training_job_failure(self, scheduler, mock_db):
        """Test training job failure handling."""
        job = RetrainingJob(
            job_id="test_job_fail",
            model_type=ModelType.ISOLATION_FOREST,
            zone_id=None,
            parameter=None,
            data_source=DataSource.MIXED,
            trigger=IntervalTrigger(hours=24),
            force=False,
        )
        
        with patch("app.services.retraining.train_all_models") as mock_train:
            mock_train.side_effect = Exception("Training failed")
            
            # Should not raise exception
            await scheduler._run_training_job(job)


class TestRetrainingSchedulerIntegration:
    """Integration tests for retraining scheduler."""

    @pytest.fixture
    def scheduler(self):
        """Create scheduler with mocked database."""
        with patch("app.services.retraining.get_database") as mock_db:
            mock_collection = AsyncMock()
            mock_collection.update_one = AsyncMock()
            mock_db.return_value.__getitem__.return_value = mock_collection
            
            sched = RetrainingScheduler()
            yield sched
            sched.stop()

    def test_default_job_creation(self):
        """Test that get_retraining_scheduler creates default job."""
        from app.services.retraining import get_retraining_scheduler
        
        # Reset global
        import app.services.retraining as retraining_module
        retraining_module._retraining_scheduler = None
        
        scheduler = get_retraining_scheduler()
        
        # Check default job exists
        jobs = scheduler.get_jobs()
        assert "global_retrain_24h" in jobs
        assert jobs["global_retrain_24h"]["model_type"] == "all"
        assert jobs["global_retrain_24h"]["data_source"] == "mixed"


