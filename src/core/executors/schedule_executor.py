"""
ZENIC-AGENTS - ScheduleExecutor (Phase 7.1)

Ejecutor de programación de jobs. Usa APScheduler si disponible, sino dict simple.
"""

import logging
import time
from typing import Any, Dict, Optional

from .base import ActionExecutor, ActionResult, _HAS_APSCHEDULER

# Conditional imports for APScheduler (must be at module level to avoid NameError)
if _HAS_APSCHEDULER:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        _HAS_APSCHEDULER = False

logger = logging.getLogger(__name__)


class ScheduleExecutor(ActionExecutor):
    """Ejecutor de programación de jobs. Usa APScheduler si disponible, sino dict simple.

    Config: {operation, job_id, func, interval, cron, args}
    Operations: add, remove, list, pause, resume
    """

    def __init__(self) -> None:
        self._scheduler: Optional[Any] = None
        self._simple_jobs: Dict[str, Dict[str, Any]] = {}
        self._job_results: Dict[str, Any] = {}
        if _HAS_APSCHEDULER:
            try:
                self._scheduler = AsyncIOScheduler()
                logger.info("ScheduleExecutor: APScheduler initialized")
            except Exception as e:
                logger.warning(f"ScheduleExecutor: APScheduler init failed: {e}")
                self._scheduler = None

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "list").lower()
        job_id = config.get("job_id", "")

        valid_ops = {"add", "remove", "list", "pause", "resume"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid schedule operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        try:
            dispatch = {"add": lambda: self._add_job(config), "remove": lambda: self._remove_job(job_id),
                        "list": lambda: self._list_jobs(), "pause": lambda: self._pause_job(job_id),
                        "resume": lambda: self._resume_job(job_id)}
            result_data = await dispatch[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"ScheduleExecutor: {operation} completed for job '{job_id}'")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"ScheduleExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "job_id": job_id}, str(e), elapsed)

    async def _add_job(self, config):
        job_id = config.get("job_id", f"job_{int(time.time())}")
        func_name = config.get("func", "")
        interval = config.get("interval", 60)
        cron = config.get("cron", "")
        args = config.get("args", [])
        if not func_name: raise ValueError("Schedule add requires 'func' (function name)")

        job_info = {"job_id": job_id, "func": func_name, "interval": interval, "cron": cron,
                    "args": args, "status": "active", "created_at": time.time(), "next_run": time.time() + interval}

        if self._scheduler and _HAS_APSCHEDULER:
            async def _task(*a):
                logger.info(f"ScheduleExecutor: Executing scheduled job '{job_id}' - {func_name}")
                self._job_results[job_id] = {"last_run": time.time(), "status": "executed"}
            try:
                if cron:
                    parts = cron.split()
                    kw = {}
                    if len(parts) >= 1: kw["hour"] = int(parts[0])
                    if len(parts) >= 2: kw["minute"] = int(parts[1])
                    trigger = CronTrigger(**kw)
                else:
                    trigger = IntervalTrigger(seconds=interval)
                self._scheduler.add_job(_task, trigger=trigger, id=job_id, args=args, replace_existing=True)
                if not self._scheduler.running: self._scheduler.start()
                job_info["scheduler"] = "apscheduler"
            except Exception as e:
                logger.warning(f"ScheduleExecutor: APScheduler add_job failed: {e}, using fallback")
                self._simple_jobs[job_id] = job_info
                job_info["scheduler"] = "fallback"
        else:
            self._simple_jobs[job_id] = job_info
            job_info["scheduler"] = "fallback"
        return job_info

    async def _remove_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.remove_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: remove_job failed for {job_id}")
        removed = self._simple_jobs.pop(job_id, None) is not None
        return {"job_id": job_id, "removed": removed}

    async def _list_jobs(self):
        jobs = list(self._simple_jobs.values())
        if self._scheduler and _HAS_APSCHEDULER and self._scheduler.running:
            try:
                for job in self._scheduler.get_jobs():
                    jobs.append({"job_id": job.id, "func": str(job.func),
                                 "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                                 "scheduler": "apscheduler"})
            except Exception as e:
                logger.warning(f"ScheduleExecutor: Could not list APScheduler jobs: {e}")
        return {"jobs": jobs, "count": len(jobs)}

    async def _pause_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.pause_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: pause_job failed for {job_id}")
        if job_id in self._simple_jobs: self._simple_jobs[job_id]["status"] = "paused"
        return {"job_id": job_id, "status": "paused"}

    async def _resume_job(self, job_id):
        if self._scheduler and _HAS_APSCHEDULER:
            try: self._scheduler.resume_job(job_id)
            except Exception: logger.debug(f"ScheduleExecutor: resume_job failed for {job_id}")
        if job_id in self._simple_jobs: self._simple_jobs[job_id]["status"] = "active"
        return {"job_id": job_id, "status": "active"}
