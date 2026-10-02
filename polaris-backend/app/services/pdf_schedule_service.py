"""PDF 教室课表解析服务。

解析策略（按优先级）：
1. 文本表格：pdfplumber lines 策略抽网格表（星期 × 节次），逐格解析课程块；
2. 明细清单：识别底部「课程号/课程名/教师/周次/星期/节次/教室」清单表；
3. 纯文本兜底：整页文本按行解析（无表格线时）；
4. 图片型 PDF：渲染页面为图片 → deepseek-vl 识别（需配置 API Key，否则给出明确错误与建议）。

解析结果结构化落库（pdf_schedule_uploads / pdf_schedule_entries），
并提供按教室 / 日期(星期+周次) / 课程类型等条件的查询。
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.course import Semester
from app.models.pdf_schedule import PdfScheduleEntry, PdfScheduleUpload
from app.utils.timeutil import current_week, parse_weeks, section_to_time, to_minutes, weekday_of

logger = logging.getLogger("polaris.pdf_schedule")

MAX_PAGES = 10          # 单文件最多解析页数
MIN_TEXT_CHARS = 40     # 少于该字符数视为图片型 PDF

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
          "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}

ROOM_RE = re.compile(r"教室[:：]\s*([^\s，。;；]+)")
SEMESTER_RE = re.compile(r"(\d{4}\s*[-–—]\s*\d{4}\s*学年第[一二12]学期)")
WEEK_RE = re.compile(r"([\d,，\-]+)\s*周\s*(单|双)?")
SECTION_RE = re.compile(r"第\s*([一二三四五六七八九十]+)\s*小?节")
TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–—~至]\s*(\d{1,2}:\d{2})")
DAY_RE = re.compile(r"星期([一二三四五六日天])")


# ─────────── 上传校验 ───────────
def validate_upload(filename: str | None, content_type: str | None, data: bytes) -> None:
    """安全性校验：扩展名 / MIME / 大小 / PDF 魔数。"""
    name = filename or ""
    if not name.lower().endswith(".pdf"):
        raise AppError("仅支持 PDF 文件（.pdf）")
    if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
        raise AppError(f"文件类型 {content_type} 不是 PDF，已拒绝")
    if len(data) > 20 * 1024 * 1024:
        raise AppError("文件超过 20MB 限制")
    if len(data) < 16 or not data.startswith(b"%PDF"):
        raise AppError("文件内容不是有效的 PDF（缺少 %PDF 头），可能已损坏")


# ─────────── 分类 ───────────
def classify_course(name: str) -> str:
    if any(k in name for k in ("实验", "实训", "实习", "上机")):
        return "实验"
    if "体育" in name:
        return "体育"
    if any(k in name for k in ("设计", "制作", "训练")):
        return "实践"
    if any(k in name for k in ("思政", "形势", "党建", "军事", "心理")):
        return "公共基础"
    return "理论"


# ─────────── 单元格块解析 ───────────
def _parse_cell_block(lines: list[str], wd: int, sec_times: dict[int, tuple[str, str]],
                      row_default: dict | None = None) -> dict | None:
    """解析网格中的一个课程块：课程名 / 教师 / 周次 / 班级 / 节次 / 地点。

    row_default 提供本行的节次与时间（来自左侧表头列），单元格内信息优先级更高。
    """
    rd = row_default or {}
    weeks, week_type = None, "全周"
    ss = rd.get("ss")
    es = rd.get("es", ss)
    cell_time: tuple[str, str] | None = rd.get("time")
    others: list[str] = []
    for l in lines:
        mw = WEEK_RE.search(l)
        ms = SECTION_RE.search(l)
        if mw and re.fullmatch(r"[\d,，\-]+\s*周\s*(单|双)?", l):
            weeks = mw.group(1).replace("，", ",")
            week_type = {"单": "单周", "双": "双周"}.get(mw.group(2), "全周")
        elif ms and re.fullmatch(r"第[\d一二三四五六七八九十]+小?节", l):
            n = CN_NUM.get(ms.group(1))
            if n:
                ss = es = n
        elif ms and re.fullmatch(r"第[\d一二三四五六七八九十]+大节", l):
            n = CN_NUM.get(ms.group(1))  # 大节 n → 小节 2n-1 ~ 2n
            if n:
                ss, es = 2 * n - 1, 2 * n
        elif re.fullmatch(r"[（(]?\d{1,2}:\d{2}\s*[-–—~]\s*\d{1,2}:\d{2}[）)]?", l):
            mt = TIME_RANGE_RE.search(l)  # 节次时间范围
            if mt:
                cell_time = (mt.group(1), mt.group(2))
        else:
            others.append(l)
    if not others:
        return None
    name = others[0]
    teacher = cls = location = None
    for l in others[1:]:
        if re.search(r"(#|楼|馆|区|教室|1教|2教)", l) and location is None:
            location = l
        elif "_" in l and cls is None:
            cls = l
        elif teacher is None and len(l) <= 6 and not re.search(r"\d", l):
            teacher = l
    if cell_time:
        start, end = cell_time
    else:
        start = sec_times.get(ss or 1, (section_to_time(ss or 1),))[0] if ss else "08:00"
        end = (sec_times.get(es or 1) or (None, section_to_time(es or 1)))[-1] or "09:40"
        if es and es in sec_times:
            end = sec_times[es][1]
    return {
        "course_name": name[:128],
        "teacher": (teacher or "")[:64] or None,
        "class_name": cls[:128] if cls else None,
        "weekday": wd,
        "start_section": ss or 1,
        "end_section": max(es or ss or 2, ss or 1),
        "start_time": start,
        "end_time": end,
        "weeks": weeks or "1-16",
        "week_type": week_type,
        "location": location[:128] if location else None,
        "confidence": 0.85,
    }


def _split_blocks(cell: str) -> list[list[str]]:
    """把一个网格单元格的文本拆成若干课程块（空行分隔；无空行则整体一块）。"""
    if not cell or not cell.strip():
        return []
    blocks = re.split(r"\n\s*\n", cell.strip())
    return [[l.strip() for l in b.splitlines() if l.strip()] for b in blocks if b.strip()]


# ─────────── 网格表解析 ───────────
def _try_parse_grid(table: list[list]) -> list[dict]:
    """识别「节次/时间 × 星期」网格表。"""
    if not table or len(table) < 2:
        return []
    header_idx, day_cols = None, {}
    for i, row in enumerate(table[:4]):
        cols = {}
        for j, c in enumerate(row):
            m = DAY_RE.search(str(c or ""))
            if m:
                cols[j] = CN_NUM[m.group(1)]
        if len(cols) >= 5:
            header_idx, day_cols = i, cols
            break
    if header_idx is None:
        return []

    # 节次时间映射（从整表收集 第X小节(hh:mm-hh:mm)）
    sec_times: dict[int, tuple[str, str]] = {}
    for row in table:
        for c in row:
            s = str(c or "")
            m = re.search(r"第\s*([一二三四五六七八九十]+)\s*小?节\s*[（(]?(\d{1,2}:\d{2})\s*[-–—~]\s*(\d{1,2}:\d{2})", s)
            if m and m.group(1) in CN_NUM:
                sec_times[CN_NUM[m.group(1)]] = (m.group(2), m.group(3))

    entries: list[dict] = []
    for row in table[header_idx + 1:]:
        first = str(row[0] or "") if row else ""
        if "课程明细" in first or "未安排" in first:
            break
        # 解析左侧表头列：第X大节/小节 + 时间范围，作为本行默认值
        row_default: dict = {}
        mrow = re.search(r"第\s*([一二三四五六七八九十]+)\s*(大|小)?节", first)
        if mrow and mrow.group(1) in CN_NUM:
            n = CN_NUM[mrow.group(1)]
            if mrow.group(2) == "大":
                row_default["ss"], row_default["es"] = 2 * n - 1, 2 * n
            else:
                row_default["ss"] = row_default["es"] = n
        mt = TIME_RANGE_RE.search(first)
        if mt:
            row_default["time"] = (mt.group(1), mt.group(2))
        for j, wd in day_cols.items():
            cell = row[j] if j < len(row) else None
            if cell is None:
                continue
            for block in _split_blocks(str(cell)):
                parsed = _parse_cell_block(block, wd, sec_times, row_default)
                if parsed:
                    entries.append(parsed)
    return entries


# ─────────── 明细清单解析 ───────────
LIST_HEADER_KEYS = ("课程名", "星期", "节次", "教室")


def _try_parse_list(table: list[list]) -> list[dict]:
    """识别底部课程明细清单：课程号|课程名|课序号|教师|周次|星期|节次|校区|教学楼|教室。"""
    if not table:
        return []
    header_idx, colmap = None, {}
    for i, row in enumerate(table):
        cells = [str(c or "").strip() for c in row]
        if all(k in "".join(cells) for k in LIST_HEADER_KEYS):
            header_idx = i
            for j, c in enumerate(cells):
                if "课程号" in c:
                    colmap[j] = "course_code"
                elif "课程名" in c:
                    colmap[j] = "course_name"
                elif "教师" in c:
                    colmap[j] = "teacher"
                elif "周次" in c:
                    colmap[j] = "weeks"
                elif "星期" in c:
                    colmap[j] = "weekday"
                elif "节次" in c:
                    colmap[j] = "sections"
                elif "教室" in c and "楼" not in c:
                    colmap[j] = "room"
                elif "校区" in c:
                    colmap[j] = "campus"
                elif "教学楼" in c:
                    colmap[j] = "building"
            break
    if header_idx is None or "course_name" not in colmap.values():
        return []

    entries: list[dict] = []
    for row in table[header_idx + 1:]:
        rec = {}
        for j, key in colmap.items():
            v = str(row[j]).strip() if j < len(row) and row[j] is not None else ""
            rec[key] = v
        name = rec.get("course_name")
        if not name:
            continue
        wd = None
        wtxt = rec.get("weekday", "")
        m = DAY_RE.search(wtxt)
        if m:
            wd = CN_NUM[m.group(1)]
        elif wtxt.strip() in CN_NUM:
            wd = CN_NUM[wtxt.strip()]
        ss = es = None
        ms = re.search(r"(\d+)\s*-\s*(\d+)", rec.get("sections", ""))
        if ms:
            ss, es = int(ms.group(1)), int(ms.group(2))
        weeks = rec.get("weeks", "") or "1-16"
        week_type = "全周"
        if "单" in weeks:
            week_type = "单周"
        elif "双" in weeks:
            week_type = "双周"
        weeks = re.sub(r"[单双周\t\s]", "", weeks) or "1-16"
        loc = " ".join(x for x in [rec.get("campus"), rec.get("building"), rec.get("room")] if x) or None
        entries.append({
            "course_name": name[:128],
            "course_code": (rec.get("course_code") or "")[:32] or None,
            "teacher": (rec.get("teacher") or "")[:64] or None,
            "class_name": None,
            "weekday": wd or 1,
            "start_section": ss or 1,
            "end_section": es or ss or 2,
            "start_time": section_to_time(ss or 1),
            "end_time": section_to_time(es or ss or 2),
            "weeks": weeks[:64],
            "week_type": week_type,
            "location": loc[:128] if loc else None,
            "room_no": (rec.get("room") or "")[:64] or None,
            "confidence": 0.9,
        })
    return entries


# ─────────── 节次时间回填（清单表只有节次号时换算）───────────
def _fix_times(e: dict) -> dict:
    if e.get("start_time") in (None, "") or e.get("end_time") in (None, ""):
        e["start_time"] = section_to_time(e["start_section"])
        e["end_time"] = section_to_time(e["end_section"])
    if to_minutes(e["start_time"]) >= to_minutes(e["end_time"]):
        e["end_time"] = section_to_time(e["end_section"] + 1)
    return e


# ─────────── 图片型 PDF：视觉识别 ───────────
VISION_PROMPT = (
    "这是一张高校教室课表图片（网格：列为星期一至星期日，行为各节次；底部可能有课程明细清单）。"
    "请提取所有课程安排，只输出 JSON 数组，不要任何解释文字。每个元素字段："
    '{"course_name":课程名,"teacher":教师,"class_name":班级或教学班,'
    '"weekday":1到7整数,"start_section":起始节次整数,"end_section":结束节次整数,'
    '"weeks":"如1-17或2-16双","location":"地点","room_no":"教室编号"}。'
    "空格子不要输出。"
)


async def _vision_parse(data: bytes) -> tuple[list[dict], str | None]:
    """渲染 PDF 首页为图片 → deepseek-vl 识别。返回 (entries, error)。"""
    from app.ai.deepseek import deepseek

    if not deepseek.is_configured:
        return [], ("该 PDF 为图片扫描件（无文字层），需要 AI 视觉识别；"
                    "服务端未配置 DEEPSEEK_API_KEY，无法识别图片内容")
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            img = pdf.pages[0].to_image(resolution=180).original
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        return [], f"PDF 页面渲染失败：{exc}"

    try:
        text = await deepseek.vision(b64, prompt=VISION_PROMPT, model=None)
    except Exception as exc:
        return [], f"AI 视觉识别调用失败：{exc}"

    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", cleaned, flags=re.S)
    if not m:
        return [], "AI 识别结果无法解析为 JSON"
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], "AI 识别结果 JSON 格式错误"

    entries = []
    for it in items if isinstance(items, list) else []:
        name = str(it.get("course_name") or "").strip()
        if not name:
            continue
        try:
            wd = int(it.get("weekday") or 1)
        except (TypeError, ValueError):
            wd = 1
        entries.append({
            "course_name": name[:128],
            "teacher": (str(it.get("teacher") or "") or None),
            "class_name": (str(it.get("class_name") or "") or None),
            "weekday": min(max(wd, 1), 7),
            "start_section": int(it.get("start_section") or 1),
            "end_section": int(it.get("end_section") or it.get("start_section") or 2),
            "start_time": section_to_time(int(it.get("start_section") or 1)),
            "end_time": section_to_time(int(it.get("end_section") or it.get("start_section") or 2)),
            "weeks": str(it.get("weeks") or "1-16")[:64],
            "week_type": "单周" if "单" in str(it.get("weeks") or "") else
                         "双周" if "双" in str(it.get("weeks") or "") else "全周",
            "location": (str(it.get("location") or "") or None),
            "room_no": (str(it.get("room_no") or "") or None),
            "confidence": 0.6,
        })
    return entries, None


# ─────────── 主解析入口 ───────────
def parse_pdf(data: bytes) -> dict:
    """解析 PDF 文本部分（同步）。返回 {entries, meta, mode, error, suggestions}。"""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        raise AppError("服务端未安装 pdfplumber，无法解析 PDF")

    meta: dict = {"room_no": None, "semester": None}
    all_text: list[str] = []
    grid_entries: list[dict] = []
    list_entries: list[dict] = []
    mode = None
    total_images = 0

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages[:MAX_PAGES]
            if not pages:
                return {"entries": [], "meta": meta, "mode": None,
                        "error": "PDF 没有任何页面", "suggestions": ["请确认文件未损坏后重新上传"]}
            for page in pages:
                text = page.extract_text() or ""
                all_text.append(text)
                total_images += len(page.images)
                for table in page.extract_tables({"vertical_strategy": "lines",
                                                  "horizontal_strategy": "lines"}):
                    if not grid_entries:
                        grid_entries = _try_parse_grid(table)
                        if grid_entries:
                            mode = "table_grid"
                    if not list_entries:
                        list_entries = _try_parse_list(table)
                        if list_entries:
                            mode = mode or "table_list"
    except Exception as exc:
        logger.warning("pdfplumber 解析失败: %s", exc)
        return {"entries": [], "meta": meta, "mode": None,
                "error": f"PDF 解析异常：{exc}",
                "suggestions": ["文件可能损坏或加密，请用 PDF 阅读器确认可以正常打开",
                                "若为加密 PDF，请去除密码后重新上传"]}

    joined = "\n".join(all_text)
    mr = ROOM_RE.search(joined)
    if mr:
        meta["room_no"] = mr.group(1)[:64]
    sr = SEMESTER_RE.search(joined)
    if sr:
        meta["semester"] = re.sub(r"\s+", "", sr.group(1))[:64]

    # 合并策略：网格为主（含星期/节次位置信息），清单补充课程号/教室/地点
    def _norm(name: str) -> str:
        return re.sub(r"[_\s（(].*$", "", name or "")  # 去掉 _01 等教学班后缀

    entries = grid_entries
    if grid_entries and list_entries:
        by_name: dict[str, dict] = {}
        for le in list_entries:
            by_name.setdefault(_norm(le["course_name"]), le)
        for e in entries:
            le = by_name.get(_norm(e["course_name"]))
            if le:
                e["course_code"] = e.get("course_code") or le.get("course_code")
                e["room_no"] = e.get("room_no") or le.get("room_no")
                e["location"] = e.get("location") or le.get("location")
                if not e.get("teacher"):
                    e["teacher"] = le.get("teacher")
        mode = "table_grid+list"
    elif list_entries:
        entries = list_entries
    if entries:
        for e in entries:
            _fix_times(e)
        return {"entries": entries, "meta": meta, "mode": mode, "error": None, "suggestions": []}

    if len(joined.strip()) < MIN_TEXT_CHARS or total_images:
        # 无文字层或课表主体是嵌入图片 → 交给 AI 视觉识别
        return {"entries": [], "meta": meta, "mode": "image_only", "error": "IMAGE_ONLY",
                "suggestions": []}

    return {"entries": [], "meta": meta, "mode": None,
            "error": "未能从 PDF 中识别出课表结构",
            "suggestions": ["确认上传的是「教室课表」而非其它文档",
                            "若课表为合并单元格网格，请尝试导出为带表格线的 PDF 或改用 Excel 导入",
                            "图片型课表需在服务端配置 DEEPSEEK_API_KEY 后由 AI 识别"]}


async def parse_and_store(db: Session, user_id: int, filename: str, data: bytes,
                          stored_path: str | None = None) -> PdfScheduleUpload:
    """解析单个 PDF 并落库（含失败记录，便于前端展示错误与建议）。"""
    result = parse_pdf(data)
    error, suggestions, entries, mode = (result["error"], result["suggestions"],
                                         result["entries"], result["mode"])

    if mode == "image_only":
        entries, error = await _vision_parse(data)
        if entries:
            mode = "vision"
            suggestions = ["AI 识别结果建议人工抽查核对（置信度 0.6）"]
        elif error is None:
            error = "AI 识别未提取到任何课程"
            suggestions = ["请确认图片清晰、课表完整；倾斜或模糊的扫描件识别率较低"]
        else:
            suggestions = ["在服务端 .env 中配置 DEEPSEEK_API_KEY 后重试（图片型 PDF 需要 AI 视觉识别）",
                           "或在本机用 OCR 工具将 PDF 转为文字版后重新上传",
                           "也可改用教务系统导出的 Excel 课表导入"]

    status = "parsed" if entries and not error else ("failed" if not entries else "partial")
    confidence = round(sum(e.get("confidence", 0.8) for e in entries) / len(entries), 3) if entries else 0.0

    upload = PdfScheduleUpload(
        user_id=user_id, filename=filename[:255], stored_path=stored_path,
        file_size=len(data), room_no=result["meta"].get("room_no"),
        semester=result["meta"].get("semester"), parse_mode=mode,
        status=status, error=error, suggestions=json.dumps(suggestions, ensure_ascii=False),
        entry_count=len(entries), confidence=confidence,
    )
    db.add(upload)
    db.flush()
    for e in entries:
        db.add(PdfScheduleEntry(
            upload_id=upload.id,
            course_name=e["course_name"], teacher=e.get("teacher"),
            class_name=e.get("class_name"), course_code=e.get("course_code"),
            weekday=e["weekday"], start_section=e["start_section"], end_section=e["end_section"],
            start_time=e["start_time"], end_time=e["end_time"],
            weeks=e["weeks"], week_type=e["week_type"],
            location=e.get("location"), room_no=e.get("room_no") or upload.room_no,
            confidence=e.get("confidence", 0.8),
        ))
    db.commit()
    db.refresh(upload)
    return upload


# ─────────── 查询 ───────────
def list_uploads(db: Session, user_id: int, limit: int = 50) -> list[PdfScheduleUpload]:
    return (db.query(PdfScheduleUpload)
            .filter(PdfScheduleUpload.user_id == user_id)
            .order_by(PdfScheduleUpload.id.desc()).limit(limit).all())


def get_upload(db: Session, user_id: int, upload_id: int) -> PdfScheduleUpload:
    upload = db.get(PdfScheduleUpload, upload_id)
    if not upload or upload.user_id != user_id:
        raise AppError("上传记录不存在", code="not_found", status_code=404)
    return upload


def delete_upload(db: Session, user_id: int, upload_id: int) -> None:
    upload = get_upload(db, user_id, upload_id)
    db.delete(upload)
    db.commit()


def _active_semester(db: Session, user_id: int) -> Semester | None:
    return db.query(Semester).filter(Semester.user_id == user_id,
                                     Semester.is_current.is_(True)).first()


def query_entries(db: Session, user_id: int, *, room_no: str | None = None,
                  weekday: int | None = None, week: int | None = None,
                  date_: date | None = None, keyword: str | None = None,
                  course_type: str | None = None, upload_id: int | None = None,
                  limit: int = 500) -> dict:
    """按教室 / 日期（或星期+周次）/ 课程类型 / 关键词筛选解析条目。"""
    q = (db.query(PdfScheduleEntry, PdfScheduleUpload.filename)
         .join(PdfScheduleUpload, PdfScheduleEntry.upload_id == PdfScheduleUpload.id)
         .filter(PdfScheduleUpload.user_id == user_id))
    if upload_id:
        q = q.filter(PdfScheduleEntry.upload_id == upload_id)
    if room_no:
        q = q.filter(PdfScheduleEntry.room_no.like(f"%{room_no}%"))
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((PdfScheduleEntry.course_name.like(like)) |
                     (PdfScheduleEntry.teacher.like(like)) |
                     (PdfScheduleEntry.class_name.like(like)))

    # 日期 → 星期 + 教学周
    sem = _active_semester(db, user_id)
    if date_:
        weekday = weekday_of(date_)
        if sem and sem.start_date:
            week = current_week(sem.start_date, date_)
    if weekday:
        q = q.filter(PdfScheduleEntry.weekday == weekday)

    rows = q.order_by(PdfScheduleEntry.weekday, PdfScheduleEntry.start_section).limit(limit).all()
    items = []
    for e, filename in rows:
        if course_type and classify_course(e.course_name) != course_type:
            continue
        active = True
        if week:
            total = sem.total_weeks if sem else 20
            active = week in parse_weeks(e.weeks, total)
        d = e.to_dict()
        d["course_type"] = classify_course(e.course_name)
        d["filename"] = filename
        d["active_this_week"] = active
        items.append(d)
    return {"total": len(items),
            "current_week": (current_week(sem.start_date) if sem and sem.start_date else None),
            "items": items}


def filter_options(db: Session, user_id: int) -> dict:
    """筛选器选项：已解析出的教室 / 课程名 / 教师清单。"""
    rows = (db.query(PdfScheduleEntry)
            .join(PdfScheduleUpload, PdfScheduleEntry.upload_id == PdfScheduleUpload.id)
            .filter(PdfScheduleUpload.user_id == user_id).all())
    rooms = sorted({r.room_no for r in rows if r.room_no})
    courses = sorted({r.course_name for r in rows})
    teachers = sorted({r.teacher for r in rows if r.teacher})
    return {"rooms": rooms, "courses": courses, "teachers": teachers,
            "course_types": ["理论", "实验", "体育", "实践", "公共基础"]}
