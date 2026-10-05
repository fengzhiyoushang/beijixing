"""验证考研情报抓取的「时间预算」生效：强制刷新不会无限期挂起。

断言：
1. 未收录院校 force=True 时，请求在 CRAWL_BUDGET + 合理余量内返回
2. 无论抓取成功与否，返回体都含完整 employment（行业/单位/岗位）
3. 默认（force=False）始终毫秒级返回
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

from app.services.kaoyan_intel_service import CRAWL_BUDGET, TIMEOUT

BASE = "http://127.0.0.1:8000"
print(f"配置：TIMEOUT={TIMEOUT}s  CRAWL_BUDGET={CRAWL_BUDGET}s\n")

c = httpx.Client(timeout=180)
r = c.post(f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

orig = c.get(f"{BASE}/api/v1/kaoyan/target", headers=H).json()
SCHOOL = "石河子大学"      # 未收录、无域名注册表 → 会走通用抓取并耗尽预算
c.put(f"{BASE}/api/v1/kaoyan/target", headers=H,
      json={"school": SCHOOL, "major": "计算机科学与技术", "degree_type": "学硕"})

fail = []

# ① 默认：应当很快
t0 = time.time()
d1 = c.get(f"{BASE}/api/v1/kaoyan/intel", headers=H).json()
ms1 = (time.time() - t0) * 1000
ok1 = ms1 < 3000
print(f"{'✓' if ok1 else '✗'} 默认加载（force=False）：{ms1:.0f}ms")
if not ok1:
    fail.append(f"默认加载过慢 {ms1:.0f}ms")

# ② 强制刷新：应受预算约束
t0 = time.time()
d2 = c.get(f"{BASE}/api/v1/kaoyan/intel", params={"force": "true"}, headers=H).json()
sec2 = time.time() - t0
limit = CRAWL_BUDGET + TIMEOUT * 3 + 8      # 预算 + 收尾余量
ok2 = sec2 <= limit
print(f"{'✓' if ok2 else '✗'} 强制刷新（force=True）：{sec2:.1f}s（上限 {limit:.0f}s）")
if not ok2:
    fail.append(f"强制刷新超时 {sec2:.1f}s > {limit:.0f}s")

# ③ 无论哪条路径，employment 都必须完整
for tag, d in (("默认", d1), ("强制", d2)):
    emp = d.get("employment") or {}
    ni, nc, npos = len(emp.get("industry") or []), len(emp.get("companies") or []), len(emp.get("positions") or [])
    ok = ni > 0 and nc > 0 and npos > 0 and d.get("available")
    print(f"{'✓' if ok else '✗'} [{tag}] available={d.get('available')} 行业={ni} 单位={nc} 岗位={npos}")
    if not ok:
        fail.append(f"{tag} 路径 employment 不完整")
    print(f"      来源：{str(d.get('source'))[:70]}")
    print(f"      分数线 {len(d.get('score_lines') or [])} 条 · 兜底={d.get('is_national_fallback')}")

c.put(f"{BASE}/api/v1/kaoyan/target", headers=H,
      json={"school": orig.get("school"), "major": orig.get("major"),
            "degree_type": orig.get("degree_type") or "学硕"})
print(f"\n↺ 已恢复目标院校：{orig.get('school')}")

print("\n" + ("✅ 时间预算与就业数据均正常" if not fail else f"❌ 失败：{fail}"))
sys.exit(0 if not fail else 1)
