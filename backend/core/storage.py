from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


class ObjectStorage:
    CHUNK_SIZE = 255 * 1024  # 255 KB, standard GridFS chunk size

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.files = db["files"]
        self.chunks = db["file_chunks"]

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        org_id: str,
        screening_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        file_id = str(uuid.uuid4())
        size = len(file_data)

        # 1. Store metadata
        file_doc = {
            "id": file_id,
            "filename": filename,
            "contentType": content_type,
            "length": size,
            "chunkSize": self.CHUNK_SIZE,
            "uploadDate": datetime.now(timezone.utc).isoformat(),
            "orgId": org_id,
            "screeningId": screening_id,
            "metadata": metadata or {},
        }
        await self.files.insert_one(file_doc)

        # 2. Store chunks
        num_chunks = (size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
        for i in range(num_chunks):
            start = i * self.CHUNK_SIZE
            end = min(start + self.CHUNK_SIZE, size)
            chunk_data = file_data[start:end]

            await self.chunks.insert_one({"fileId": file_id, "n": i, "data": chunk_data})

        return file_id

    async def download_file(self, file_id: str, org_id: str) -> Optional[Dict]:
        """Returns metadata and a generator for chunked data."""
        file_doc = await self.files.find_one({"id": file_id, "orgId": org_id}, {"_id": 0})
        if not file_doc:
            return None

        return {"metadata": file_doc, "stream": self._stream_chunks(file_id)}

    async def _stream_chunks(self, file_id: str) -> AsyncGenerator[bytes, None]:
        cursor = self.chunks.find({"fileId": file_id}).sort("n", 1)
        async for chunk in cursor:
            yield chunk["data"]

    async def list_files(self, org_id: str, screening_id: Optional[str] = None) -> List[Dict]:
        query = {"orgId": org_id}
        if screening_id:
            query["screeningId"] = screening_id

        cursor = self.files.find(query, {"_id": 0}).sort("uploadDate", -1)
        return await cursor.to_list(length=100)
