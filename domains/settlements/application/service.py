from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.audit.application.service import write_audit_log
from domains.reports.application.service import get_daily_dashboard
from domains.settlements.infrastructure.models import DailySettlement


def close_daily_settlement(
    db: Session, *, franchise_id: int, business_date: date, actor_user_id: int
) -> DailySettlement:
    existing = db.scalar(
        select(DailySettlement).where(
            DailySettlement.franchise_id == franchise_id,
            DailySettlement.business_date == business_date,
        )
    )
    if existing is not None:
        raise ValueError("Settlement already exists for this franchise and date.")

    dashboard = get_daily_dashboard(db, franchise_id=franchise_id, business_date=business_date)
    settlement = DailySettlement(
        franchise_id=franchise_id,
        business_date=business_date,
        total_income=dashboard["total_income"],
        pending_income=dashboard["pending_income"],
        cash_income=dashboard["cash_income"],
        upi_income=dashboard["upi_income"],
        card_income=dashboard["card_income"],
        bank_income=dashboard["bank_income"],
        status="settled",
        closed_by_user_id=actor_user_id,
    )
    db.add(settlement)
    db.flush()

    write_audit_log(
        db,
        action="settlement.close",
        entity_name="daily_settlements",
        entity_id=str(settlement.id),
        actor_user_id=actor_user_id,
        franchise_id=settlement.franchise_id,
        payload={"business_date": business_date.isoformat()},
    )
    return settlement
