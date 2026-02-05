import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth.models import AuditLog

class AuditLogger:
    @staticmethod
    def canonical_str(data: dict) -> str:
        """Sort keys for consistent hashing"""
        return json.dumps(data, sort_keys=True, separators=(',', ':'))

    @staticmethod
    def compute_signature(data_str: str) -> str:
        """HMAC Signature"""
        return hmac.new(
            settings.SECRET_KEY.encode(),
            data_str.encode(),
            hashlib.sha256
        ).hexdigest()

    def log(
        self,
        db,
        org_id: UUID,
        actor_id: str,
        action: str,
        entity: str,
        entity_id: str,
        details: Optional[dict] = None
    ):
        """
        Write Immutable Audit Log with Hash Chain
        """
        # Fetch last log for chain
        last_log = db.query(AuditLog).filter(AuditLog.org_id == org_id).order_by(AuditLog.timestamp.desc()).first()
        prev_hash = last_log.signature if last_log else "0" * 64
        
        timestamp = datetime.now(timezone.utc)
        
        # Payload to sign
        payload = {
            "org_id": str(org_id),
            "actor_id": actor_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "timestamp": timestamp.isoformat(),
            "prev_hash": prev_hash,
            "details": details or {}
        }
        
        canonical = self.canonical_str(payload)
        signature = self.compute_signature(canonical)
        
        log_entry = AuditLog(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            timestamp=timestamp,
            prev_hash=prev_hash,
            signature=signature,
            details=json.dumps(details) if details else None
        )
        
        db.add(log_entry)
        db.commit()
        
audit = AuditLogger()
