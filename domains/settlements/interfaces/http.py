from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from domains.users.domain.access import SETTLE_DAY
from domains.settlements.application.service import close_daily_settlement
from foundation.database.session import get_db
from foundation.web.dependencies import FranchiseScope, UserContext, get_franchise_scope, require_permissions

router = APIRouter(prefix="/settlements", tags=["settlements"])


class SettlementCloseRequest(BaseModel):
    business_date: date


@router.post("/close", status_code=status.HTTP_201_CREATED)
def close_settlement(
        payload: SettlementCloseRequest,
        db: Session = Depends(get_db),
        context: UserContext = Depends(require_permissions(SETTLE_DAY)),
        scope: FranchiseScope = Depends(get_franchise_scope),
) -> dict:
    """Close daily settlement for franchise. **Body:** `SettlementCloseRequest` (`business_date`). **Auth:** `SETTLE_DAY` + franchise scope. **Success:** 201 with settlement id and totals. **Errors:** **400** `detail` string on business rule failure (`ValueError`); 401/403 as deps."""
    try:
        settlement = close_daily_settlement(
            db,
            franchise_id=scope.franchise_id,
            business_date=payload.business_date,
            actor_user_id=context.user.id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": settlement.id,
        "business_date": settlement.business_date.isoformat(),
        "total_income": str(settlement.total_income),
        "pending_income": str(settlement.pending_income),
    }
