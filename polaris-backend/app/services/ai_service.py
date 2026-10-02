"""AI 服务层：会话管理、Function Call 循环、流式对话、工具直调。"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai import prompts, tools
from app.ai.deepseek import deepseek
from app.ai.rag import build_context, search
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.ai import AiMessage, AiSession

logger = logging.getLogger("polaris.ai.service")


# ─────────── 会话 ───────────
def ensure_session(db: Session, user_id: int, session_id: int | None = None,
                   title: str | None = None, channel: str = "web") -> AiSession:
    if session_id:
        session = db.get(AiSession, session_id)
        if not session or session.user_id != user_id:
            raise NotFoundError("会话不存在")
        return session
    session = AiSession(user_id=user_id, title=(title or "新会话")[:120], channel=channel)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, user_id: int, limit: int = 30) -> list[AiSession]:
    return (db.query(AiSession)
            .filter(AiSession.user_id == user_id)
            .order_by(AiSession.updated_at.desc()).limit(limit).all())


def get_session(db: Session, user_id: int, session_id: int, *, with_messages: bool = True) -> AiSession:
    session = db.get(AiSession, session_id)
    if not session or session.user_id != user_id:
        raise NotFoundError("会话不存在")
    return session


def delete_session(db: Session, user_id: int, session_id: int) -> None:
    session = get_session(db, user_id, session_id)
    db.delete(session)
    db.commit()


def save_message(db: Session, session: AiSession, role: str, content: str | None,
                 *, tool_calls: list | None = None, tool_name: str | None = None) -> AiMessage:
    message = AiMessage(session_id=session.id, role=role, content=content,
                        tool_calls=tool_calls or [], tool_name=tool_name,
                        tokens=len(content or "") // 2)
    db.add(message)
    session.message_count = (session.message_count or 0) + 1
    session.updated_at = datetime.now()
    db.commit()
    db.refresh(message)
    return message


# ─────────── 消息组装 ───────────
def system_prompt(user) -> str:
    config = user.config or {}
    return prompts.SYSTEM_ASSISTANT.format(
        now=datetime.now().strftime("%Y-%m-%d %H:%M %A"),
        nickname=user.nickname or user.username,
        school=config.get("school", "华中科技大学"),
        role=config.get("role", "考研备战中"),
    )


def build_messages(db: Session, user, session: AiSession, question: str, *,
                   use_rag: bool = False, custom_system: str | None = None,
                   history_limit: int = 10) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": custom_system or system_prompt(user)}]

    history = (db.query(AiMessage)
               .filter(AiMessage.session_id == session.id, AiMessage.role.in_(["user", "assistant"]))
               .order_by(AiMessage.id.desc()).limit(history_limit).all())
    for msg in reversed(history):
        if msg.content:
            messages.append({"role": msg.role, "content": msg.content})

    if use_rag:
        hits = search(db, user.id, question, top_k=settings.RAG_TOP_K)
        if hits:
            messages.append({
                "role": "system",
                "content": "以下是从用户知识库检索到的片段，回答时优先使用并可标注 [资料N]：\n"
                           + build_context(hits, limit=3000),
            })

    messages.append({"role": "user", "content": question})
    return messages


# ─────────── 工具循环 ───────────
async def run_tool_loop(db: Session, user, messages: list[dict], *, use_tools: bool = True,
                        temperature: float = 0.7, on_trace=None) -> tuple[dict, list[dict]]:
    """执行 Function Call 循环，返回 (最终消息, 工具轨迹)。"""
    traces: list[dict] = []
    if not use_tools:
        return await deepseek.chat(messages, temperature=temperature), traces

    tool_specs = tools.specs()
    last_message: dict = {}
    for round_index in range(settings.MAX_TOOL_ROUNDS):
        last_message = await deepseek.chat(messages, tools=tool_specs, temperature=temperature)
        calls = last_message.get("tool_calls") or []
        if not calls:
            return last_message, traces

        messages.append({
            "role": "assistant",
            "content": last_message.get("content"),
            "tool_calls": calls,
        })
        for call in calls:
            name = (call.get("function") or {}).get("name", "")
            raw_args = (call.get("function") or {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            result = await tools.execute(db, user, name, args)
            trace = {"round": round_index + 1, "name": name, "arguments": args,
                     "ok": result.get("ok", True) if isinstance(result, dict) else True,
                     "result": result}
            traces.append(trace)
            if on_trace:
                on_trace(trace)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id") or f"call_{round_index}_{name}",
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str)[:6000],
            })

    # 达到最大轮次：关闭工具做最终收敛
    logger.info("工具轮次达到上限 %s，进行最终收敛", settings.MAX_TOOL_ROUNDS)
    final = await deepseek.chat(messages, tools=None, temperature=temperature)
    return final, traces


# ─────────── 对话（非流式） ───────────
async def chat(db: Session, user, payload) -> dict:
    session = ensure_session(db, user.id, payload.session_id,
                             title=payload.message[:40], channel="web")
    if session.message_count == 0:
        session.title = payload.message[:40]
        db.commit()

    save_message(db, session, "user", payload.message)
    messages = build_messages(db, user, session, payload.message, use_rag=payload.use_rag,
                              custom_system=payload.system)
    message, traces = await run_tool_loop(db, user, messages, use_tools=payload.use_tools,
                                          temperature=payload.temperature)
    reply = message.get("content") or "（模型未返回内容）"
    save_message(db, session, "assistant", reply)

    return {
        "session_id": session.id,
        "reply": reply,
        "tool_traces": traces,
        "ai_mode": "live" if deepseek.is_configured else "mock",
        "message_count": session.message_count,
    }


# ─────────── 对话（SSE 流式） ───────────
async def stream_chat(db: Session, user, payload) -> AsyncGenerator[dict, None]:
    """产出事件：meta → (tool)* → token* → done | error"""
    session = ensure_session(db, user.id, payload.session_id,
                             title=payload.message[:40], channel="web")
    save_message(db, session, "user", payload.message)
    yield {"event": "meta", "data": {"session_id": session.id,
                                     "mode": "live" if deepseek.is_configured else "mock"}}

    messages = build_messages(db, user, session, payload.message, use_rag=payload.use_rag,
                              custom_system=payload.system)
    queue: list[dict] = []

    def on_trace(trace: dict) -> None:
        queue.append(trace)

    try:
        message, _ = await run_tool_loop(db, user, messages, use_tools=payload.use_tools,
                                         temperature=payload.temperature, on_trace=on_trace)
        for trace in queue:
            yield {"event": "tool", "data": trace}

        answer = message.get("content")
        if not answer:
            # 工具执行完毕但无自然语言结论 → 追加一轮流式生成
            messages.append({"role": "system",
                             "content": "请基于以上工具返回的数据，用中文简洁总结并给出建议。"})
            async for chunk in deepseek.stream_chat(messages, temperature=payload.temperature):
                if chunk["type"] == "token":
                    yield {"event": "token", "data": {"content": chunk["content"]}}
                elif chunk["type"] == "error":
                    yield {"event": "error", "data": {"message": chunk["message"]}}
                elif chunk["type"] == "done":
                    answer = chunk.get("content") or ""
        else:
            # 已有完整结论：分块吐出以获得打字机效果
            import asyncio

            for i in range(0, len(answer), 8):
                yield {"event": "token", "data": {"content": answer[i:i + 8]}}
                await asyncio.sleep(0.01)

        save_message(db, session, "assistant", answer or "")
        yield {"event": "done", "data": {"session_id": session.id, "reply": answer or ""}}
    except Exception as exc:                     # pragma: no cover
        logger.exception("流式对话失败")
        yield {"event": "error", "data": {"message": str(exc)}}


def list_tool_specs() -> list[dict]:
    return tools.specs()


async def call_tool(db: Session, user, name: str, arguments: dict) -> dict:
    """直接调用工具（不经过模型），便于前端/调试使用。"""
    return await tools.execute(db, user, name, arguments)
