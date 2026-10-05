"""查看/临时切换考研目标院校，用于验证非宁大院校的情报渲染。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.database import SessionLocal
from app.models.kaoyan import KaoyanTarget

db = SessionLocal()
rows = db.query(KaoyanTarget).all()
print(f"共 {len(rows)} 条考研目标：")
for t in rows:
    print(f"  id={t.id} user={t.user_id} school={t.school!r} major={t.major!r} "
          f"status={getattr(t, 'status', '-')}")
db.close()
