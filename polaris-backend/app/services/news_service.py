"""新闻资讯抓取服务：通用抓取（RSS）→ 增量去重（url_hash）→ 聚焦抓取（正文补全）。

合规准则（严格遵守）：
1. 不非法侵入：只访问公开可访问的 RSS / 页面，不绕过登录、鉴权与访问控制；
2. 不干扰正常运行：每个源遵守最小抓取间隔（默认 ≥30 分钟），请求串行、超时短、
   单次抓取限量（新条目 ≤ ENRICH_LIMIT 篇做正文补全），UA 声明为个人学习用途；
3. 不破坏技术措施：不识别、不解码、不规避 robots 或反爬机制；若源不可达即跳过；
4. 不损害合法权益：仅缓存标题/摘要/原文链接供个人阅读，正文不对外分发，
   展示时始终引导跳转原始来源，尊重著作权。

三级联动：
- 通用爬虫：按配置的 RSS 源批量发现条目；
- 增量爬虫：以 url_hash 唯一索引去重，只入库"新出现"的条目，避免重复抓取；
- 聚焦爬虫：对本次新增的高价值条目（财经/考研类）回访原文页补全正文与配图。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.news import NewsCrawlLog, NewsItem, NewsSource

logger = logging.getLogger("polaris.news")

UA = "PolarisTerminal/1.0 (personal study aggregator; contact: local-user)"
TIMEOUT = 12.0
ENRICH_LIMIT = 6            # 每次运行最多聚焦抓取正文的条数
MAX_ITEMS_PER_SOURCE = 25   # 每个源单次最多处理条目

# 内置默认源（均为公开 RSS/JSON，经连通性验证，可在源管理中增删停用）
DEFAULT_SOURCES = [
    # 财经
    {"name": "华尔街见闻·快讯", "url": "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30", "category": "财经", "mode": "json"},
    {"name": "新浪财经·要闻", "url": "https://rss.sina.com.cn/roll/finance/hot_roll.xml", "category": "财经", "mode": "rss"},
    {"name": "东方财富·财经", "url": "https://rss.eastmoney.com/rss_partener.xml", "category": "财经", "mode": "rss"},
    # 科技
    {"name": "少数派", "url": "https://sspai.com/feed", "category": "科技", "mode": "rss"},
    {"name": "cnBeta", "url": "https://rss.cnbeta.com.tw/", "category": "科技", "mode": "rss"},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "category": "科技", "mode": "rss"},
    {"name": "Solidot 科学资讯", "url": "https://www.solidot.org/index.rss", "category": "科技", "mode": "rss"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "category": "科技", "mode": "rss"},
    # 学习考研就业
    {"name": "人民网·教育", "url": "http://www.people.com.cn/rss/edu.xml", "category": "考研就业", "mode": "rss"},
    {"name": "人民网·时政", "url": "http://www.people.com.cn/rss/politics.xml", "category": "考研就业", "mode": "rss"},
    {"name": "中国新闻网·滚动", "url": "https://www.chinanews.com.cn/rss/scroll-news.xml", "category": "考研就业", "mode": "rss"},
]

# 历史默认源中已失效/更换的 URL（启动时自动清理）
_OBSOLETE_URLS = {
    "http://www.ftchinese.com/rss/news",
    "https://36kr.com/feed",
    "https://www.eol.cn/rss/kaoyan.xml",
}


def normalize_existing_images(db: Session) -> int:
    """启动迁移：修正历史坏数据中的 image_url（幂等）。

    - 协议相对（//host/...）→ 补 https:
    - 相对路径（无法可靠还原）或占位图 → 置空（前端回退分类占位视觉）
    """
    fixed = 0
    for it in db.scalars(select(NewsItem).where(NewsItem.image_url.isnot(None))).all():
        s = (it.image_url or "").strip()
        if not s:
            continue
        if s.startswith("//"):
            it.image_url = "https:" + s
            fixed += 1
            continue
        low = s.lower()
        if not low.startswith(("http://", "https://")) or any(h in low for h in _PLACEHOLDER_HINTS):
            it.image_url = None
            fixed += 1
    if fixed:
        db.commit()
    return fixed


def ensure_default_sources(db: Session) -> int:
    """注入/更新内置源（幂等）：新增缺失源，清理失效源，修正旧名称。"""
    changed = 0
    # 清理失效源
    for old in db.execute(select(NewsSource).where(NewsSource.url.in_(_OBSOLETE_URLS))).scalars().all():
        db.delete(old)
        changed += 1
    for s in DEFAULT_SOURCES:
        exists = db.execute(select(NewsSource).where(NewsSource.url == s["url"])).scalar_one_or_none()
        if not exists:
            db.add(NewsSource(**s, enabled=True, interval_min=30))
            changed += 1
        elif exists.name != s["name"] or exists.category != s["category"] or exists.mode != s["mode"]:
            # 旧数据修正（如 politics.xml 曾被误命名为"人民网教育"）
            exists.name, exists.category, exists.mode = s["name"], s["category"], s["mode"]
            changed += 1
    if changed:
        db.commit()
    return changed


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8", "ignore")).hexdigest()[:40]


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(html: str | None, limit: int = 400) -> str:
    if not html:
        return ""
    text = unescape(_TAG_RE.sub(" ", html))
    text = _WS_RE.sub(" ", text).strip()
    return text[:limit]


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:25], fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)

# 通用占位图/图标特征（非真实新闻配图），命中则丢弃，避免前端加载出无意义灰图
_PLACEHOLDER_HINTS = ("live-", "placeholder", "default", "/logo", "loading.", "blank.", "icon.")


def _is_real_image(src: str, base: str | None) -> bool:
    """过滤占位图，并把相对/协议相对路径补全为绝对 http(s) URL。返回 '' 表示应丢弃。"""
    if not src:
        return ""
    s = src.strip()
    low = s.lower()
    if low.startswith("data:"):
        return ""
    # 相对路径 / 协议相对路径 → 基于来源 url 补全
    if s.startswith("//") and base:
        s = ("https:" if base.startswith("https") else "http:") + s
    elif not low.startswith(("http://", "https://")) and base:
        s = urljoin(base, s)
    low = s.lower()
    if any(h in low for h in _PLACEHOLDER_HINTS):
        return ""
    return s if low.startswith(("http://", "https://")) else ""


def _first_image(html: str | None, base: str | None = None) -> str | None:
    if not html:
        return None
    for m in _IMG_RE.finditer(html):
        real = _is_real_image(m.group(1), base)
        if real:
            return real
    return None


async def _fetch_rss(client: httpx.AsyncClient, source: NewsSource) -> list[dict]:
    """通用抓取：解析 RSS/Atom，返回条目字典列表。"""
    # 注意：部分源（如东方财富）对 Accept 头返回 406，仅带 UA 最稳妥
    resp = await client.get(source.url, headers={"User-Agent": UA})
    resp.raise_for_status()
    text = resp.text.lstrip("\ufeff")   # 部分源带 UTF-8 BOM，会导致 XML 解析失败
    items: list[dict] = []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        # 部分源带非法字符，做一次宽松清洗再试
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        root = ElementTree.fromstring(cleaned)

    ns_atom = "{http://www.w3.org/2005/Atom}"
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items[:MAX_ITEMS_PER_SOURCE]:
            def g(tag):
                el = it.find(tag)
                return el.text if el is not None else None
            link = (g("link") or "").strip()
            if not link:
                continue
            desc = g("description") or g("{http://purl.org/dc/elements/1.1/}description")
            items.append({
                "title": _clean_text(g("title"), 200) or "(无标题)",
                "url": link,
                "summary": _clean_text(desc),
                "published_at": _parse_dt(g("pubDate") or g("{http://purl.org/dc/elements/1.1/}date")),
                "author": _clean_text(g("author") or g("{http://purl.org/dc/elements/1.1/}creator"), 60),
                "image_url": _first_image(desc, link),
                "raw_html": desc,
            })
    else:  # Atom
        for it in root.findall(f".//{ns_atom}entry")[:MAX_ITEMS_PER_SOURCE]:
            def g(tag):
                el = it.find(f"{ns_atom}{tag}")
                return el.text if el is not None else None
            link_el = it.find(f"{ns_atom}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
            if not link:
                continue
            content = g("content") or g("summary")
            items.append({
                "title": _clean_text(g("title"), 200) or "(无标题)",
                "url": link.strip(),
                "summary": _clean_text(content),
                "published_at": _parse_dt(g("published") or g("updated")),
                "author": _clean_text(g("author"), 60),
                "image_url": _first_image(content, link),
                "raw_html": content,
            })
    return items


async def _fetch_json_feed(client: httpx.AsyncClient, source: NewsSource) -> list[dict]:
    """通用抓取：JSON 快讯接口（华尔街见闻）。"""
    resp = await client.get(source.url, headers={"User-Agent": UA})
    resp.raise_for_status()
    data = resp.json()
    items = []
    for it in (data.get("data", {}).get("items") or [])[:MAX_ITEMS_PER_SOURCE]:
        title = it.get("title") or _clean_text(it.get("content_text", ""), 80)
        uri = it.get("uri") or f"https://wallstreetcn.com/livenews/{it.get('id', '')}"
        if not title or not uri:
            continue
        ts = it.get("display_time")
        items.append({
            "title": _clean_text(title, 200),
            "url": uri,
            "summary": _clean_text(it.get("content_text")),
            "published_at": datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else None,
            "author": "",
            "image_url": None,
            "raw_html": it.get("content_text"),
        })
    return items


async def _enrich(client: httpx.AsyncClient, item: NewsItem) -> None:
    """聚焦抓取：回访原文页，补全正文摘要与配图（失败静默跳过）。"""
    try:
        resp = await client.get(item.url, headers={"User-Agent": UA})
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            return
        html = resp.text
        m = re.search(r"<article[^>]*>([\s\S]*?)</article>", html, re.I)
        if not m:
            m = re.search(r'class="[^"]*(?:content|post-body|article-content|detail-content)[^"]*"[^>]*>([\s\S]{200,}?)</(?:div|article)>',
                         html, re.I)
        body = m.group(1) if m else ""
        text = _clean_text(body, 1200)
        if len(text) > len(item.summary or ""):
            item.content = text
            if not item.summary:
                item.summary = text[:400]
        img = _first_image(body, item.url) or _first_image(html, item.url)
        if img and not item.image_url:
            item.image_url = img[:700]
    except Exception as exc:  # noqa: BLE001
        logger.debug("聚焦抓取失败 %s: %s", item.url, exc)


def _existing_hashes(db: Session, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()
    rows = db.execute(select(NewsItem.url_hash).where(NewsItem.url_hash.in_(hashes))).scalars().all()
    return set(rows)


async def crawl_all(db: Session, force: bool = False) -> dict:
    """执行一轮三级联动抓取，返回统计。"""
    ensure_default_sources(db)
    now = datetime.now()
    sources = db.execute(select(NewsSource).where(NewsSource.enabled == True)).scalars().all()  # noqa: E712
    # 增量节流：未到间隔的源跳过（force 时忽略）
    due = []
    for s in sources:
        if force or not s.last_crawled_at or now - s.last_crawled_at >= timedelta(minutes=s.interval_min):
            due.append(s)

    stats = {"sources": len(due), "found": 0, "new": 0, "enriched": 0, "errors": []}
    found_items: list[tuple[NewsSource, dict]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        # ① 通用抓取（串行限速，避免并发冲击源站）
        for s in due:
            try:
                items = await (_fetch_json_feed(client, s) if s.mode == "json" else _fetch_rss(client, s))
                stats["found"] += len(items)
                for it in items:
                    found_items.append((s, it))
                s.last_crawled_at = now
                db.add(NewsCrawlLog(stage="general", source_name=s.name, found=len(items), ok=True))
            except Exception as exc:  # noqa: BLE001
                stats["errors"].append(f"{s.name}: {type(exc).__name__}")
                db.add(NewsCrawlLog(stage="general", source_name=s.name, ok=False,
                                    message=str(exc)[:480]))
            await asyncio.sleep(0.6)   # 礼貌间隔

        # ② 增量去重入库
        hashes = [_url_hash(it["url"]) for _, it in found_items]
        known = _existing_hashes(db, hashes)
        new_items: list[NewsItem] = []
        seen_batch: set[str] = set()
        for (s, it), h in zip(found_items, hashes):
            if h in known or h in seen_batch:
                continue
            seen_batch.add(h)
            item = NewsItem(
                source_id=s.id, source_name=s.name, category=s.category,
                title=it["title"][:300], url=it["url"][:700], url_hash=h,
                summary=it.get("summary") or None, image_url=(it.get("image_url") or "")[:700] or None,
                author=(it.get("author") or None), published_at=it.get("published_at") or now,
            )
            db.add(item)
            new_items.append(item)
        stats["new"] = len(new_items)
        db.commit()
        for ni in new_items[:1]:
            db.refresh(ni)

        # ③ 聚焦抓取：仅对本次新增的前 ENRICH_LIMIT 条补全正文
        to_enrich = new_items[:ENRICH_LIMIT]
        for item in to_enrich:
            await _enrich(client, item)
            if item.content:
                stats["enriched"] += 1
            await asyncio.sleep(0.5)
        if to_enrich:
            db.add(NewsCrawlLog(stage="focused", source_name=f"{len(to_enrich)} 条新增",
                                new_items=stats["new"], enriched=stats["enriched"], ok=True))
        db.add(NewsCrawlLog(stage="incremental", found=stats["found"], new_items=stats["new"],
                            ok=not stats["errors"], message="; ".join(stats["errors"])[:480] or None))
        db.commit()

    return stats


# ─────────── 查询 ───────────

def list_items(db: Session, category: str | None = None, keyword: str | None = None,
               unread_only: bool = False, starred_only: bool = False,
               limit: int = 30, offset: int = 0) -> dict:
    q = select(NewsItem)
    if category:
        q = q.where(NewsItem.category == category)
    if unread_only:
        q = q.where(NewsItem.is_read == False)  # noqa: E712
    if starred_only:
        q = q.where(NewsItem.is_starred == True)  # noqa: E712
    if keyword:
        like = f"%{keyword}%"
        q = q.where(NewsItem.title.like(like) | NewsItem.summary.like(like))
    total = len(db.execute(q).unique().scalars().all())
    # 可移植排序：NULL 排最后（MySQL 不支持 NULLS LAST）
    rows = db.execute(
        q.order_by(NewsItem.published_at.is_(None), NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return {"total": total, "items": [r.to_dict() for r in rows]}


def get_item(db: Session, item_id: int) -> NewsItem | None:
    return db.get(NewsItem, item_id)


def categories(db: Session) -> list[dict]:
    from sqlalchemy import case, func

    rows = db.execute(
        select(
            NewsItem.category,
            func.count(NewsItem.id),
            func.sum(case((NewsItem.is_read == False, 1), else_=0)),  # noqa: E712
        ).group_by(NewsItem.category)
    ).all()
    return [{"category": c, "count": n, "unread": int(u or 0)} for c, n, u in rows]


def recent_logs(db: Session, limit: int = 10) -> list[dict]:
    rows = db.execute(
        select(NewsCrawlLog).order_by(NewsCrawlLog.id.desc()).limit(limit)
    ).scalars().all()
    return [r.to_dict() for r in rows]
