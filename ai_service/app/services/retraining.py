"""
Scheduled Retraining Service
Handles automatic model retraining on schedule using APScheduler.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.services.model_trainer import train_all_models
from app.models.ai import ModelType, DataSource, ModelStatus
from app.core.database import get_database, Collections

logger = get_logger(__name__)


@dataclass
class RetrainingJob:
    """Configuration for a retraining job."""
    job_id: str
    model_type: Optional[ModelType]
    zone_id: Optional[str]
    parameter: Optional[str]
    data_source: DataSource
    trigger: IntervalTrigger | CronTrigger
    force: bool = False


class RetrainingScheduler:
    """
    Manages scheduled model retraining jobs.
    
    Features:
    - Interval-based retraining (e.g., every 24 hours)
    - Cron-based retraining (e.g., daily at 3 AM)
    - Per-zone/parameter or global retraining
    - Force retrain option
    - Job persistence and monitoring
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, RetrainingJob] = {}
        self._running = False
    
    def start(self) -> None:
        """Start the scheduler."""
        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("retraining_scheduler_started")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("retraining_scheduler_stopped")
    
    def add_interval_job(
        self,
        job_id: str,
        hours: int,
        model_type: Optional[ModelType] = None,
        zone_id: Optional[str] = None,
        parameter: Optional[str] = None,
        data_source: DataSource = DataSource.MIXED,
        force: bool = False,
    ) -> None:
        """Add an interval-based retraining job."""
        if job_id in self.jobs:
            self.remove_job(job_id)
        
        trigger = IntervalTrigger(hours=hours)
        job = RetrainingJob(
            job_id=job_id,
            model_type=model_type,
            zone_id=zone_id,
            parameter=parameter,
            data_source=data_source,
            trigger=trigger,
            force=force,
        )
        
        self.scheduler.add_job(
            self._run_training_job,
            trigger=trigger,
            id=job_id,
            args=[job],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        
        self.jobs[job_id] = job
        logger.info("retraining_job_added", job_id=job_id, interval_hours=hours)
    
    def add_cron_job(
        self,
        job_id: str,
        hour: int,
        minute: int = 0,
        model_type: Optional[ModelType] = None,
        zone_id: Optional[str] = None,
        parameter: Optional[str] = None,
        data_source: DataSource = DataSource.MIXED,
        force: bool = False,
    ) -> None:
        """Add a cron-based retraining job (runs at specific time daily)."""
        if job_id in self.jobs:
            self.remove_job(job_id)
        
        trigger = CronTrigger(hour=hour, minute=minute)
        job = RetrainingJob(
            job_id=job_id,
            model_type=model_type,
            zone_id=zone_id,
            parameter=parameter,
            data_source=data_source,
            trigger=trigger,
            force=force,
        )
        
        self.scheduler.add_job(
            self._run_training_job,
            trigger=trigger,
            id=job_id,
            args=[job],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        
        self.jobs[job_id] = job
        logger.info("retraining_job_added", job_id=job_id, cron=f"{hour}:{minute:02d}")
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a retraining job."""
        try:
            self.scheduler.remove_job(job_id)
            self.jobs.pop(job_id, None)
            logger.info("retraining_job_removed", job_id=job_id)
            return True
        except Exception as e:
            logger.warning("retraining_job_remove_failed", job_id=job_id, error=str(e))
            return False
    
    def get_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all scheduled jobs."""
        jobs_info = {}
        for job_id, job in self.jobs.items():
            scheduler_job = self.scheduler.get_job(job_id)
            jobs_info[job_id] = {
                "job_id": job_id,
                "model_type": job.model_type.value if job.model_type else "all",
                "zone_id": job.zone_id or "global",
                "parameter": job.parameter or "all",
                "data_source": job.data_source.value,
                "force": job.force,
                "next_run": scheduler_job.next_run_time.isoformat() if scheduler_job and scheduler_job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        return jobs_info
    
    async def _run_training_job(self, job: RetrainingJob) -> None:
        """Execute a training job."""
        logger.info("scheduled_training_started", job_id=job.job_id)
        
        try:
            result = await train_all_models(
                zone_id=job.zone_id,
                parameter=job.parameter,
                data_source=job.data_source,
                force=job.force,
            )
            
            logger.info("scheduled_training_completed", 
                       job_id=job.job_id, 
                       status=result.get("status"),
                       best_model=result.get("best_model"),
                       best_f1=result.get("best_f1"))
            
            # Update job status in database
            await self._update_job_status(job.job_id, "completed", result)
            
        except Exception as e:
            logger.error("scheduled_training_failed", job_id=job.job_id, error=str(e))
            await self._update_job_status(job.job_id, "failed", {"error": str(e)})
    
    async def _update_job_status(self, job_id: str, status: str, result: Dict) -> None:
        """Update job status in database."""
        try:
            db = get_database()
            await db[Collections.MODEL_METADATA].update_one(
                {"_id": job_id},  # Using job_id as custom ID
                {
                    "$set": {
                        "last_run": datetime.now(timezone.utc),
                        "last_status": status,
                        "last_result": result,
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("job_status_update_failed", job_id=job_id, error=str(e))
    
    async def trigger_manual_retrain(
        self,
        model_type: Optional[ModelType] = None,
        zone_id: Optional[str] = None,
        parameter: Optional[str] = None,
        data_source: DataSource = DataSource.MIXED,
        force: bool = True,
    ) -> Dict[str, Any]:
        """Manually trigger retraining (for admin use)."""
        logger.info("manual_retrain_triggered", 
                   model_type=model_type, zone_id=zone_id, parameter=parameter)
        
        result = await train_all_models(
            zone_id=zone_id,
            parameter=parameter,
            data_source=data_source,
            force=force,
        )
        
        return result


# Global scheduler instance
_retraining_scheduler: Optional[RetrainingScheduler] = None


def get_retraining_scheduler() -> RetrainingScheduler:
    """Get singleton RetrainingScheduler instance."""
    global _retraining_scheduler
    if _retraining_scheduler is None:
        _retraining_scheduler = RetrainingScheduler()
        # Add default scheduled job
        _retraining_scheduler.add_interval_job(
            job_id="global_retrain_24h",
            hours=settings.MODEL_RETRAIN_INTERVAL_HOURS,
            data_source=DataSource.MIXED,
        )
    return _retraining_scheduler


async def init_scheduler() -> RetrainingScheduler:
    """Initialize and start the retraining scheduler."""
    scheduler = get_retraining_scheduler()
    scheduler.start()
    logger.info("retraining_scheduler_initialized")
    return scheduler


async def shutdown_scheduler() -> None:
    """Shutdown the retraining scheduler."""
    global _retraining_scheduler
    if _retraining_scheduler:
        _retraining_scheduler.stop()
        _retraining_scheduler = None
    logger.info("retraining_scheduler_shutdown")