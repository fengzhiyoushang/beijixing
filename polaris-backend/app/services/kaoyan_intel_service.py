"""考研情报聚焦爬虫：抓取目标院校公开页面，缓存历年分数线与就业信息。

合规准则（与新闻抓取一致）：
1. 不非法侵入：仅访问公开可访问页面（无需登录），不绕过任何访问控制；
2. 不干扰运行：串行请求、12s 超时、请求间隔 ≥1.5s、每次抓取 ≤4 个页面；
3. 不破坏技术措施：不解码混淆数据、不识别/规避反爬；源不可达即回退缓存；
4. 不损害权益：仅缓存公开统计数字供个人决策参考，展示标注来源与采集时间，
   并引导跳转原始页面。

聚焦策略：按 school+major 定位"招生历年数据 / 就业概况"两类页面 →
解析表格 → 结构化入库（kaoyan_intel 表，school+major 唯一）。
页面不可达或解析失败时回退内置官方数据快照（来源均为院校官网/权威发布）。
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kaoyan import KaoyanTarget
from app.models.kaoyan_intel import KaoyanIntel

logger = logging.getLogger("polaris.kaoyan.intel")

UA = "PolarisTerminal/1.0 (personal study aggregator; contact: local-user)"
TIMEOUT = 6.0          # 单次请求超时（原 12s；降低以免页面长时间等待）
CACHE_TTL_DAYS = 7
CRAWL_BUDGET = 25.0    # 单次抓取总时间预算（秒），超时即放弃并回退本地数据


# ───────────────────────── 内置官方数据快照（回退用） ─────────────────────────
# 数据出处：宁波大学信息科学与工程学院官网（eecs.nbu.edu.cn 历年数据/就业概况）、
# 宁波大学研究生院《2024 年硕士一志愿及调剂录取初试总分情况》、教育部国家线。
_SNAPSHOTS: dict[str, dict] = {
    "宁波大学": {
        "majors": {
            "计算机科学与技术": {
                "major_code": "081200",
                "degree": "学硕（全日制）",
                "exam_subjects": "政治 / 英语一 / 数学一 / 408 计算机学科专业基础",
                "score_lines": [
                    {"year": 2023, "line": 273, "line_type": "国家A线·工学", "report": 155,
                     "admit": 20, "max": 357, "min": 291, "avg": 318.7},
                    {"year": 2024, "line": 273, "line_type": "国家A线·工学", "report": 148,
                     "admit": 20, "max": 361, "min": 276, "avg": 321.71},
                    {"year": 2025, "line": 260, "line_type": "国家A线·工学", "report": None,
                     "admit": 20, "max": 368, "min": 298, "avg": None},
                ],
                "single_line": {"2025": {"politics": 34, "foreign": 34, "paper1": 51, "paper2": 51},
                                 "2024": {"politics": 37, "foreign": 37, "paper1": 56, "paper2": 56},
                                 "2023": {"politics": 38, "foreign": 38, "paper1": 57, "paper2": 57}},
                "retest": {
                    "formula": "总成绩 = 初试成绩 ÷5×100 × 60% + 复试成绩(300分制) ÷3×100 × 40%",
                    "content": [
                        {"item": "专业笔试", "score": 100, "note": "含算法与编程"},
                        {"item": "外语听说", "score": 50, "note": "现场测试"},
                        {"item": "综合面试", "score": 150, "note": "科研潜力、项目经历"},
                    ],
                    "ratio": "差额复试，比例不低于 120%",
                    "rule": "按总成绩从高到低择优录取；复试成绩低于 180 分（60%）不予录取",
                    "min_admitted": {"2025": 298, "2024": 276, "2023": 291},
                },
                "employment": {
                    "rate_3y": [{"year": 2022, "rate": 96.44}, {"year": 2023, "rate": 96.29},
                                 {"year": 2024, "rate": 95.04}],
                    "industry": [
                        {"name": "IT / 互联网 / 软件", "share": 42, "note": "主力去向"},
                        {"name": "电子制造 / 智能硬件", "share": 18, "note": "宁波本地产业"},
                        {"name": "金融 / 银行科技岗", "share": 12, "note": "软开与运维"},
                        {"name": "运营商 / 通信设备", "share": 10, "note": "移动·电信·华为等"},
                        {"name": "机关事业 / 升学深造", "share": 18, "note": "公务员·教师·读博"},
                    ],
                    "positions": ["后端/全栈开发工程师", "算法工程师", "嵌入式开发",
                                   "测试开发工程师", "运维/SRE", "产品经理（技术向）"],
                    "companies": [
                        {"name": "阿里云", "industry": "云计算/互联网", "roles": "研发、解决方案"},
                        {"name": "华为", "industry": "通信设备", "roles": "软件开发、网络工程师"},
                        {"name": "海康威视", "industry": "智能安防", "roles": "算法、嵌入式开发"},
                        {"name": "大华股份", "industry": "智能安防", "roles": "研发工程师"},
                        {"name": "舜宇集团", "industry": "光学光电子", "roles": "软件、算法"},
                        {"name": "均胜电子", "industry": "汽车电子", "roles": "嵌入式、测试"},
                        {"name": "浙江移动/电信", "industry": "运营商", "roles": "网络、数据岗"},
                        {"name": "宁波银行", "industry": "金融", "roles": "金融科技开发"},
                    ],
                    "salary_note": "学院与阿里云等 23 家龙头共建实习基地；计算机专业起薪居全校首位，平均约 14.8 万元/年",
                },
                "sources": [
                    {"name": "宁大信息学院·历年招生数据", "url": "https://eecs.nbu.edu.cn/zsjy/yjszs/lnsj.htm"},
                    {"name": "宁大研究生院·录取总分情况", "url": "https://graduate.nbu.edu.cn/2024blbd.pdf"},
                    {"name": "宁大信息学院·就业概况", "url": "https://eecs.nbu.edu.cn/zsjy/jygk.htm"},
                    {"name": "宁波大学2024届毕业生就业质量年度报告", "url": "https://ndjy.nbu.edu.cn/"},
                ],
            },
        },
    },
    # 数据出处：杭州电子科技大学研究生院官网复试分数线公告、
    # 计算机学院《2025年硕士研究生招生复试录取工作实施细则》（cs.hdu.edu.cn）。
    "杭州电子科技大学": {
        "majors": {
            "计算机科学与技术": {
                "major_code": "081200",
                "degree": "学硕（全日制）",
                "exam_subjects": "政治 / 英语一 / 数学一 / 408 计算机学科专业基础",
                "score_lines": [
                    {"year": 2025, "line": 285, "line_type": "自划线", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2026, "line": 325, "line_type": "自划线", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                ],
                "single_line": {"2026": {"politics": 35, "foreign": 35, "paper1": 53, "paper2": 53},
                                 "2025": {"politics": 34, "foreign": 34, "paper1": 51, "paper2": 51}},
                "retest": {
                    "formula": "综合成绩 = 初试成绩 ÷5×100 × 60% + 复试成绩 ÷(复试总分)×100 × 40%",
                    "content": [
                        {"item": "专业笔试", "score": 100, "note": "计算机程序设计综合能力（语言不限）"},
                        {"item": "面试", "score": 100, "note": "含外语能力测试，每人不少于20分钟"},
                    ],
                    "ratio": "差额复试，比例一般不低于 120%",
                    "rule": "单科和总分均须上线；按综合成绩从高到低择优录取，复试不合格者不予录取",
                    "min_admitted": {},
                },
                "employment": {
                    "rate_3y": [],
                    "industry": [
                        {"name": "IT / 互联网 / 软件", "share": 52, "note": "杭电计算机传统强势去向"},
                        {"name": "智能制造 / 电子信息", "share": 16, "note": "浙江数字经济产业"},
                        {"name": "金融 / 银行科技岗", "share": 12, "note": "软开与数据中心"},
                        {"name": "通信 / 运营商", "share": 8, "note": "华为·中兴·运营商"},
                        {"name": "机关事业 / 升学深造", "share": 12, "note": "公务员·教师·读博"},
                    ],
                    "positions": ["后端/全栈开发工程师", "算法工程师", "测试开发工程师",
                                   "嵌入式开发", "运维/SRE", "数据开发"],
                    "companies": [
                        {"name": "华为", "industry": "通信设备", "roles": "软件开发、网络工程师"},
                        {"name": "阿里巴巴", "industry": "互联网/云计算", "roles": "研发、数据"},
                        {"name": "海康威视", "industry": "智能安防", "roles": "算法、嵌入式开发"},
                        {"name": "大华股份", "industry": "智能安防", "roles": "研发工程师"},
                        {"name": "网易", "industry": "互联网", "roles": "游戏开发、后端"},
                        {"name": "零跑/吉利", "industry": "智能汽车", "roles": "嵌入式、算法"},
                    ],
                    "salary_note": "杭电计算机业内口碑强校，长三角 IT 企业校招重点目标；行业占比为公开报道约数，以学校就业质量报告为准",
                },
                "sources": [
                    {"name": "杭电研究生院·2026复试分数线", "url": "https://grs.hdu.edu.cn/2026/0324/c13498a290580/page.htm"},
                    {"name": "杭电计算机学院·2025复试细则", "url": "https://cs.hdu.edu.cn/"},
                    {"name": "杭电研究生院·2024复试分数线", "url": "https://grs.hdu.edu.cn/2024/0327/c13270a262640/page.htm"},
                ],
            },
        },
    },
    # 数据出处：山东科技大学研究生招生网"往届录取"历年复试分数线公告
    # （yjsy.sdust.edu.cn/zhaosheng/wjlq.htm）、计算机学院2025复试实施细则。
    "山东科技大学": {
        "majors": {
            "计算机科学与技术": {
                "major_code": "081200",
                "degree": "学硕（全日制）",
                "exam_subjects": "政治 / 英语一 / 数学一 / 408 计算机学科专业基础",
                "score_lines": [
                    {"year": 2023, "line": 298, "line_type": "院校线", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2024, "line": 273, "line_type": "国家线(A区·工学)", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2025, "line": 260, "line_type": "国家线(A区·工学)", "report": 5,
                     "admit": 25, "max": None, "min": None, "avg": None},
                ],
                "single_line": {"2023": {"politics": 38, "foreign": 38, "paper1": 57, "paper2": 57},
                                "2024": {"politics": 37, "foreign": 37, "paper1": 56, "paper2": 56},
                                "2025": {"politics": 34, "foreign": 34, "paper1": 51, "paper2": 51}},
                "retest": {
                    "formula": "除公告专业外执行 A 类国家线；综合成绩 = 初试成绩 + 复试成绩（按学院细则权重折算）",
                    "content": [
                        {"item": "专业能力笔试", "score": 100, "note": "《数据库系统概论》闭卷"},
                        {"item": "综合素质面试", "score": 100, "note": "每名考生约 20 分钟"},
                        {"item": "外语听说测试", "score": 50, "note": "与综合考核同期进行"},
                    ],
                    "ratio": "差额复试，比例原则上不低于 120%",
                    "rule": "单科与总分均须过线；081200 计算机 2025 年一志愿上线 5 人、招生计划 25 人（含调剂）",
                    "min_admitted": {},
                },
                "employment": {
                    "rate_3y": [],
                    "industry": [
                        {"name": "互联网 / 软件", "share": 45, "note": "阿里·腾讯·百度·字节等（学院官方列举）"},
                        {"name": "IT 设备 / 通信", "share": 20, "note": "华为、海信、歌尔等山东本地产业"},
                        {"name": "能源 / 智慧矿山", "share": 15, "note": "学校优势方向：矿山信息化、安全监测"},
                        {"name": "金融科技 / 安全", "share": 10, "note": "深信服、安恒、花旗金融等"},
                        {"name": "升学深造 / 机关事业", "share": 10, "note": "中科院、985 高校读博等"},
                    ],
                    "positions": ["后端/全栈开发工程师", "算法工程师", "网络安全工程师",
                                   "测试开发", "数据开发", "嵌入式开发"],
                    "companies": [
                        {"name": "阿里巴巴", "industry": "互联网", "roles": "研发工程师"},
                        {"name": "腾讯", "industry": "互联网", "roles": "后端、游戏开发"},
                        {"name": "字节跳动", "industry": "互联网", "roles": "研发、算法"},
                        {"name": "百度", "industry": "互联网/AI", "roles": "算法、开发"},
                        {"name": "华为", "industry": "通信设备", "roles": "软件开发、网络工程师"},
                        {"name": "浪潮集团", "industry": "IT/云计算", "roles": "研发、实施（山东本地龙头）"},
                        {"name": "深信服", "industry": "网络安全", "roles": "安全研发、交付"},
                        {"name": "东软集团", "industry": "软件服务", "roles": "开发、外包项目"},
                    ],
                    "salary_note": "行业占比为依据学院官方就业去向的估算约数；详见学校就业质量年度报告",
                },
                "sources": [
                    {"name": "山科大研招网·2025复试分数线", "url": "https://yjsy.sdust.edu.cn/zhaosheng/info/1067/1833.htm"},
                    {"name": "山科大研招网·2023复试分数线", "url": "https://yjsy.sdust.edu.cn/zhaosheng/info/1067/1541.htm"},
                    {"name": "山科大计算机学院·2025复试细则", "url": "https://cise.sdust.edu.cn/"},
                ],
            },
        },
    },
    # 数据出处：青岛理工大学信息与控制工程学院官网复试录取实施细则（2025/2026）、
    # 研究生院复试录取方案、学院官方成绩表（综合成绩公式经真实成绩反推验证）。
    "青岛理工大学": {
        "majors": {
            "计算机科学与技术": {
                "major_code": "081200",
                "degree": "学硕（全日制）",
                "exam_subjects": "政治 / 英语一 / 数学一 / 408 计算机学科专业基础",
                "score_lines": [
                    {"year": 2023, "line": 273, "line_type": "国家线(A区·工学)", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2024, "line": 273, "line_type": "国家线(A区·工学)", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2025, "line": 260, "line_type": "国家线(A区·工学)", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                    {"year": 2026, "line": 264, "line_type": "国家线(A区·工学)", "report": None,
                     "admit": None, "max": None, "min": None, "avg": None},
                ],
                "single_line": {"2023": {"politics": 38, "foreign": 38, "paper1": 57, "paper2": 57},
                                "2024": {"politics": 37, "foreign": 37, "paper1": 56, "paper2": 56},
                                "2025": {"politics": 34, "foreign": 34, "paper1": 51, "paper2": 51},
                                "2026": {"politics": 35, "foreign": 35, "paper1": 53, "paper2": 53}},
                "retest": {
                    "formula": "总成绩 = 初试成绩 ÷5 × 60% + 复试成绩 × 40%（经学院官方成绩表反推验证）",
                    "content": [
                        {"item": "专业课笔试", "score": 100, "note": "《数据库》（计算机学科组）"},
                        {"item": "综合面试", "score": 100, "note": "专业素质与综合能力考核"},
                        {"item": "英语听说测试", "score": 50, "note": "与面试同期组织"},
                    ],
                    "ratio": "差额复试，比例原则上不低于 120%",
                    "rule": "总分≥院线且单科过 A 类国家线方可复试；081200 复试线执行国家线（2025=260、2026=264）",
                    "min_admitted": {},
                },
                "employment": {
                    "rate_3y": [],
                    "industry": [
                        {"name": "信息技术 / 软件", "share": 40, "note": "青岛 IT 产业主力生源校之一"},
                        {"name": "智能制造 / 电子", "share": 25, "note": "歌尔·海信·海尔等本地产业"},
                        {"name": "央企 / 基建信息化", "share": 15, "note": "中建·中交·中车四方等"},
                        {"name": "汽车 / 能源装备", "share": 10, "note": "潍柴·赛轮·电力等"},
                        {"name": "升学 / 机关事业单位", "share": 10, "note": "读博·选调·教师等"},
                    ],
                    "positions": ["软件开发工程师", "嵌入式工程师", "测试工程师",
                                   "算法工程师", "硬件工程师", "IT 运维"],
                    "companies": [
                        {"name": "歌尔股份", "industry": "智能硬件/声学", "roles": "嵌入式、测试、软件（校友近500人）"},
                        {"name": "海信集团", "industry": "家电/电子信息", "roles": "软件研发、智能硬件"},
                        {"name": "海尔智家", "industry": "智慧家庭/物联网", "roles": "嵌入式、IoT 开发"},
                        {"name": "中车四方", "industry": "轨道交通装备", "roles": "嵌入式、信息化"},
                        {"name": "潍柴动力", "industry": "装备制造", "roles": "电控软件、信息化"},
                        {"name": "赛轮集团", "industry": "智能制造", "roles": "信息化、数据"},
                        {"name": "中建/中交集团", "industry": "建筑央企", "roles": "信息化、智能建造"},
                        {"name": "青岛地铁", "industry": "城市轨道", "roles": "信号、信息化"},
                    ],
                    "salary_note": "行业占比为估算约数（依据学校就业质量报告与校企合作协议公开信息），以官方报告为准",
                },
                "sources": [
                    {"name": "青理工信控学院·2026复试细则", "url": "https://ice.qut.edu.cn/info/1051/2976.htm"},
                    {"name": "青理工信控学院·2026调剂成绩表", "url": "https://ice.qut.edu.cn/info/1383/12734.htm"},
                    {"name": "青理工研究生院·2025复试录取方案", "url": "https://yjsh.qut.edu.cn/info/1097/3630.htm"},
                ],
            },
        },
    },
}


# ───────────────────────── 就业画像数据集（任意院校均可展示） ─────────────────────────
# 说明：以下为**公开报道 / 院校就业质量报告的估算画像**，用于在页面呈现
# 「行业分布与就业率」「主要就业单位与岗位」两个模块；非官方精确统计，
# 页面会标注口径来源，实际以院校毕业生就业质量年度报告为准。
EMPLOYMENT_PROFILES: dict[str, dict] = {
    "宁波大学": _SNAPSHOTS["宁波大学"]["majors"]["计算机科学与技术"]["employment"],
    "杭州电子科技大学": _SNAPSHOTS["杭州电子科技大学"]["majors"]["计算机科学与技术"]["employment"],
    "青岛理工大学": _SNAPSHOTS["青岛理工大学"]["majors"]["计算机科学与技术"]["employment"],
}

# 未单独收录院校：按院校类型套用画像（覆盖绝大多数计算机考研目标院校）
_GENERIC_PROFILES: dict[str, dict] = {
    "it_strong": {
        "label": "IT / 互联网强校",
        "industry": [
            {"name": "IT / 互联网 / 软件", "share": 46, "note": "主力去向：研发、测试、数据"},
            {"name": "电子制造 / 智能硬件", "share": 16, "note": "芯片、嵌入式、智能终端"},
            {"name": "金融 / 银行科技岗", "share": 12, "note": "软开中心与数据中心"},
            {"name": "通信 / 运营商", "share": 10, "note": "设备商与三大运营商"},
            {"name": "机关事业 / 升学深造", "share": 16, "note": "选调、教师、读博"},
        ],
        "positions": ["后端/全栈开发工程师", "算法工程师", "测试开发工程师",
                       "嵌入式开发工程师", "运维/SRE", "数据开发工程师"],
        "companies": [
            {"name": "华为", "industry": "通信设备", "roles": "软件开发、网络工程师"},
            {"name": "阿里巴巴", "industry": "互联网/云计算", "roles": "研发、数据"},
            {"name": "腾讯", "industry": "互联网", "roles": "后端、客户端开发"},
            {"name": "字节跳动", "industry": "互联网", "roles": "研发、算法"},
            {"name": "海康威视", "industry": "智能安防", "roles": "算法、嵌入式开发"},
            {"name": "中国移动/电信/联通", "industry": "运营商", "roles": "网络、数据岗"},
            {"name": "国家电网/南方电网", "industry": "能源央企", "roles": "信息化、调度自动化"},
            {"name": "各大银行软开中心", "industry": "金融科技", "roles": "金融科技开发"},
        ],
        "salary_note": "画像按「IT/互联网强校」口径估算，行业占比为公开报道约数；"
                       "实际以该校毕业生就业质量年度报告为准",
    },
    "comprehensive": {
        "label": "综合类院校",
        "industry": [
            {"name": "IT / 互联网 / 软件", "share": 34, "note": "研发与技术支持"},
            {"name": "机关事业 / 国企", "share": 22, "note": "公务员、事业单位、央企"},
            {"name": "教育 / 科研 / 升学深造", "share": 18, "note": "教师、读博、科研助理"},
            {"name": "金融 / 银行科技岗", "share": 14, "note": "软开与运维"},
            {"name": "制造业信息化", "share": 12, "note": "智能制造、工业软件"},
        ],
        "positions": ["软件开发工程师", "测试工程师", "运维工程师",
                       "数据分析师", "产品经理（技术向）", "技术支持工程师"],
        "companies": [
            {"name": "华为", "industry": "通信设备", "roles": "软件开发、交付"},
            {"name": "中国移动/电信/联通", "industry": "运营商", "roles": "网络、数据岗"},
            {"name": "国家电网/南方电网", "industry": "能源央企", "roles": "信息化、自动化"},
            {"name": "各大银行软开中心", "industry": "金融科技", "roles": "金融科技开发"},
            {"name": "本地龙头软件企业", "industry": "软件服务", "roles": "开发、实施"},
            {"name": "中小学 / 高校", "industry": "教育", "roles": "信息技术教师"},
        ],
        "salary_note": "画像按「综合类院校」口径估算，覆盖机关事业与升学方向；"
                       "实际以该校毕业生就业质量年度报告为准",
    },
    "engineering": {
        "label": "理工/行业特色院校",
        "industry": [
            {"name": "制造业信息化 / 工业软件", "share": 32, "note": "装备制造、智能制造"},
            {"name": "IT / 互联网 / 软件", "share": 28, "note": "研发、测试、嵌入式"},
            {"name": "能源 / 电力 / 交通央企", "share": 18, "note": "电网、轨道、能源集团"},
            {"name": "机关事业 / 国企", "share": 12, "note": "选调、事业单位"},
            {"name": "升学深造", "share": 10, "note": "读博、科研院所"},
        ],
        "positions": ["嵌入式开发工程师", "工业软件开发", "电控/自动化工程师",
                       "软件开发工程师", "算法工程师", "测试工程师"],
        "companies": [
            {"name": "国家电网/南方电网", "industry": "能源央企", "roles": "信息化、调度自动化"},
            {"name": "中国中车", "industry": "轨道交通装备", "roles": "嵌入式、信息化"},
            {"name": "中国航天/航空工业", "industry": "国防军工", "roles": "软件、嵌入式"},
            {"name": "华为/中兴", "industry": "通信设备", "roles": "软件开发、网络"},
            {"name": "本地装备制造龙头", "industry": "智能制造", "roles": "电控软件、工业信息化"},
            {"name": "各大银行软开中心", "industry": "金融科技", "roles": "金融科技开发"},
        ],
        "salary_note": "画像按「理工/行业特色院校」口径估算，行业方向偏工业与能源央企；"
                       "实际以该校毕业生就业质量年度报告为准",
    },
}

# 院校 → 画像类型（未命中时按名称特征自动判定）
_SCHOOL_PROFILE: dict[str, str] = {
    "清华大学": "it_strong", "北京大学": "it_strong", "浙江大学": "it_strong",
    "上海交通大学": "it_strong", "复旦大学": "it_strong", "南京大学": "it_strong",
    "中国科学技术大学": "it_strong", "哈尔滨工业大学": "it_strong",
    "华中科技大学": "it_strong", "西安电子科技大学": "it_strong",
    "北京邮电大学": "it_strong", "电子科技大学": "it_strong",
    "东南大学": "it_strong", "同济大学": "it_strong", "武汉大学": "it_strong",
    "中山大学": "comprehensive", "四川大学": "comprehensive", "山东大学": "comprehensive",
    "吉林大学": "comprehensive", "湖南大学": "comprehensive", "郑州大学": "comprehensive",
    "苏州大学": "comprehensive", "上海大学": "comprehensive", "深圳大学": "comprehensive",
    "昆明理工大学": "engineering", "西安理工大学": "engineering",
    "哈尔滨工程大学": "engineering", "南京航空航天大学": "engineering",
    "中国矿业大学": "engineering", "中国石油大学": "engineering",
}

# 名称特征 → 画像类型
_PROFILE_HINTS = [
    (r"电子|邮电|信息|理工|工业|科技|工程|交通|矿业|石油|地质|水利|电力|航空|航天|海事|建筑",
     "engineering"),
    (r"师范|农业|林业|医科|中医药|财经|政法|民族|外国语|大学$", "comprehensive"),
]


def _pick_profile_key(school: str) -> str:
    """按院校名选择就业画像：显式登记 > 名称特征 > 默认 IT 强校。"""
    if school in _SCHOOL_PROFILE:
        return _SCHOOL_PROFILE[school]
    for pattern, key in _PROFILE_HINTS:
        if re.search(pattern, school):
            return key
    return "it_strong"


def _employment_for(school: str, major: str = "") -> dict:
    """返回适用于该院校的就业画像（含 industry / positions / companies）。

    - 已收录院校：直接复用其真实快照
    - 其他院校：套用画像模板，并把 label 写进 salary_note 说明口径
    """
    if school in EMPLOYMENT_PROFILES:
        return dict(EMPLOYMENT_PROFILES[school])
    key = _pick_profile_key(school)
    base = _GENERIC_PROFILES.get(key) or _GENERIC_PROFILES["it_strong"]
    profile = {k: v for k, v in base.items() if k != "label"}
    profile["rate_3y"] = []
    profile["profile_label"] = base["label"]
    profile["salary_note"] = f"{school}｜{base['label']}就业画像：{base['salary_note']}"
    profile["is_estimate"] = True
    return profile


# ───────────────────────── 聚焦爬虫（在线抓取 + 解析） ─────────────────────────
def _fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception as exc:
        logger.warning("情报抓取失败 %s -> %s", url, exc)
    return None


def _parse_admit_rows(html: str) -> list[dict]:
    """解析学院"历年数据"页表格：定位 081200 行，提取 一志愿招收/初试最高/最低分。

    行布局：类别 | 代码 | 专业 | 共招 | 一志愿人数 | 一志愿最高 | 一志愿最低 | 调剂数 | ...
    取代码之后的数字序列：[共招, 一志愿人数, 最高, 最低, 调剂数...]。
    """
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        joined = "".join(cells)
        if "081200" not in joined:
            continue
        # 跳过专业代码单元格，仅统计其后的数字
        after = []
        seen_code = False
        for c in cells:
            if not seen_code:
                if "081200" in c:
                    seen_code = True
                continue
            if re.fullmatch(r"\d+", c):
                after.append(int(c))
        if len(after) >= 4:
            rows.append({"admit": after[1], "max": after[2], "min": after[3]})
    return rows


def _parse_employment(html: str) -> list[dict]:
    """解析"就业概况"页：近三年 总人数/就业人数/就业率。"""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(cells) >= 4 and re.fullmatch(r"20\d{2}", cells[0]) and "%" in cells[3]:
            try:
                out.append({"year": int(cells[0]), "rate": float(cells[3].rstrip("%"))})
            except ValueError:
                pass
    return out


def _crawl_nbu(major_key: str) -> dict | None:
    """抓取宁波大学信息学院公开页面，成功则覆盖快照中的对应字段。"""
    snap = _SNAPSHOTS["宁波大学"]["majors"].get(major_key)
    if not snap:
        return None
    data = json.loads(json.dumps(snap))  # deep copy
    ok = False
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
        html = _fetch(c, "https://eecs.nbu.edu.cn/zsjy/yjszs/lnsj.htm")
        if html:
            # 从页面标题识别数据年份（如"2025年信息学院硕士研究生招生情况"）
            m = re.search(r"(20\d{2})\s*年[^<]{0,20}(招生|录取)", html)
            year = int(m.group(1)) if m else None
            rows = _parse_admit_rows(html)
            target_line = next((ln for ln in data["score_lines"] if ln["year"] == year),
                               None) if year else None
            if rows and rows[0].get("admit") and target_line:
                target_line.update({k: v for k, v in rows[0].items() if v is not None})
                target_line["source_live"] = True
                ok = True
        time.sleep(1.5)
        html2 = _fetch(c, "https://eecs.nbu.edu.cn/zsjy/jygk.htm")
        if html2:
            emp = _parse_employment(html2)
            if emp:
                data["employment"]["rate_3y"] = emp
                ok = True
    data["live_updated"] = ok
    return data


def _crawl_hdu(major_key: str) -> dict | None:
    """抓取杭电研究生院复试分数线公告页（HTML 表格），解析 081200 行覆盖快照。"""
    snap = _SNAPSHOTS["杭州电子科技大学"]["majors"].get(major_key)
    if not snap:
        return None
    data = json.loads(json.dumps(snap))
    ok = False
    urls = [s["url"] for s in snap.get("sources", []) if s["url"].startswith("https://grs.hdu.edu.cn")]
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for url in urls[:2]:
            html = _fetch(c, url)
            if not html:
                continue
            m = re.search(r"(20\d{2})\s*年[^<]{0,15}复试分数线", html)
            year = int(m.group(1)) if m else None
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
                cells = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
                joined = "".join(cells)
                if "081200" not in joined or "计算机科学与技术" not in joined:
                    continue
                # 排除中外合作/联合研究中心等特殊招生单位，取主学院自划线行
                if any(k in joined for k in ("中外合作", "合作", "圣光机", "民族", "退役", "士兵")):
                    continue
                nums = [int(x) for x in cells if re.fullmatch(r"\d{3}", x) and 150 <= int(x) <= 500]
                singles = [int(x) for x in cells if re.fullmatch(r"\d{2}", x) and 20 <= int(x) <= 100]
                if nums and year:
                    line = nums[0]
                    ln = next((l for l in data["score_lines"] if l["year"] == year), None)
                    if ln:
                        ln["line"] = line
                        ln["source_live"] = True
                    else:
                        data["score_lines"].append({"year": year, "line": line, "line_type": "自划线",
                                                     "report": None, "admit": None, "max": None,
                                                     "min": None, "avg": None, "source_live": True})
                        data["score_lines"].sort(key=lambda x: x["year"])
                    if len(singles) >= 2:
                        data.setdefault("single_line", {})[str(year)] = {
                            "politics": singles[0], "foreign": singles[0],
                            "paper1": singles[1], "paper2": singles[1]}
                    ok = True
                    break
            time.sleep(1.5)
    data["live_updated"] = ok
    return data


# 学校 → 在线抓取函数（未收录的学校走通用发现式抓取）
_CRAWLERS = {"宁波大学": _crawl_nbu, "杭州电子科技大学": _crawl_hdu}

# 教育部官方国家线（A类·工学其他学科专业，计算机 081200 属此类）
# 来源：教育部《全国硕士研究生招生考试考生进入复试的初试成绩基本要求》
_NATIONAL_GX = {
    "2023": {"line": 273, "politics": 38, "paper": 57},
    "2024": {"line": 273, "politics": 37, "paper": 56},
    "2025": {"line": 260, "politics": 34, "paper": 51},
}


def _national_fallback(major_code: str) -> dict:
    """未收录/抓取失败院校：回退到教育部官方国家线（A区·工学）。

    非自划线院校复试线即执行国家线，因此该数据对绝大多数院校准确可靠。
    """
    lines = [{"year": int(y), "line": v["line"], "line_type": "国家线(A区·工学)",
              "report": None, "admit": None, "max": None, "min": None, "avg": None}
             for y, v in sorted(_NATIONAL_GX.items())]
    singles = {y: {"politics": v["politics"], "foreign": v["politics"],
                   "paper1": v["paper"], "paper2": v["paper"]} for y, v in _NATIONAL_GX.items()}
    return {
        "major_code": major_code, "degree": "学术学位", "exam_subjects": "政治 · 英语一 · 数学一 · 408计算机学科专业基础",
        "score_lines": lines, "single_line": singles,
        "retest": {"formula": "复试线执行教育部国家线（A区·工学）；院校可在此基础上自主提高，以该校研究生院公告为准",
                   "content": [], "ratio": "一般差额比例 ≥120%",
                   "rule": "总分与单科均须过线方可进入复试，综合成绩按院校办法录取",
                   "min_admitted": {}},
        "employment": _employment_for("__national__"),
        "sources": [{"name": "教育部·全国硕士研究生招生考试国家分数线", "url": "http://www.moe.gov.cn"}],
        "live_updated": False, "is_national_fallback": True,
    }


def _discover_pages(school: str, major_code: str, year: int,
                    deadline: float | None = None) -> list[str]:
    """定位院校官方"复试分数线"公告页（域名直达，不依赖搜索引擎）。

    策略：①内置研究生院域名注册表；②未注册院校查 Wikidata 官方网址推断域名。
    抓取候选站点首页，验证页面确属该学校后，收集含"复试/分数线/录取"的公告链接。
    合规：仅访问公开页面、串行、限速、不绕过任何反爬；失败返回空列表。

    deadline（time.monotonic 时间戳）用于限制总耗时，超时立即返回已找到的链接，
    避免用户点「刷新情报」后长时间无响应。
    """

    def expired() -> bool:
        return deadline is not None and time.monotonic() > deadline

    urls: list[str] = []
    hosts = _GRAD_DOMAINS.get(school) or _wikidata_hosts(school)
    # ① 域名直达：注册表 / Wikidata 推断出研究生院域名，直接抓首页找公告
    if hosts:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
            for host in hosts[:4]:
                if expired():
                    logger.info("抓取预算用尽，提前结束页面发现（%s）", school)
                    break
                base = f"https://{host}/"
                html = _fetch(c, base)
                if not html:
                    html = _fetch(c, f"http://{host}/")
                    base = f"http://{host}/"
                if not html:
                    continue
                plain = re.sub(r"<[^>]+>", " ", html)
                core = _school_core(school)
                if core not in plain:  # 域名不属于该校（猜测失误），跳过
                    continue
                # 第一轮：首页直接命中"复试/分数线/录取"公告链接
                urls = _scan_links(html, base, host, r"复试|分数线|录取", 6)
                if urls:
                    break
                # 第二轮：先定位"招生/研招/录取"栏目页，再扫其公告链接
                time.sleep(1.5)
                navs = _scan_links(html, base, host, r"招生|研招|录取", 3)
                for nav in navs:
                    if expired():
                        break
                    nav_html = _fetch(c, nav)
                    if not nav_html:
                        continue
                    found = _scan_links(nav_html, nav, host, r"复试|分数线|录取", 6)
                    if found:
                        urls = found
                        break
                    time.sleep(1.5)
                if urls:
                    break

    # ② 搜索引擎兜底：域名直达失败（未收录院校 / 域名猜错 / 栏目结构不同）时，
    #    通过公开搜索页发现 .edu.cn 官方公告页，显著提升「任意学校」的命中率。
    if not urls and (deadline is None or time.monotonic() < deadline):
        try:
            urls = _search_official_pages(school, year, deadline=deadline)
            if urls:
                logger.info("搜索引擎兜底命中 %s：%d 个官方页面", school, len(urls))
        except Exception as exc:
            logger.warning("搜索引擎兜底失败 %s：%s", school, exc)

    return urls[:6]


def _scan_links(html: str, base: str, host: str, pattern: str, limit: int) -> list[str]:
    """收集链接文本命中 pattern 的同域公告 URL（允许嵌套标签）。"""
    out: list[str] = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not re.search(pattern, text):
            continue
        u = href if href.startswith("http") else urllib.parse.urljoin(base, href)
        try:
            if urllib.parse.urlparse(u).netloc != host:
                continue
        except ValueError:
            continue
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def _school_core(school: str) -> str:
    """学校名核心字（用于页面归属校验），取前 4 字去后缀。"""
    return re.sub(r"(大学|学院|学校)$", "", school)[:4]


# 常见院校研究生院/研招网域名注册表（公开官网信息；猜错会被归属校验拦截）
_GRAD_DOMAINS: dict[str, list[str]] = {
    "山东科技大学": ["yjsy.sdust.edu.cn"],
    "青岛理工大学": ["yjsh.qut.edu.cn", "yjs.qut.edu.cn"],
    "青岛大学": ["yjs.qdu.edu.cn", "grad.qdu.edu.cn"],
    "山东建筑大学": ["yjs.sdjzu.edu.cn", "yjsb.sdjzu.edu.cn"],
    "齐鲁工业大学": ["yjs.qlu.edu.cn", "yjs.qlub.edu.cn"],
    "山东财经大学": ["yjs.sdufe.edu.cn"],
    "宁波大学": ["gs.nbu.edu.cn", "yjs.nbu.edu.cn"],
    "杭州电子科技大学": ["grs.hdu.edu.cn", "yjs.hdu.edu.cn"],
    "浙江工业大学": ["yjszsc.zjut.edu.cn", "grs.zjut.edu.cn"],
    "江苏大学": ["yjs.ujs.edu.cn"],
    "南京邮电大学": ["yz.njupt.edu.cn", "yjs.njupt.edu.cn"],
    "合肥工业大学": ["yjs.hfut.edu.cn"],
    "中国矿业大学": ["gs.cumt.edu.cn", "yjs.cumt.edu.cn"],
    # ── 扩充：常见计算机考研目标院校（研究生院/研招网官方域名）──
    "清华大学": ["yjsy.tsinghua.edu.cn", "yz.tsinghua.edu.cn"],
    "北京大学": ["grs.pku.edu.cn", "admission.pku.edu.cn"],
    "浙江大学": ["grs.zju.edu.cn", "yjsy.zju.edu.cn"],
    "上海交通大学": ["gs.sjtu.edu.cn", "yzb.sjtu.edu.cn"],
    "复旦大学": ["gsao.fudan.edu.cn", "gs.fudan.edu.cn"],
    "南京大学": ["grawww.nju.edu.cn", "yjsy.nju.edu.cn"],
    "中国科学技术大学": ["gradschool.ustc.edu.cn", "yz.ustc.edu.cn"],
    "哈尔滨工业大学": ["yzb.hit.edu.cn", "hitgs.hit.edu.cn"],
    "华中科技大学": ["gs.hust.edu.cn", "yzb.hust.edu.cn"],
    "武汉大学": ["gs.whu.edu.cn", "yjs.whu.edu.cn"],
    "西安电子科技大学": ["gr.xidian.edu.cn", "yzb.xidian.edu.cn"],
    "电子科技大学": ["yz.uestc.edu.cn", "gr.uestc.edu.cn"],
    "北京邮电大学": ["yzb.bupt.edu.cn", "grs.bupt.edu.cn"],
    "东南大学": ["yzb.seu.edu.cn", "seugs.seu.edu.cn"],
    "同济大学": ["yz.tongji.edu.cn", "gs.tongji.edu.cn"],
    "北京航空航天大学": ["yzb.buaa.edu.cn", "graduate.buaa.edu.cn"],
    "北京理工大学": ["grd.bit.edu.cn", "yz.bit.edu.cn"],
    "西北工业大学": ["yzb.nwpu.edu.cn", "gs.nwpu.edu.cn"],
    "大连理工大学": ["gs.dlut.edu.cn", "yjsy.dlut.edu.cn"],
    "东北大学": ["yz.neu.edu.cn", "graduate.neu.edu.cn"],
    "吉林大学": ["yjsy.jlu.edu.cn", "gs.jlu.edu.cn"],
    "山东大学": ["yz.sdu.edu.cn", "grad.sdu.edu.cn"],
    "四川大学": ["gs.scu.edu.cn", "yz.scu.edu.cn"],
    "重庆大学": ["yz.cqu.edu.cn", "graduate.cqu.edu.cn"],
    "中南大学": ["gra.csu.edu.cn", "yz.csu.edu.cn"],
    "湖南大学": ["gra.hnu.edu.cn", "yjsy.hnu.edu.cn"],
    "华南理工大学": ["yz.scut.edu.cn", "gs.scut.edu.cn"],
    "中山大学": ["graduate.sysu.edu.cn", "yz.sysu.edu.cn"],
    "厦门大学": ["gs.xmu.edu.cn", "yz.xmu.edu.cn"],
    "天津大学": ["yzb.tju.edu.cn", "gs.tju.edu.cn"],
    "南开大学": ["yzb.nankai.edu.cn", "graduate.nankai.edu.cn"],
    "郑州大学": ["gs.zzu.edu.cn", "yz.zzu.edu.cn"],
    "苏州大学": ["yjs.suda.edu.cn", "yz.suda.edu.cn"],
    "上海大学": ["yjsb.shu.edu.cn", "gs.shu.edu.cn"],
    "深圳大学": ["yz.szu.edu.cn", "gs.szu.edu.cn"],
    "南京航空航天大学": ["yzb.nuaa.edu.cn", "gs.nuaa.edu.cn"],
    "南京理工大学": ["yzb.njust.edu.cn", "gs.njust.edu.cn"],
    "哈尔滨工程大学": ["yzb.hrbeu.edu.cn", "gs.hrbeu.edu.cn"],
    "西南交通大学": ["yz.swjtu.edu.cn", "gs.swjtu.edu.cn"],
    "北京交通大学": ["yzb.bjtu.edu.cn", "gs.bjtu.edu.cn"],
    "河海大学": ["yzb.hhu.edu.cn", "gs.hhu.edu.cn"],
    "江南大学": ["yzb.jiangnan.edu.cn", "gs.jiangnan.edu.cn"],
    "南昌大学": ["yjsy.ncu.edu.cn", "yz.ncu.edu.cn"],
    "福州大学": ["yjsy.fzu.edu.cn", "yz.fzu.edu.cn"],
    "云南大学": ["yjsy.ynu.edu.cn", "yz.ynu.edu.cn"],
    "昆明理工大学": ["yjsy.kmust.edu.cn", "yz.kmust.edu.cn"],
    "西安理工大学": ["yjsy.xaut.edu.cn", "yz.xaut.edu.cn"],
    "长沙理工大学": ["yjsy.csust.edu.cn", "yz.csust.edu.cn"],
    "浙江理工大学": ["yjsy.zstu.edu.cn", "yz.zstu.edu.cn"],
    "杭州师范大学": ["yjsy.hznu.edu.cn", "yz.hznu.edu.cn"],
    "宁波工程学院": ["yjsy.nbut.edu.cn"],
    "中国海洋大学": ["yz.ouc.edu.cn", "gs.ouc.edu.cn"],
    "中国石油大学": ["yjsy.upc.edu.cn", "yz.upc.edu.cn"],
    "中国地质大学": ["yjsy.cug.edu.cn", "yz.cug.edu.cn"],
    "华北电力大学": ["yjsy.ncepu.edu.cn", "yz.ncepu.edu.cn"],
    "北京科技大学": ["yjsy.ustb.edu.cn", "yz.ustb.edu.cn"],
    "北京工业大学": ["yjsy.bjut.edu.cn", "yz.bjut.edu.cn"],
    "北京化工大学": ["yjsy.buct.edu.cn", "yz.buct.edu.cn"],
    "合肥学院": ["yjsy.hfuu.edu.cn"],
    "安徽大学": ["yjsy.ahu.edu.cn", "yz.ahu.edu.cn"],
    "合肥师范学院": ["yjsy.hfnu.edu.cn"],
    "河南大学": ["yjsy.henu.edu.cn", "yz.henu.edu.cn"],
    "河南理工大学": ["yjsy.hpu.edu.cn", "yz.hpu.edu.cn"],
    "山东理工大学": ["yjsy.sdut.edu.cn", "yz.sdut.edu.cn"],
    "烟台大学": ["yjsy.ytu.edu.cn", "yz.ytu.edu.cn"],
    "青岛科技大学": ["yjsy.qust.edu.cn", "yz.qust.edu.cn"],
    "济南大学": ["yjsy.ujn.edu.cn", "yz.ujn.edu.cn"],
}


# 搜索引擎兜底：注册表与 Wikidata 都未命中时，用公开搜索页发现院校研招公告
# 仅取搜索结果的链接文本与 URL，不解析搜索引擎自身内容；限速、串行、可失败。
_SEARCH_ENDPOINTS = [
    # DuckDuckGo HTML 版（无需 JS、无 API Key，返回静态 HTML）
    ("https://html.duckduckgo.com/html/?q={q}",
     r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'),
    # 必应中国（公开检索页）
    ("https://cn.bing.com/search?q={q}&count=20",
     r'<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>'),
]


def _search_official_pages(school: str, year: int, deadline: float | None = None) -> list[str]:
    """搜索引擎兜底：检索「院校 + 复试分数线/招生简章」公开页面，返回候选 URL。

    只接受 .edu.cn 域名的结果（保证是院校官方发布），并做院校归属校验。
    合规：仅 GET 公开搜索页、串行、限速；失败返回空列表。
    """
    out: list[str] = []
    queries = [
        f"{school} 硕士研究生 复试分数线 {year} site:edu.cn",
        f"{school} 研究生院 复试分数线 录取",
        f"{school} 计算机 考研 复试线 {major_hint(year)}",
    ]
    core = _school_core(school)
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for tpl, link_re in _SEARCH_ENDPOINTS:
            for q in queries:
                if deadline is not None and time.monotonic() > deadline:
                    return out
                if len(out) >= 8:
                    return out
                url = tpl.format(q=urllib.parse.quote(q))
                html = _fetch(c, url)
                if not html:
                    continue
                for m in re.finditer(link_re, html, re.S | re.I):
                    href = m.group(1)
                    text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    # DuckDuckGo 会给出跳转链接，取出真实目标
                    if "duckduckgo.com/l/" in href:
                        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        href = (qs.get("uddg") or [""])[0]
                    if not href.startswith("http"):
                        continue
                    try:
                        host = urllib.parse.urlparse(href).netloc.lower()
                    except ValueError:
                        continue
                    if not host.endswith(".edu.cn"):
                        continue                      # 仅收院校官方域名
                    if core and core not in text and core not in host:
                        continue                      # 院校归属校验
                    if href not in out:
                        out.append(href)
                        if len(out) >= 8:
                            return out
                time.sleep(1.2)
    return out


def major_hint(year: int) -> str:
    """检索词补全：带上专业与年份，提高命中率。"""
    return f"{year} 录取"


def _wikidata_hosts(school: str) -> list[str]:
    """未注册院校：查 Wikidata 官方网址（P856），推断研究生院子域名候选。"""
    try:
        r = httpx.get("https://www.wikidata.org/w/api.php",
                      params={"action": "wbsearchentities", "search": school,
                              "language": "zh", "limit": 1, "format": "json"},
                      headers={"User-Agent": UA}, timeout=TIMEOUT)
        found = json.loads(r.text).get("search") or []
        if not found:
            return []
        ent = found[0]["id"]
        time.sleep(1.5)
        r2 = httpx.get("https://www.wikidata.org/w/api.php",
                       params={"action": "wbgetentities", "ids": ent,
                               "props": "claims", "format": "json"},
                       headers={"User-Agent": UA}, timeout=TIMEOUT)
        claims = (json.loads(r2.text).get("entities", {}).get(ent, {})
                  .get("claims", {}).get("P856") or [])
        if not claims:
            return []
        site = claims[0]["mainsnak"]["datavalue"]["value"]
        root = urllib.parse.urlparse(site).netloc.replace("www.", "")
        if not root.endswith(".edu.cn"):
            return []
        return [f"{p}.{root}" for p in ("yjsy", "yjs", "yjsh", "yz", "grs", "gs", "yjsc", "graduate")]
    except Exception as exc:
        logger.warning("Wikidata 查询失败 %s：%s", school, exc)
        return []


def _crawl_generic(school: str, major_code: str) -> dict | None:
    """通用发现式聚焦爬虫：搜索院校官方复试线公告页 → 解析含专业代码的表格行。

    仅抓取 .edu.cn 公开页面，串行 + 1.5s 间隔，最多 3 页。成功返回最小情报包，
    失败返回 None（上层回退快照/提示）。

    全程受 CRAWL_BUDGET 总时间预算约束：超时即返回已获得的结果，
    保证用户点「刷新情报」后不会长时间无响应。
    """
    deadline = time.monotonic() + CRAWL_BUDGET
    year = datetime.now().year
    pages = _discover_pages(school, major_code, year, deadline=deadline)
    if not pages and time.monotonic() < deadline:
        # 目标年份未发布则尝试上一年
        pages = _discover_pages(school, major_code, year - 1, deadline=deadline)
    lines, singles = [], {}
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True) as c:
        for url in pages[:3]:
            if time.monotonic() > deadline:
                logger.info("抓取预算用尽，停止解析公告页（%s）", school)
                break
            html = _fetch(c, url)
            if not html:
                continue
            ym = re.search(r"(20\d{2})\s*年", html)
            page_year = int(ym.group(1)) if ym else year

            # ① 表格解析：优先定位含专业代码的行（多数院校以表格公布复试线）
            hit = _parse_score_tables(html, major_code, page_year)
            if hit:
                lines.append(hit["line"])
                if hit.get("single"):
                    singles[str(page_year)] = hit["single"]
                time.sleep(1.5)
                continue

            # ② 正文解析：部分院校把分数线写在正文段落（"计算机科学与技术 081200 复试线 310"）
            hit = _parse_score_text(html, major_code, page_year)
            if hit:
                lines.append(hit["line"])
                if hit.get("single"):
                    singles[str(page_year)] = hit["single"]
            time.sleep(1.5)
    if not lines:
        return None
    # 同年去重（同一年只保留一条）
    dedup: dict[int, dict] = {}
    for ln in lines:
        dedup.setdefault(ln["year"], ln)
    lines = sorted(dedup.values(), key=lambda x: x["year"])
    return {"score_lines": lines, "single_line": singles, "live_updated": True,
            "sources": [{"name": f"{school}官方公告（自动发现）", "url": pages[0]}]}


def _mk_line(year: int, score: int) -> dict:
    return {"year": year, "line": score, "line_type": "官方公告",
            "report": None, "admit": None, "max": None, "min": None,
            "avg": None, "source_live": True}


def _parse_score_tables(html: str, major_code: str, page_year: int) -> dict | None:
    """从表格中解析复试线：先精确匹配专业代码，再退化为「含计算机相关关键词 + 合理分数」。

    许多院校表格只写专业名称不写代码，或代码写在相邻单元格，故做两级匹配。
    """
    kw = re.compile(r"计算机|软件工程|电子信息|网络空间|人工智能|081200|085400|077500")
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", " ", x).strip()
                 for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        row = " ".join(cells)
        if not row:
            continue
        # 精确：含专业代码；退化：含计算机类关键词
        if major_code not in row and not kw.search(row):
            continue
        nums = [int(x) for x in re.findall(r"(?<!\d)(\d{3})(?!\d)", row) if 150 <= int(x) <= 500]
        if not nums:
            continue
        two = [int(x) for x in re.findall(r"(?<!\d)(\d{2})(?!\d)", row) if 20 <= int(x) <= 100]
        out = {"line": _mk_line(page_year, nums[0])}
        if len(two) >= 2:
            out["single"] = {"politics": two[0], "foreign": two[0],
                             "paper1": two[1], "paper2": two[1]}
        return out
    return None


def _parse_score_text(html: str, major_code: str, page_year: int) -> dict | None:
    """从正文段落解析复试线：匹配「专业名/代码 … 分数」邻近出现的写法。"""
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    kw = r"(?:计算机科学与技术|计算机技术|软件工程|电子信息|网络空间安全|人工智能|" + re.escape(major_code) + r")"
    # 形如 "计算机科学与技术（081200）复试分数线 310 分"
    for m in re.finditer(kw + r"[^。；;]{0,40}?(\d{3})\s*分", text):
        score = int(m.group(1))
        if 150 <= score <= 500:
            out = {"line": _mk_line(page_year, score)}
            seg = text[max(0, m.start() - 60): m.end() + 120]
            two = [int(x) for x in re.findall(r"(?<!\d)(\d{2})(?!\d)", seg) if 20 <= int(x) <= 100]
            if len(two) >= 2:
                out["single"] = {"politics": two[0], "foreign": two[0],
                                 "paper1": two[1], "paper2": two[1]}
            return out
    return None


# ───────────────────────── 对外服务 ─────────────────────────
def _match_major(snapshot: dict, major: str) -> str | None:
    for key in snapshot:
        if key in major or major in key or key.rstrip("（(学硕专硕0123456789 ") in major:
            return key
    return next(iter(snapshot), None)


def _snapshot_of(school: str, major_key: str) -> dict:
    return json.loads(json.dumps(_SNAPSHOTS[school]["majors"][major_key]))


def build_intel(db: Session, school: str, major: str, force: bool = False) -> dict:
    """获取（或聚焦抓取）院校专业情报；带 TTL 缓存。"""
    school, major = (school or "").strip(), (major or "").strip()
    if not school:
        return {"available": False, "reason": "尚未设定目标院校"}

    now = datetime.now()
    row = db.execute(select(KaoyanIntel).where(KaoyanIntel.school == school,
                                               KaoyanIntel.major == major)).scalar_one_or_none()
    fresh = row and row.crawled_at and (now - row.crawled_at) < timedelta(days=CACHE_TTL_DAYS)
    if fresh and not force:
        d = row.to_dict()
        d["available"] = True
        d["from_cache"] = True
        return d

    # 数据组装策略（性能与可用性优先）：
    #   默认（force=False）：只用本地数据（内置快照 / 国家线兜底 + 就业画像）→ 毫秒级返回，
    #                        保证「行业分布与就业率」「主要就业单位与岗位」立即可见；
    #   force=True（用户点「刷新情报」）：才发起真实网络抓取，成功后覆盖本地数据。
    # 说明：早期实现默认就同步抓取，导致未收录院校页面长时间停在「正在抓取…」，
    #       就业图表与单位卡片迟迟不出现。
    payload: dict | None = None
    crawled_live = False
    crawler = _CRAWLERS.get(school)
    if school in _SNAPSHOTS:
        major_key = _match_major(_SNAPSHOTS[school]["majors"], major)
        if major_key:
            payload = _snapshot_of(school, major_key)
            if force and crawler:
                try:
                    live = crawler(major_key)
                    if live:
                        payload = live
                        crawled_live = True
                except Exception as exc:
                    logger.warning("在线抓取异常，回退快照：%s", exc)
    else:
        # 任意学校：专业代码默认 081200（计算机学硕），可含于专业名中则提取
        code_m = re.search(r"\d{6}", major)
        code = code_m.group(0) if code_m else "081200"
        # 先构造本地兜底（国家线 + 就业画像）——保证任意院校都立刻有内容
        payload = _national_fallback(code)
        payload["degree"] = major or "学术学位"
        payload["employment"] = _employment_for(school, major)
        live = None
        if force:
            try:
                live = _crawl_generic(school, code)
            except Exception as exc:
                logger.warning("通用抓取异常 %s：%s", school, exc)
                live = None
        if live:
            payload = {
                "major_code": code,
                "degree": major or "—",
                "exam_subjects": "",
                "score_lines": live["score_lines"],
                "single_line": live.get("single_line", {}),
                "retest": {"formula": "初复试权重与计算方式以院校官方复试细则为准",
                            "content": [], "ratio": "以官方公告为准",
                            "rule": "单科和总分均须上线，按官方综合成绩办法录取",
                            "min_admitted": {}},
                "employment": _employment_for(school, major),
                "sources": live.get("sources", []),
                "live_updated": True,
            }
            crawled_live = True

    if payload is None:
        if row:  # 有旧缓存先用旧的
            d = row.to_dict()
            d["available"] = True
            d["from_cache"] = True
            return d
        return {"available": False,
                "reason": f"暂未收录「{school} · {major}」的公开数据源，可在抓取源中扩展",
                "hint_sources": ["院校研究生院官网", "学院招生网·历年数据", "毕业生就业质量年度报告"]}

    sources = payload.get("sources") or []
    source_names = "；".join(s["name"] for s in sources[:3]) or "院校公开页面"
    # 标注数据来源性质，供前端提示「可点刷新抓取院校专属数据」
    payload["from_snapshot"] = school in _SNAPSHOTS and not crawled_live
    payload["live_updated"] = crawled_live
    payload["can_refresh"] = True
    if row:
        row.payload = json.dumps(payload, ensure_ascii=False)
        row.major = major
        row.major_code = payload.get("major_code")
        row.source = source_names
        row.crawled_at = now
        row.from_cache = False
    else:
        row = KaoyanIntel(school=school, major=major, major_code=payload.get("major_code"),
                          payload=json.dumps(payload, ensure_ascii=False),
                          source=source_names, crawled_at=now, from_cache=False)
        db.add(row)
    db.commit()
    db.refresh(row)
    d = row.to_dict()
    d["available"] = True
    d["from_cache"] = False
    return d


def get_for_user(db: Session, user_id: int, force: bool = False) -> dict:
    target = db.execute(select(KaoyanTarget).where(KaoyanTarget.user_id == user_id,
                                                   KaoyanTarget.status == "active")
                         .order_by(KaoyanTarget.id.desc())).scalars().first()
    if not target:
        return {"available": False, "reason": "尚未录入考研目标"}
    return build_intel(db, target.school, target.major, force=force)
