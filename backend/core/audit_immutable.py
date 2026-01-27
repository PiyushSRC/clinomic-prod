"""Immutable Audit Logger with Cryptographic Sealing.

This module extends the base audit logger with:
- HMAC-based cryptographic sealing
- Periodic checkpoint signing
- Tamper-evident markers
- Chain verification
- Archive support for immutable storage
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.secrets import get_secret


class ImmutableAuditLogger:
    """
    Cryptographically sealed audit logger.

    Features:
    - Hash-chained entries (like blockchain)
    - HMAC signature on each entry for tampering detection
    - Periodic checkpoints with merkle root
    - Export capability for archival
    """

    CHECKPOINT_INTERVAL = 100  # Create checkpoint every N entries

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.audit_logs = db["audit_logs_v2"]  # New collection for immutable logs
        self.checkpoints = db["audit_checkpoints"]
        self._signing_key: Optional[str] = None

    def _get_signing_key(self) -> str:
        """Get the signing key (cached)."""
        if self._signing_key is None:
            self._signing_key = get_secret("AUDIT_SIGNING_KEY")
        return self._signing_key

    @staticmethod
    def canonical_json(data: Any) -> str:
        """Canonical JSON serialization for hashing."""
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _compute_hmac(self, data: str) -> str:
        """Compute HMAC-SHA256 signature."""
        key = self._get_signing_key().encode()
        signature = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()
        return signature

    def _compute_hash(self, data: str) -> str:
        """Compute SHA256 hash."""
        return hashlib.sha256(data.encode()).hexdigest()

    async def get_last_entry(self, org_id: str) -> Optional[Dict]:
        """Get the last audit entry for an organization."""
        return await self.audit_logs.find_one({"orgId": org_id}, sort=[("sequence", -1)])

    async def get_next_sequence(self, org_id: str) -> int:
        """Get the next sequence number for an organization."""
        last_entry = await self.get_last_entry(org_id)
        return (last_entry.get("sequence", 0) + 1) if last_entry else 1

    async def log_event(
        self,
        actor: str,
        org_id: str,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """Log an immutable audit event with cryptographic sealing."""
        now = datetime.now(timezone.utc)
        sequence = await self.get_next_sequence(org_id)

        # Get previous hash for chain
        last_entry = await self.get_last_entry(org_id)
        prev_hash = last_entry["entryHash"] if last_entry else "0" * 64

        # Build entry data (excluding computed fields)
        entry_id = str(uuid.uuid4())
        entry_data = {
            "id": entry_id,
            "orgId": org_id,
            "sequence": sequence,
            "timestamp": now.isoformat(),
            "actor": actor,
            "action": action,
            "entity": entity,
            "entityId": entity_id,
            "details": details or {},
            "requestId": request_id,
            "ipAddress": ip_address,
            "userAgent": user_agent,
            "prevHash": prev_hash,
        }

        # Compute entry hash (content + chain)
        canonical = self.canonical_json(entry_data)
        entry_hash = self._compute_hash(canonical)

        # Compute HMAC signature for tamper detection
        signature = self._compute_hmac(canonical + entry_hash)

        # Final document
        doc = {
            **entry_data,
            "entryHash": entry_hash,
            "signature": signature,
            "sealed": True,
        }

        await self.audit_logs.insert_one(doc)

        # Check if checkpoint needed
        if sequence % self.CHECKPOINT_INTERVAL == 0:
            await self._create_checkpoint(org_id, sequence)

        return entry_id

    async def _create_checkpoint(self, org_id: str, up_to_sequence: int) -> str:
        """Create a checkpoint with merkle root of recent entries."""
        # Get entries since last checkpoint
        last_checkpoint = await self.checkpoints.find_one({"orgId": org_id}, sort=[("upToSequence", -1)])
        from_sequence = (last_checkpoint["upToSequence"] + 1) if last_checkpoint else 1

        # Fetch entries
        cursor = self.audit_logs.find({"orgId": org_id, "sequence": {"$gte": from_sequence, "$lte": up_to_sequence}}).sort(
            "sequence", 1
        )
        entries = await cursor.to_list(length=self.CHECKPOINT_INTERVAL + 10)

        # Compute merkle root
        hashes = [e["entryHash"] for e in entries]
        merkle_root = self._compute_merkle_root(hashes)

        # Create checkpoint
        checkpoint_id = str(uuid.uuid4())
        checkpoint_data = {
            "id": checkpoint_id,
            "orgId": org_id,
            "fromSequence": from_sequence,
            "upToSequence": up_to_sequence,
            "entryCount": len(entries),
            "merkleRoot": merkle_root,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Sign the checkpoint
        canonical = self.canonical_json(checkpoint_data)
        checkpoint_data["signature"] = self._compute_hmac(canonical)

        await self.checkpoints.insert_one(checkpoint_data)
        return checkpoint_id

    def _compute_merkle_root(self, hashes: List[str]) -> str:
        """Compute merkle root from a list of hashes."""
        if not hashes:
            return "0" * 64
        if len(hashes) == 1:
            return hashes[0]

        # Pad to even length
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        # Compute parent level
        parent_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i + 1]
            parent_level.append(self._compute_hash(combined))

        return self._compute_merkle_root(parent_level)

    async def verify_entry(self, entry_id: str) -> Dict[str, Any]:
        """Verify the integrity of a single audit entry."""
        entry = await self.audit_logs.find_one({"id": entry_id})
        if not entry:
            return {"valid": False, "error": "Entry not found"}

        # Reconstruct entry data
        entry_data = {
            "id": entry["id"],
            "orgId": entry["orgId"],
            "sequence": entry["sequence"],
            "timestamp": entry["timestamp"],
            "actor": entry["actor"],
            "action": entry["action"],
            "entity": entry["entity"],
            "entityId": entry.get("entityId"),
            "details": entry.get("details", {}),
            "requestId": entry.get("requestId"),
            "ipAddress": entry.get("ipAddress"),
            "userAgent": entry.get("userAgent"),
            "prevHash": entry["prevHash"],
        }

        # Verify hash
        canonical = self.canonical_json(entry_data)
        expected_hash = self._compute_hash(canonical)
        if entry["entryHash"] != expected_hash:
            return {"valid": False, "error": "Hash mismatch - content tampered"}

        # Verify signature
        expected_sig = self._compute_hmac(canonical + expected_hash)
        if entry["signature"] != expected_sig:
            return {"valid": False, "error": "Signature mismatch - tampering detected"}

        return {"valid": True, "entry_id": entry_id}

    async def verify_chain(self, org_id: str, limit: int = 1000) -> Dict[str, Any]:
        """Verify the integrity of the audit chain."""
        cursor = self.audit_logs.find({"orgId": org_id}).sort("sequence", 1).limit(limit)
        entries = await cursor.to_list(length=limit)

        if not entries:
            return {"valid": True, "totalVerified": 0, "issues": []}

        expected_prev_hash = "0" * 64
        issues = []

        for entry in entries:
            # Verify hash chain
            if entry["prevHash"] != expected_prev_hash:
                issues.append(
                    {
                        "sequence": entry["sequence"],
                        "type": "chain_break",
                        "message": f"Chain break at sequence {entry['sequence']}",
                    }
                )

            # Verify entry integrity
            result = await self.verify_entry(entry["id"])
            if not result["valid"]:
                issues.append({"sequence": entry["sequence"], "type": "integrity_failure", "message": result["error"]})

            expected_prev_hash = entry["entryHash"]

        return {
            "valid": len(issues) == 0,
            "totalVerified": len(entries),
            "issues": issues,
            "lastSequence": entries[-1]["sequence"] if entries else 0,
        }

    async def export_for_archive(
        self, org_id: str, from_sequence: int = 1, to_sequence: Optional[int] = None
    ) -> Dict[str, Any]:
        """Export audit logs for archival to immutable storage."""
        query = {"orgId": org_id, "sequence": {"$gte": from_sequence}}
        if to_sequence:
            query["sequence"]["$lte"] = to_sequence

        cursor = self.audit_logs.find(query, {"_id": 0}).sort("sequence", 1)
        entries = await cursor.to_list(length=10000)

        # Get relevant checkpoints
        checkpoint_query = {"orgId": org_id, "fromSequence": {"$gte": from_sequence}}
        if to_sequence:
            checkpoint_query["upToSequence"] = {"$lte": to_sequence}

        checkpoints_cursor = self.checkpoints.find(checkpoint_query, {"_id": 0})
        checkpoints = await checkpoints_cursor.to_list(length=1000)

        # Create export package
        export_data = {
            "orgId": org_id,
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "fromSequence": from_sequence,
            "toSequence": entries[-1]["sequence"] if entries else from_sequence,
            "entryCount": len(entries),
            "entries": entries,
            "checkpoints": checkpoints,
        }

        # Sign the export
        canonical = self.canonical_json(
            {
                "orgId": org_id,
                "fromSequence": export_data["fromSequence"],
                "toSequence": export_data["toSequence"],
                "entryCount": export_data["entryCount"],
            }
        )
        export_data["exportSignature"] = self._compute_hmac(canonical)

        return export_data

    async def get_audit_summary(self, org_id: str) -> Dict[str, Any]:
        """Get summary statistics for audit logs."""
        total_entries = await self.audit_logs.count_documents({"orgId": org_id})
        last_entry = await self.get_last_entry(org_id)

        # Verify chain integrity (sample)
        verification = await self.verify_chain(org_id, limit=100)

        # Get checkpoint count
        checkpoint_count = await self.checkpoints.count_documents({"orgId": org_id})

        return {
            "orgId": org_id,
            "totalEntries": total_entries,
            "lastSequence": last_entry["sequence"] if last_entry else 0,
            "lastTimestamp": last_entry["timestamp"] if last_entry else None,
            "checkpointCount": checkpoint_count,
            "chainIntegrity": {
                "verified": verification["valid"],
                "sampledEntries": verification["totalVerified"],
                "issues": len(verification["issues"]),
            },
        }
