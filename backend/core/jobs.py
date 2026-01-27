from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("clinomic.jobs")


class JobStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobManager:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["jobs"]

    async def create_job(self, job_type: str, org_id: str, user_id: str, params: Optional[Dict] = None) -> str:
        job_id = str(uuid.uuid4())
        job_doc = {
            "id": job_id,
            "type": job_type,
            "status": JobStatus.PENDING,
            "progress": 0,
            "result": None,
            "error": None,
            "orgId": org_id,
            "userId": user_id,
            "params": params or {},
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        await self.collection.insert_one(job_doc)
        return job_id

    async def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ):
        update_data: Dict[str, Any] = {"updatedAt": datetime.now(timezone.utc).isoformat()}
        if status:
            update_data["status"] = status
        if progress is not None:
            update_data["progress"] = progress
        if result is not None:
            update_data["result"] = result
        if error is not None:
            update_data["error"] = error

        await self.collection.update_one({"id": job_id}, {"$set": update_data})

    async def run_in_background(self, job_id: str, coro_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs):
        """
        Wraps a coroutine and executes it in the background,
        updating job status automatically.
        """

        async def _wrapper():
            try:
                await self.update_job(job_id, status=JobStatus.RUNNING, progress=10)
                result = await coro_func(job_id, *args, **kwargs)
                await self.update_job(job_id, status=JobStatus.COMPLETED, progress=100, result=result)
            except Exception as e:
                logger.exception(f"Job {job_id} failed")
                await self.update_job(job_id, status=JobStatus.FAILED, error=str(e))

        asyncio.create_task(_wrapper())

    async def get_job(self, job_id: str, org_id: str) -> Optional[Dict]:
        return await self.collection.find_one({"id": job_id, "orgId": org_id}, {"_id": 0})

    async def list_jobs(self, org_id: str, limit: int = 50) -> list[Dict]:
        cursor = self.collection.find({"orgId": org_id}, {"_id": 0}).sort("createdAt", -1).limit(limit)
        return await cursor.to_list(length=limit)
