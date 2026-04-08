from sqlalchemy.orm import Session

from domains.audit.infrastructure.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    entity_name: str,
    entity_id: str,
    actor_user_id: int | None,
    franchise_id: int | None,
    payload: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        franchise_id=franchise_id,
        payload=payload,
    )
    db.add(entry)
    return entry
