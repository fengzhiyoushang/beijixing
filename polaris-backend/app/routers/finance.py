"""财务路由：记账 CRUD、汇总、趋势、预算、学习投入专项。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.finance import BudgetIn, BudgetUpdate, FinanceRecordIn, FinanceRecordUpdate
from app.services import finance_service

router = APIRouter(prefix="/finance", tags=["⑨ 财务"])


# ─────────── 统计（置于 /records/{id} 之前） ───────────
@router.get("/summary", summary="月度汇总（收入/支出/结余/学习投入占比/分类）")
def summary(month: str | None = Query(default=None, description="YYYY-MM，缺省本月"),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return finance_service.summary(db, user.id, month)


@router.get("/trend", summary="近 N 个月收支趋势")
def trend(months: int = Query(default=6, ge=1, le=36), db: Session = Depends(get_db),
          user: User = Depends(get_current_user)) -> dict:
    return {"items": finance_service.trend(db, user.id, months=months)}


@router.get("/study-analysis", summary="学习投入专项分析")
def study_analysis(months: int = Query(default=6, ge=1, le=36), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    return finance_service.study_analysis(db, user.id, months=months)


@router.get("/budgets", summary="预算列表（含已用/剩余/执行率）")
def list_budgets(month: str | None = Query(default=None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    items = finance_service.list_budgets(db, user.id, month)
    return {"total": len(items), "items": items}


@router.post("/budgets", summary="设置预算（category='*' 为总预算）")
def set_budget(body: BudgetIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    budget = finance_service.set_budget(db, user.id, body)
    items = finance_service.list_budgets(db, user.id, body.month)
    current = next((b for b in items if b["category"] == budget.category), None)
    return current or budget.to_dict()


@router.put("/budgets/{budget_id}", summary="修改预算额度")
def update_budget(budget_id: int, body: BudgetUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.core.exceptions import NotFoundError
    from app.models.finance import FinanceBudget

    budget = db.get(FinanceBudget, budget_id)
    if not budget or budget.user_id != user.id:
        raise NotFoundError("预算不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(budget, key, value)
    db.commit()
    return budget.to_dict()


@router.delete("/budgets/{budget_id}", summary="删除预算")
def delete_budget(budget_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    finance_service.delete_budget(db, user.id, budget_id)
    return {"deleted": True}


# ─────────── 记账 ───────────
@router.get("/records", summary="记账流水（可按月/分类/类型/学习投入筛选）")
def list_records(month: str | None = Query(default=None), category: str | None = Query(default=None),
                 type: str | None = Query(default=None, alias="type"),
                 is_study: bool | None = Query(default=None),
                 limit: int = Query(default=300, ge=1, le=1000),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    records = finance_service.list_records(db, user.id, month=month, category=category,
                                           type_=type, is_study=is_study, limit=limit)
    return {"total": len(records), "items": [r.to_dict() for r in records]}


@router.post("/records", summary="记一笔（收入/支出）")
def create_record(body: FinanceRecordIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = finance_service.create_record(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.put("/records/{record_id}", summary="修改记录")
def update_record(record_id: int, body: FinanceRecordUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = finance_service.update_record(db, user.id, record_id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.delete("/records/{record_id}", summary="删除记录")
def delete_record(record_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    finance_service.delete_record(db, user.id, record_id)
    dashboard_service.invalidate(user.id)
    return {"deleted": True}
