"""财务服务：记账、汇总、趋势、预算、学习投入专项分析。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.finance import FinanceBudget, FinanceRecord
from app.utils.timeutil import last_months, month_range, month_str

STUDY_CATEGORIES = {"学习投入", "书籍", "课程", "文具", "考试报名"}


def get_record(db: Session, user_id: int, record_id: int) -> FinanceRecord:
    record = db.get(FinanceRecord, record_id)
    if not record or record.user_id != user_id:
        raise NotFoundError("财务记录不存在")
    return record


def list_records(db: Session, user_id: int, *, month: str | None = None,
                 start: date | None = None, end: date | None = None,
                 category: str | None = None, type_: str | None = None,
                 is_study: bool | None = None, limit: int = 300) -> list[FinanceRecord]:
    query = db.query(FinanceRecord).filter(FinanceRecord.user_id == user_id)
    if month:
        first, last = month_range(month)
        query = query.filter(FinanceRecord.occurred_at >= datetime.combine(first, datetime.min.time()),
                             FinanceRecord.occurred_at < datetime.combine(last, datetime.max.time()))
    if start:
        query = query.filter(FinanceRecord.occurred_at >= datetime.combine(start, datetime.min.time()))
    if end:
        query = query.filter(FinanceRecord.occurred_at <= datetime.combine(end, datetime.max.time()))
    if category:
        query = query.filter(FinanceRecord.category == category)
    if type_:
        query = query.filter(FinanceRecord.type == type_)
    if is_study is not None:
        query = query.filter(FinanceRecord.is_study.is_(is_study))
    return query.order_by(FinanceRecord.occurred_at.desc()).limit(limit).all()


def create_record(db: Session, user_id: int, payload) -> FinanceRecord:
    record = FinanceRecord(
        user_id=user_id,
        type=payload.type,
        category=payload.category,
        amount=payload.amount,
        occurred_at=payload.occurred_at or datetime.now(),
        note=payload.note,
        is_study=payload.is_study or payload.category in STUDY_CATEGORIES,
        payment_method=payload.payment_method,
        related_task_id=payload.related_task_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_record(db: Session, user_id: int, record_id: int, payload) -> FinanceRecord:
    record = get_record(db, user_id, record_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def delete_record(db: Session, user_id: int, record_id: int) -> None:
    record = get_record(db, user_id, record_id)
    db.delete(record)
    db.commit()


# ─────────── 汇总 ───────────
def summary(db: Session, user_id: int, month: str | None = None) -> dict:
    month = month or month_str()
    first, last = month_range(month)
    records = list_records(db, user_id, start=first, end=last, limit=1000)

    income = sum(r.amount for r in records if r.type == "income")
    expense = sum(r.amount for r in records if r.type == "expense")
    study_expense = sum(r.amount for r in records if r.type == "expense" and r.is_study)

    category_map: dict[str, float] = {}
    for r in records:
        if r.type == "expense":
            category_map[r.category] = category_map.get(r.category, 0) + r.amount

    categories = sorted(({"category": k, "amount": round(v, 2)} for k, v in category_map.items()),
                        key=lambda x: -x["amount"])

    # 日均支出 & 记账天数
    days = (min(last, date.today()) - first).days + 1
    spend_days = len({r.occurred_at.date() for r in records if r.type == "expense"})

    return {
        "month": month,
        "income": round(income, 2),
        "expense": round(expense, 2),
        "balance": round(income - expense, 2),
        "study_expense": round(study_expense, 2),
        "study_ratio": round(study_expense / expense, 4) if expense else 0,
        "record_count": len(records),
        "avg_daily_expense": round(expense / days, 2) if days else 0,
        "bookkeeping_days": spend_days,
        "categories": categories,
        "top_category": categories[0] if categories else None,
        "recent": [r.to_dict() for r in records[:10]],
    }


def trend(db: Session, user_id: int, months: int = 6) -> list[dict]:
    out = []
    for month in last_months(months):
        first, last = month_range(month)
        rows = (db.query(FinanceRecord.type, func.sum(FinanceRecord.amount))
                .filter(FinanceRecord.user_id == user_id,
                        FinanceRecord.occurred_at >= datetime.combine(first, datetime.min.time()),
                        FinanceRecord.occurred_at <= datetime.combine(last, datetime.max.time()))
                .group_by(FinanceRecord.type).all())
        study = (db.query(func.sum(FinanceRecord.amount))
                 .filter(FinanceRecord.user_id == user_id, FinanceRecord.is_study.is_(True),
                         FinanceRecord.type == "expense",
                         FinanceRecord.occurred_at >= datetime.combine(first, datetime.min.time()),
                         FinanceRecord.occurred_at <= datetime.combine(last, datetime.max.time()))
                 .scalar() or 0)
        mapping = {t: float(v or 0) for t, v in rows}
        out.append({
            "month": month,
            "income": round(mapping.get("income", 0), 2),
            "expense": round(mapping.get("expense", 0), 2),
            "study_expense": round(float(study), 2),
        })
    return out


# ─────────── 预算 ───────────
def set_budget(db: Session, user_id: int, payload) -> FinanceBudget:
    budget = (db.query(FinanceBudget)
              .filter(FinanceBudget.user_id == user_id, FinanceBudget.month == payload.month,
                      FinanceBudget.category == payload.category).first())
    if budget:
        budget.limit_amount = payload.limit_amount
        budget.note = payload.note
    else:
        budget = FinanceBudget(user_id=user_id, month=payload.month, category=payload.category,
                               limit_amount=payload.limit_amount, note=payload.note)
        db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def list_budgets(db: Session, user_id: int, month: str | None = None) -> list[dict]:
    month = month or month_str()
    budgets = (db.query(FinanceBudget)
               .filter(FinanceBudget.user_id == user_id, FinanceBudget.month == month)
               .order_by(FinanceBudget.category).all())
    first, last = month_range(month)

    used_total = (db.query(func.sum(FinanceRecord.amount))
                  .filter(FinanceRecord.user_id == user_id, FinanceRecord.type == "expense",
                          FinanceRecord.occurred_at >= datetime.combine(first, datetime.min.time()),
                          FinanceRecord.occurred_at <= datetime.combine(last, datetime.max.time()))
                  .scalar() or 0)
    category_rows = (db.query(FinanceRecord.category, func.sum(FinanceRecord.amount))
                     .filter(FinanceRecord.user_id == user_id, FinanceRecord.type == "expense",
                             FinanceRecord.occurred_at >= datetime.combine(first, datetime.min.time()),
                             FinanceRecord.occurred_at <= datetime.combine(last, datetime.max.time()))
                     .group_by(FinanceRecord.category).all())
    used_map = {k: float(v or 0) for k, v in category_rows}

    out = []
    for budget in budgets:
        used = used_total if budget.category == "*" else used_map.get(budget.category, 0)
        out.append(budget.to_dict(used=used))
    return out


def delete_budget(db: Session, user_id: int, budget_id: int) -> None:
    budget = db.get(FinanceBudget, budget_id)
    if not budget or budget.user_id != user_id:
        raise NotFoundError("预算不存在")
    db.delete(budget)
    db.commit()


def study_analysis(db: Session, user_id: int, months: int = 6) -> dict:
    """学习投入专项：总额、占比、明细、月度趋势。"""
    series = trend(db, user_id, months)
    total_study = sum(x["study_expense"] for x in series)
    total_expense = sum(x["expense"] for x in series)
    items = [r.to_dict() for r in
             list_records(db, user_id, is_study=True, limit=20)]
    return {
        "months": series,
        "total_study_expense": round(total_study, 2),
        "total_expense": round(total_expense, 2),
        "study_ratio": round(total_study / total_expense, 4) if total_expense else 0,
        "monthly_avg": round(total_study / months, 2) if months else 0,
        "items": items,
    }
