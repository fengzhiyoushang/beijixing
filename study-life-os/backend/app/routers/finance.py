"""个人财务：流水 CRUD / 月度汇总与学习投入专项 / 趋势 / 预算执行。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas import BudgetIn, FinanceIn, FinancePatchIn
from app.services.dashboard import finance_month_summary
from app.utils.timeutil import month_str, parse_month

router = APIRouter(prefix="/finance", tags=["个人财务"])

STUDY_CATEGORIES = ("学习", "书籍", "课程")


@router.get("/records")
def list_records(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    type: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    q = db.query(m.FinanceRecord).filter(m.FinanceRecord.user_id == user.id)
    if month:
        start, end = parse_month(month)
        q = q.filter(m.FinanceRecord.occurred_at >= start, m.FinanceRecord.occurred_at < end)
    if type:
        q = q.filter(m.FinanceRecord.type == type)
    if category:
        q = q.filter(m.FinanceRecord.category == category)
    if search:
        q = q.filter(m.FinanceRecord.note.contains(search))
    return [r.to_dict() for r in q.order_by(m.FinanceRecord.occurred_at.desc(),
                                            m.FinanceRecord.id.desc()).all()]


@router.post("/records", status_code=201)
def create_record(body: FinanceIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    rec = m.FinanceRecord(
        user_id=user.id, type=body.type, category=body.category, amount=body.amount,
        is_study=body.is_study or body.category in STUDY_CATEGORIES,
        note=body.note, occurred_at=body.occurred_at or date.today(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.to_dict()


@router.put("/records/{rec_id}")
def update_record(rec_id: int, body: FinancePatchIn, db: Session = Depends(get_db),
                  user: m.User = Depends(get_current_user)):
    rec = db.get(m.FinanceRecord, rec_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(rec, k, v)
    db.commit()
    db.refresh(rec)
    return rec.to_dict()


@router.delete("/records/{rec_id}")
def delete_record(rec_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    rec = db.get(m.FinanceRecord, rec_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(rec)
    db.commit()
    return {"deleted": rec_id}


@router.get("/summary")
def summary(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
            db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    month = month or month_str(date.today())
    data = finance_month_summary(db, user.id, month)
    start, end = parse_month(month)
    study_recs = (
        db.query(m.FinanceRecord)
        .filter(m.FinanceRecord.user_id == user.id,
                m.FinanceRecord.type == "expense",
                m.FinanceRecord.occurred_at >= start, m.FinanceRecord.occurred_at < end,
                (m.FinanceRecord.is_study == True)  # noqa: E712
                | m.FinanceRecord.category.in_(STUDY_CATEGORIES))
        .order_by(m.FinanceRecord.amount.desc())
        .limit(10)
        .all()
    )
    data["study_items"] = [r.to_dict() for r in study_recs]
    return data


@router.get("/trend")
def trend(months: int = Query(6, ge=1, le=24),
          db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    today = date.today()
    out = []
    for back in range(months - 1, -1, -1):
        y, mth = today.year, today.month - back
        while mth <= 0:
            mth += 12
            y -= 1
        data = finance_month_summary(db, user.id, f"{y:04d}-{mth:02d}")
        out.append({k: data[k] for k in ("month", "income", "expense", "study_expense")})
    return out


@router.get("/budgets")
def list_budgets(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                 db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    month = month or month_str(date.today())
    budgets = db.query(m.Budget).filter(m.Budget.user_id == user.id, m.Budget.month == month).all()
    summary_data = finance_month_summary(db, user.id, month)
    expense_by_cat = {c["category"]: c["amount"] for c in summary_data["categories"]}
    result = []
    for b in budgets:
        used = summary_data["expense"] if b.category == "*" else expense_by_cat.get(b.category, 0.0)
        d = b.to_dict()
        d["used"] = round(used, 2)
        d["remaining"] = round(b.limit_amount - used, 2)
        d["usage_rate"] = round(used / b.limit_amount, 3) if b.limit_amount else None
        result.append(d)
    return {"month": month, "budgets": result, "summary": summary_data}


@router.post("/budgets", status_code=201)
def upsert_budget(body: BudgetIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    budget = (
        db.query(m.Budget)
        .filter(m.Budget.user_id == user.id, m.Budget.month == body.month,
                m.Budget.category == body.category)
        .first()
    )
    if budget is None:
        budget = m.Budget(user_id=user.id, month=body.month, category=body.category)
    budget.limit_amount = body.limit_amount
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget.to_dict()


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    b = db.get(m.Budget, budget_id)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "预算不存在")
    db.delete(b)
    db.commit()
    return {"deleted": budget_id}
