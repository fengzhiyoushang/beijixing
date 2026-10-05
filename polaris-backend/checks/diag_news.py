"""复现并验证「新闻资讯 - 科技分类点击后空白/同页无内容」问题。

排查思路：
1. 分类统计里「科技」是否真实存在、有多少条
2. 按 category=科技 拉列表，逐条检查返回字段是否完整（id/title/summary/content/url）
3. 模拟前端点击：GET /news/items/{id} 详情，检查返回的正文与原文链接
4. 找出「详情打不开」的具体条目特征
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
c = httpx.Client(timeout=25)

# ── 登录 ──
cred = [{"username": "admin", "password": "admin123"}]
token = None
for body in cred:
    r = c.post(f"{BASE}/api/v1/auth/login", json=body)
    if r.status_code == 200:
        token = r.json()["access_token"]
        print(f"✓ 登录成功（{body['username']}）")
        break
if not token:
    print("✗ 登录失败：", r.status_code, r.text[:200]); sys.exit(1)
H = {"Authorization": f"Bearer {token}"}

# ── 1. 分类统计 ──
cats = c.get(f"{BASE}/api/v1/news/categories", headers=H).json()["items"]
print("\n── 分类统计 ──")
for x in cats:
    print(f"  {x['category']:<10} 总数 {x['count']:<5} 未读 {x['unread']}")

# ── 2. 科技分类列表 ──
print("\n── 科技分类列表 ──")
lst = c.get(f"{BASE}/api/v1/news/items", params={"category": "科技", "limit": 50}, headers=H).json()
print(f"  total={lst['total']}  返回 {len(lst['items'])} 条")
if not lst["items"]:
    print("  ⚠ 科技分类没有任何条目 → 这就是“点进去空白”的直接原因")

# ── 3. 逐条检查字段完整性 ──
print("\n── 条目字段体检（科技）──")
bad_content, bad_url, ok = [], [], 0
for it in lst["items"][:50]:
    iid, title = it["id"], (it.get("title") or "")[:34]
    url = (it.get("url") or "").strip()
    summ = (it.get("summary") or "").strip()
    has_url = url.startswith("http")
    if not has_url:
        bad_url.append((iid, title, url))
    if not summ:
        bad_content.append((iid, title))
    ok += 1

print(f"  返回 {ok} 条 · 缺原文链接 {len(bad_url)} 条 · 缺摘要 {len(bad_content)} 条")
for iid, t, u in bad_url[:8]:
    print(f"    ✗ 无有效链接 id={iid} 「{t}」 url={u!r}")
for iid, t in bad_content[:8]:
    print(f"    ✗ 无摘要 id={iid} 「{t}」")

# ── 4. 逐条拉详情（模拟前端点击）──
print("\n── 详情接口体检（模拟点击）──")
fail = []
for it in lst["items"][:30]:
    iid = it["id"]
    r = c.get(f"{BASE}/api/v1/news/items/{iid}", headers=H)
    if r.status_code != 200:
        fail.append((iid, f"HTTP {r.status_code}", ""))
        continue
    d = r.json()
    body = (d.get("content") or d.get("summary") or "").strip()
    if not body:
        fail.append((iid, "正文与摘要均为空", (d.get("title") or "")[:30]))
print(f"  详情请求 {min(30, len(lst['items']))} 条 · 异常 {len(fail)} 条")
for iid, why, t in fail[:12]:
    print(f"    ✗ id={iid} {why} 「{t}」")

# ── 5. 全局：所有分类的空正文比例 ──
print("\n── 全部分类空正文统计 ──")
allr = c.get(f"{BASE}/api/v1/news/items", params={"limit": 100}, headers=H).json()
empty = [x for x in allr["items"] if not ((x.get("summary") or "").strip())]
print(f"  最新 100 条中：摘要为空 {len(empty)} 条")
by_cat: dict[str, list[int]] = {}
for x in allr["items"]:
    b = by_cat.setdefault(x["category"], [0, 0])
    b[1] += 1
    if not ((x.get("summary") or "").strip()):
        b[0] += 1
for k, (e, n) in sorted(by_cat.items(), key=lambda kv: -kv[1][1]):
    print(f"    {k:<10} 空 {e}/{n}")

print("\n" + ("✅ 未发现空正文条目" if not fail else f"❌ {len(fail)} 条点击后无内容"))
