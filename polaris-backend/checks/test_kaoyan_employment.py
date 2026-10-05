"""考研情报：任意院校都必须能产出「行业分布与就业率」「主要就业单位与岗位」数据。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.kaoyan_intel_service import (_employment_for, _pick_profile_key,
                                               _national_fallback)

SCHOOLS = [
    "宁波大学", "杭州电子科技大学", "青岛理工大学",          # 已收录（真实快照）
    "华中科技大学", "西安电子科技大学", "清华大学",            # IT 强校画像
    "郑州大学", "深圳大学", "上海大学",                        # 综合类画像
    "昆明理工大学", "哈尔滨工程大学", "中国矿业大学",          # 理工/行业特色画像
    "某某师范大学", "西南医科大学", "对外经济贸易大学",        # 名称特征兜底
    "塔里木大学",                                              # 未登记 → 默认画像
]

failures = []
print(f"{'院校':<20}{'画像':<22}{'行业项':>6}{'单位':>6}{'岗位':>6}  就业率")
print("─" * 76)
for s in SCHOOLS:
    emp = _employment_for(s)
    ind = emp.get("industry") or []
    comp = emp.get("companies") or []
    pos = emp.get("positions") or []
    rate = emp.get("rate_3y") or []
    label = emp.get("profile_label") or ("已收录快照" if s in ("宁波大学", "杭州电子科技大学", "青岛理工大学") else "-")
    ok = len(ind) > 0 and len(comp) > 0 and len(pos) > 0
    if not ok:
        failures.append(s)
    print(f"{'✓' if ok else '✗'} {s:<18}{label:<22}{len(ind):>6}{len(comp):>6}{len(pos):>6}  "
          f"{('/'.join(str(r['rate']) for r in rate)) if rate else '—'}")

print("\n── 行业占比合计（应接近 100%）──")
for s in ("华中科技大学", "郑州大学", "昆明理工大学"):
    ind = _employment_for(s)["industry"]
    total = sum(x["share"] for x in ind)
    flag = "✓" if 95 <= total <= 105 else "✗"
    if flag == "✗":
        failures.append(f"{s} 占比合计 {total}")
    print(f"{flag} {s}: {total}%")

print("\n── 国家线兜底也必须含就业画像 ──")
nat = _national_fallback("081200")
ok = bool(nat["employment"]["industry"] and nat["employment"]["companies"])
print(f"{'✓' if ok else '✗'} national_fallback employment "
      f"industry={len(nat['employment']['industry'])} companies={len(nat['employment']['companies'])}")
if not ok:
    failures.append("national_fallback employment 为空")

print("\n" + ("✅ 全部通过：任意院校均有行业分布与就业单位数据" if not failures
              else f"❌ 失败：{failures}"))
sys.exit(0 if not failures else 1)
