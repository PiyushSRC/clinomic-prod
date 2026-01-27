from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


class AuditLogger:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    @staticmethod
    def canonical_json(data: Any) -> str:
        """Canonical JSON serialization for hashing."""
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    async def get_last_hash(self, org_id: str) -> str:
        """Fetch the latest eventHash for the given org."""
        last_event = await self.db.audit_logs.find_one({"orgId": org_id}, sort=[("timestamp", -1), ("_id", -1)])
        return last_event["eventHash"] if last_event else "0" * 64

    async def log_event(
        self,
        actor: str,
        org_id: str,
        action: str,
        entity: str,
        details: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> str:
        """Appends a new hash-chained event to the audit ledger."""
        now = datetime.now(timezone.utc).isoformat()
        prev_hash = await self.get_last_hash(org_id)

        # Base event data
        event_data = {
            "actor": actor,
            "orgId": org_id,
            "action": action,
            "entity": entity,
            "details": details,
            "timestamp": now,
            "requestId": request_id,
            "prevHash": prev_hash,
        }

        # Calculate eventHash (SHA256 of canonical JSON representation)
        payload = self.canonical_json(event_data)
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        # Save to DB
        doc = {**event_data, "eventHash": event_hash}
        await self.db.audit_logs.insert_one(doc)

        return event_hash

    async def verify_chain(self, org_id: str, limit: int = 100) -> Dict[str, Any]:
        """Verifies the integrity of the audit chain for an organization."""
        cursor = self.db.audit_logs.find({"orgId": org_id}).sort([("timestamp", 1), ("_id", 1)]).limit(limit)
        logs = await cursor.to_list(length=limit)

        expected_prev_hash = "0" * 64
        verification_results = []
        is_valid = True

        for log in logs:
            log_copy = {k: v for k, v in log.items() if k not in ("_id", "eventHash")}
            actual_event_hash = log["eventHash"]
            prev_hash = log["prevHash"]

            # 1. Check prevHash link
            link_valid = prev_hash == expected_prev_hash

            # 2. Check current hash
            payload = self.canonical_json(log_copy)
            calculated_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            content_valid = actual_event_hash == calculated_hash

            log_valid = link_valid and content_valid
            if not log_valid:
                is_valid = False

            verification_results.append(
                {
                    "id": str(log.get("_id")),
                    "timestamp": log["timestamp"],
                    "action": log["action"],
                    "isValid": log_valid,
                    "reason": None if log_valid else ("Link broken" if not link_valid else "Content tampered"),
                }
            )

            expected_prev_hash = actual_event_hash

        return {"orgId": org_id, "isValid": is_valid, "totalVerified": len(logs), "results": verification_results}
