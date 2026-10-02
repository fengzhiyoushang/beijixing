"""教室课表 Excel 解析检查服务。

职责：
- 批量解析教室课表 Excel（支持两种格式：网格课表 / 平铺表）
- 从文件名、标题单元格、课程格子三处提取教室编码并校验对应关系
- 按规则拆解教室编码：井号前数字=楼号，井号后第一位数字=楼层，末两位=教室序号
- 输出结构化结果（文件名/时间段/课程名/完整编码/楼号/楼层/序号），支持导出 xlsx / json
"""
from __future__ import annotations

import io
import json
import re

from openpyxl import Workbook, load_workbook

# 教室编码：数字#数字（如 6#104、1#106；井号后至少 2 位，取最长串）
ROOM_CODE_RE = re.compile(r"(\d+)#(\d{2,})")
CN_SECTION = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9, "十": 10}


def parse_room_code(code: str) -> dict:
    """拆解教室编码 → {ok, code, building_no, floor, room_seq, error}。

    规则：井号前的数字=楼号；井号后的第一个数字=楼层数；最后两位=教室序号。
    例：6#104 → 6 号楼 / 1 层 / 04 号教室。
    """
    raw = (code or "").strip()
    m = ROOM_CODE_RE.search(raw)
    if not m:
        return {"ok": False, "code": raw, "building_no": None, "floor": None,
                "room_seq": None, "error": f"格式错误的教室编码「{raw}」：应形如 6#104（数字#数字）"}
    b, after = int(m.group(1)), m.group(2)
    if len(after) < 3:
        return {"ok": False, "code": f"{b}#{after}", "building_no": b, "floor": None,
                "room_seq": None,
                "error": f"教室编码「{b}#{after}」井号后不足 3 位，无法按「首位=楼层、末两位=序号」拆解"}
    return {"ok": True, "code": f"{b}#{after}", "building_no": b,
            "floor": int(after[0]), "room_seq": after[-2:], "error": None}


def _codes_in_text(text: str) -> list[str]:
    """提取一段文本中所有教室编码（去重保序）。"""
    out: list[str] = []
    for m in ROOM_CODE_RE.finditer(text or ""):
        c = f"{m.group(1)}#{m.group(2)}"
        if c not in out:
            out.append(c)
    return out


codes_in_text = _codes_in_text


def _code_from_filename(name: str) -> str | None:
    """从文件名猜编码：6104 → 6#104；6#104 / 6号楼308 → 308 缺井号无法确定楼内格式时返回 None。"""
    stem = re.sub(r"\.(xlsx|xls)$", "", name, flags=re.I)
    m = ROOM_CODE_RE.search(stem)
    if m:
        return f"{m.group(1)}#{m.group(2)}"
    # 末尾 4 位数字（如 教室课表6104 / 教室课表6102）：首位=楼号，后三位=教室号
    m = re.search(r"(\d)(\d{3})\s*$", stem)
    if m:
        return f"{m.group(1)}#{m.group(2)}"
    return None


def _norm_weeks(expr: str) -> tuple[str, list[int]]:
    """周次文本 → 表达式 + 周次列表（复用 timeutil，含第N周修复）。"""
    from app.utils.timeutil import parse_weeks
    return expr or "", sorted(parse_weeks(expr))


def _parse_section_ranges(text: str) -> list[tuple[int, int]]:
    """'1-2节' / '3-4节' / '第1节' → [(1,2),(3,4)]。"""
    out = []
    for part in re.split(r"[,，]", (text or "").replace("节", "")):
        part = part.strip().replace("第", "")
        m = re.match(r"^(\d+)(?:-(\d+))?$", part)
        if m:
            a = int(m.group(1))
            b = int(m.group(2) or a)
            out.append((a, b))
    return out


def _parse_cell_block(block: str, weekday: int, section_label: str,
                      time_range: str, filename: str) -> tuple[list[dict], list[str]]:
    """解析网格中的一个课程块：课程名/[老师]/周次/节次/地点（多块以空行分隔）。"""
    errors: list[str] = []
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return [], []
    course = lines[0]
    teacher = weeks = sections_txt = location = ""
    rest = lines[1:]
    # 依次识别：老师（无数字行）、周次（含"周"）、节次（含"节"）、地点（含"#"或"教室"或"校区"）
    for ln in rest:
        if "#" in ln or "校区" in ln or "教室" in ln:
            location = ln
        elif "周" in ln:
            weeks = ln
        elif "节" in ln:
            sections_txt = ln
        elif not teacher:
            teacher = ln
    if not location:
        errors.append(f"课程「{course}」缺少教室地点信息")
        return [], errors
    codes = _codes_in_text(location)
    if not codes:
        errors.append(f"课程「{course}」地点「{location}」中未找到教室编码（形如 6#104）")
        return [], errors
    if len(codes) > 1:
        errors.append(f"课程「{course}」地点包含多个教室编码 {codes}，取第一个")
    code = codes[0]
    parsed = parse_room_code(code)
    if not parsed["ok"]:
        errors.append(parsed["error"])
        return [], errors
    rngs = _parse_section_ranges(sections_txt)
    if not rngs:
        errors.append(f"课程「{course}」节次「{sections_txt or '?'}」无法解析")
        rngs = [(1, 2)]
    weeks_expr, weeks_list = _norm_weeks(weeks.replace("周", ""))
    entries = []
    for ss, es in rngs:
        entries.append({
            "filename": filename,
            "weekday": weekday,
            "weekday_cn": f"星期{'一二三四五六日'[weekday - 1]}",
            "section_label": section_label,
            "time_range": time_range,
            "start_section": ss,
            "end_section": es,
            "course": course,
            "teacher": teacher,
            "weeks": weeks_expr,
            "weeks_list": weeks_list,
            "location_raw": location,
            "room_code": code,
            "building_no": parsed["building_no"],
            "floor": parsed["floor"],
            "room_seq": parsed["room_seq"],
        })
    return entries, errors


def _parse_grid_sheet(ws, filename: str) -> tuple[list[dict], list[str], list[str]]:
    """网格课表：A1 标题（教室：X#YYY），第一列节次，第一行星期。"""
    errors: list[str] = []
    title = str(ws.cell(row=1, column=1).value or "")
    title_codes = _codes_in_text(title)
    if not title_codes:
        errors.append("标题单元格未找到「教室：X#YYY」编码，按格子内地点为准")
    # 星期列
    wd_cols: dict[int, int] = {}
    for col in range(2, ws.max_column + 1):
        v = str(ws.cell(row=2, column=col).value or ws.cell(row=1, column=col).value or "")
        m = re.search(r"星期([一二三四五六日])", v)
        if m:
            wd_cols["一二三四五六日".index(m.group(1)) + 1] = col
    if not wd_cols:
        raise ValueError(f"{filename}：未找到星期列头，不是有效的教室网格课表")
    entries: list[dict] = []
    for row in range(3, ws.max_row + 1):
        label = str(ws.cell(row=row, column=1).value or "")
        if not label.strip():
            continue
        m = re.search(r"\((\d{1,2}:\d{2})-(\d{1,2}:\d{2})\)", label)
        time_range = f"{m.group(1)}-{m.group(2)}" if m else ""
        for wd, col in wd_cols.items():
            cell = ws.cell(row=row, column=col).value
            if cell is None or not str(cell).strip():
                continue
            for block in re.split(r"\n\s*\n", str(cell)):
                if not block.strip():
                    continue
                ents, errs = _parse_cell_block(block, wd, label.strip(), time_range, filename)
                entries.extend(ents)
                errors.extend(errs)
    return entries, title_codes, errors


FLAT_HEADERS = {"课程名": "course", "老师": "teacher", "教室": "location",
                "星期": "weekday", "开始": "start", "结束": "end", "周次": "weeks",
                "开始时间": "start", "结束时间": "end"}
WD_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}


def _parse_flat_sheet(ws, filename: str) -> tuple[list[dict], list[str], list[str]]:
    """平铺表：课程名/老师/教室/星期/开始/结束/周次。"""
    errors: list[str] = []
    header_row = None
    cols: dict[str, int] = {}
    for row in range(1, min(6, ws.max_row) + 1):
        found = {}
        for col in range(1, ws.max_column + 1):
            v = str(ws.cell(row=row, column=col).value or "").strip()
            key = FLAT_HEADERS.get(v)
            if key:
                found[key] = col
        if "course" in found and "location" in found:
            header_row, cols = row, found
            break
    if not header_row:
        raise ValueError(f"{filename}：既不是网格课表也不是平铺表（未找到表头）")
    entries: list[dict] = []
    all_codes: set[str] = set()
    for row in range(header_row + 1, ws.max_row + 1):
        course = str(ws.cell(row=row, column=cols["course"]).value or "").strip()
        if not course or "填写说明" in course:
            continue
        location = str(ws.cell(row=row, column=cols.get("location", 0)).value or "").strip() if "location" in cols else ""
        codes = _codes_in_text(location)
        if not codes:
            errors.append(f"第 {row} 行「{course}」缺少有效教室编码（地点：{location or '空'}）")
            continue
        code = codes[0]
        parsed = parse_room_code(code)
        if not parsed["ok"]:
            errors.append(parsed["error"])
            continue
        all_codes.add(code)
        wd_raw = str(ws.cell(row=row, column=cols["weekday"]).value or "") if "weekday" in cols else ""
        m = re.search(r"(?:星期|周|礼拜)?([一二三四五六日天])", wd_raw)
        weekday = WD_MAP.get(m.group(1)) if m else None
        if not weekday:
            errors.append(f"第 {row} 行「{course}」星期「{wd_raw}」无法解析")
            continue
        weeks_expr, weeks_list = _norm_weeks(str(ws.cell(row=row, column=cols["weeks"]).value or "") if "weeks" in cols else "")
        entries.append({
            "filename": filename,
            "weekday": weekday,
            "weekday_cn": f"星期{'一二三四五六日'[weekday - 1]}",
            "section_label": "",
            "time_range": f"{ws.cell(row=row, column=cols['start']).value or ''}-{ws.cell(row=row, column=cols['end']).value or ''}" if "start" in cols and "end" in cols else "",
            "start_section": None,
            "end_section": None,
            "course": course,
            "teacher": str(ws.cell(row=row, column=cols["teacher"]).value or "").strip() if "teacher" in cols else "",
            "weeks": weeks_expr,
            "weeks_list": weeks_list,
            "location_raw": location,
            "room_code": code,
            "building_no": parsed["building_no"],
            "floor": parsed["floor"],
            "room_seq": parsed["room_seq"],
        })
    return entries, sorted(all_codes), errors


def parse_schedule_files(files: list[tuple[str, bytes]]) -> dict:
    """批量解析教室课表 Excel 文件。

    files: [(原始文件名, 二进制内容)]
    返回：{files: [{filename, room_code, code_source, consistent, entries, errors}],
          summary: {...}}
    """
    results = []
    total_entries = 0
    total_errors = 0
    for name, data in files:
        # 跳过 Excel 打开时产生的临时锁文件（~$xxx.xlsx）
        if name.startswith("~$"):
            continue
        file_errors: list[str] = []
        try:
            wb = load_workbook(io.BytesIO(data), data_only=True)
        except Exception as exc:
            results.append({"filename": name, "room_code": None, "code_source": [],
                            "consistent": False, "entries": [],
                            "errors": [f"文件无法打开（不是有效的 xlsx）：{exc}"]})
            total_errors += 1
            continue
        entries: list[dict] = []
        cell_codes: set[str] = set()
        for ws in wb.worksheets:
            title = str(ws.cell(row=1, column=1).value or "")
            try:
                if "教室课表" in title and _codes_in_text(title):
                    ents, tc, errs = _parse_grid_sheet(ws, name)
                    cell_codes.update(tc)
                else:
                    ents, tc, errs = _parse_flat_sheet(ws, name)
                entries.extend(ents)
                cell_codes.update(e["room_code"] for e in ents)
                file_errors.extend(errs)
            except ValueError as exc:
                file_errors.append(str(exc))
        title_codes = _codes_in_text(str(wb.worksheets[0].cell(row=1, column=1).value or ""))
        name_code = _code_from_filename(name)
        # 三方对应校验：文件名 / 标题 / 格子地点
        sources = {}
        if name_code:
            sources["文件名"] = name_code
        if title_codes:
            sources["标题"] = "/".join(title_codes)
        if cell_codes:
            sources["课程格子"] = "/".join(sorted(cell_codes))
        distinct = {c for c in ([name_code] if name_code else []) + title_codes + sorted(cell_codes)}
        consistent = len(distinct) <= 1
        if len(distinct) > 1:
            file_errors.append(f"教室编码不一致：{'；'.join(f'{k}={v}' for k, v in sources.items())}")
        room_code = next(iter(distinct)) if len(distinct) == 1 else (sorted(cell_codes)[0] if cell_codes else None)
        if not entries and not any("无法打开" in e for e in file_errors):
            file_errors.append("未解析到任何课程条目")
        results.append({
            "filename": name,
            "room_code": room_code,
            "code_source": sources,
            "consistent": consistent,
            "entry_count": len(entries),
            "entries": entries,
            "errors": file_errors,
        })
        total_entries += len(entries)
        total_errors += len(file_errors)
    summary = {
        "file_count": len(results),
        "ok_files": sum(1 for r in results if r["entries"] and not r["errors"]),
        "total_entries": total_entries,
        "total_errors": total_errors,
        "rooms": sorted({r["room_code"] for r in results if r["room_code"]}),
    }
    return {"files": results, "summary": summary}


def build_export_xlsx(result: dict) -> bytes:
    """解析结果导出为 Excel：概览 + 明细 + 错误 三个 sheet。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "概览"
    s = result["summary"]
    ws.append(["文件数", "无异常文件数", "课程条目数", "异常数", "涉及教室"])
    ws.append([s["file_count"], s["ok_files"], s["total_entries"], s["total_errors"],
               "、".join(s["rooms"])])
    ws2 = wb.create_sheet("解析明细")
    headers = ["文件名", "时间段", "星期", "课程名称", "教师", "周次", "完整教室编码",
               "楼号", "楼层", "教室序号", "原始地点"]
    ws2.append(headers)
    for c in ws2[1]:
        from openpyxl.styles import Font
        c.font = Font(bold=True)
    for f in result["files"]:
        for e in f["entries"]:
            ws2.append([e["filename"], e["time_range"] or e["section_label"], e["weekday_cn"],
                        e["course"], e["teacher"], e["weeks"], e["room_code"],
                        e["building_no"], e["floor"], e["room_seq"], e["location_raw"]])
    ws3 = wb.create_sheet("异常")
    ws3.append(["文件名", "错误信息"])
    for f in result["files"]:
        for err in f["errors"]:
            ws3.append([f["filename"], err])
    for col, w in zip("ABCDEFGHIJK", [22, 12, 8, 26, 10, 10, 12, 6, 6, 9, 22]):
        ws2.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_export_json(result: dict) -> bytes:
    return json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
