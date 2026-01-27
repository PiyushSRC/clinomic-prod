from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TenantContext:
    org_id: str
    is_super_admin: bool = False


def org_id_for_lab_id(lab_id: Optional[str]) -> Optional[str]:
    if not lab_id:
        return None
    # Simple deterministic mapping for seeded labs.
    if lab_id == "LAB-2024-001":
        return "ORG-LAB-2024-001"
    if lab_id == "LAB-2024-014":
        return "ORG-LAB-2024-014"
    return None


def org_id_for_demo_user(username: str) -> TenantContext:
    # Milestone 1: keep demo users but assign stable orgs.
    if username == "admin":
        return TenantContext(org_id="ORG-CLINOMIC", is_super_admin=True)
    if username == "lab":
        return TenantContext(org_id="ORG-LAB-2024-001", is_super_admin=False)
    if username == "doctor":
        return TenantContext(org_id="ORG-LAB-2024-001", is_super_admin=False)
    return TenantContext(org_id="ORG-CLINOMIC", is_super_admin=False)


def enforce_org(query: Dict[str, Any], org_id: str, is_super_admin: bool) -> Dict[str, Any]:
    if is_super_admin:
        return query
    q = dict(query)
    q["orgId"] = org_id
    return q
