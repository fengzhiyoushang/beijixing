"""AI 路由：对话、SSE 流式、会话管理、工具清单与直调、向量索引维护。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai import rag
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.ai import ChatIn, LlmCfgIn, LlmTestIn, ToolCallIn
from app.services import ai_config_service, ai_service

logger = logging.getLogger("polaris.ai.router")
router = APIRouter(prefix="/ai", tags=["⑫ AI 助手"])


# ─────────── 对话 ───────────
@router.post("/chat", summary="对话（支持 Function Call 与 RAG 增强）")
async def chat(body: ChatIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    return await ai_service.chat(db, user, body)


@router.post("/chat/stream", summary="流式对话（SSE：meta → tool* → token* → done）")
async def chat_stream(body: ChatIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> StreamingResponse:
    user_id = user.id

    async def event_source():
        # 流式响应期间使用独立会话，避免请求会话提前关闭
        session = SessionLocal()
        try:
            current_user = session.get(User, user_id)
            if current_user is None:
                yield _sse("error", {"message": "用户不存在"})
                return
            async for event in ai_service.stream_chat(session, current_user, body):
                yield _sse(event["event"], event["data"])
        except Exception as exc:                 # pragma: no cover
            logger.exception("SSE 流式对话异常")
            yield _sse("error", {"message": str(exc)})
        finally:
            session.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ─────────── 会话 ───────────
@router.get("/sessions", summary="会话列表")
def list_sessions(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    sessions = ai_service.list_sessions(db, user.id, limit=limit)
    return {"total": len(sessions), "items": [s.to_dict() for s in sessions]}


@router.post("/sessions", summary="新建会话")
def create_session(title: str | None = Query(default=None), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    return ai_service.ensure_session(db, user.id, title=title).to_dict()


@router.get("/sessions/{session_id}", summary="会话详情（含消息）")
def get_session(session_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    return ai_service.get_session(db, user.id, session_id).to_dict(with_messages=True)


@router.delete("/sessions/{session_id}", summary="删除会话")
def delete_session(session_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    ai_service.delete_session(db, user.id, session_id)
    return {"deleted": True}


# ─────────── 工具 ───────────
@router.get("/tools", summary="可用工具清单（Function Call schema）")
def list_tools(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    specs = ai_service.list_tool_specs()
    return {"total": len(specs),
            "items": [{"name": s["function"]["name"], "description": s["function"]["description"],
                       "parameters": s["function"]["parameters"]} for s in specs]}


@router.post("/tools/call", summary="直接调用工具（不经过模型，便于调试/前端直连）")
async def call_tool(body: ToolCallIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    return await ai_service.call_tool(db, user, body.name, body.arguments)


# ─────────── 状态与索引 ───────────
@router.get("/status", summary="AI 运行状态（是否配置 Key、模型、向量 provider）")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from app.core.config import settings
    from app.ai.deepseek import deepseek

    return {
        "ai": deepseek.status(),
        "embedding": {"provider": settings.EMBEDDING_PROVIDER, "dim": settings.EMBEDDING_DIM},
        "rag": {"chunk_size": settings.RAG_CHUNK_SIZE, "overlap": settings.RAG_CHUNK_OVERLAP,
                "top_k": settings.RAG_TOP_K},
        "max_tool_rounds": settings.MAX_TOOL_ROUNDS,
    }


# ─────────── 模型配置与 Token 用量 ───────────
@router.get("/config", summary="获取当前用户的大模型配置（Key 脱敏）与运行状态")
def get_config(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    from app.ai.deepseek import deepseek

    cfg = ai_config_service.get_llm_cfg(user)
    return {"config": ai_config_service.public_cfg(user), "status": deepseek.status(cfg)}


@router.put("/config", summary="保存大模型配置（api_key 留空=不修改）")
def save_config(body: LlmCfgIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    data = body.model_dump(exclude_unset=True)
    # api_key 传空字符串视为保持原值（前端脱敏展示无法回填）；显式清除用 null
    if data.get("api_key") == "":
        data.pop("api_key")
    ai_config_service.set_llm_cfg(db, user, data)
    return {"config": ai_config_service.public_cfg(user)}


@router.post("/config/test", summary="测试模型连接（真实小请求，用量计入台账）")
async def test_config(body: LlmTestIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> dict:
    from app.ai.deepseek import deepseek

    stored = ai_config_service.get_llm_cfg(user)
    submitted = body.model_dump(exclude_unset=True)
    # 测试用"表单值优先、已存值兜底"的合并配置（Key 留空则用已保存的 Key）
    cfg = {**stored, **{k: v for k, v in submitted.items() if v not in (None, "")}}
    result = await deepseek.test_connection(cfg)
    usage = result.get("usage")
    if usage:
        ai_service.record_usage(db, user.id, None,
                                result.get("model") or cfg.get("model"), usage)
        result["usage"] = None  # 不回传细节，前端刷新汇总即可
        result["recorded"] = True
    return result


@router.get("/usage", summary="Token 真实用量汇总（累计/今日/周/月/按模型/剩余）")
def get_usage(db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict:
    cfg = ai_config_service.get_llm_cfg(user)
    return ai_config_service.usage_summary(db, user.id, quota=int(cfg.get("quota") or 0))


@router.get("/usage/recent", summary="最近用量明细")
def get_recent_usage(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    return {"items": ai_config_service.recent_usage(db, user.id, limit=limit)}


@router.post("/reindex", summary="重建当前用户全部文档的向量索引")
async def reindex(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from app.services import knowledge_service

    docs = knowledge_service.list_docs(db, user.id, limit=1000)
    results = []
    for doc in docs:
        try:
            results.append(await rag.build_index(db, doc))
        except Exception as exc:                 # pragma: no cover
            results.append({"doc_id": doc.id, "error": str(exc)[:120]})
    return {"documents": len(docs), "results": results}
