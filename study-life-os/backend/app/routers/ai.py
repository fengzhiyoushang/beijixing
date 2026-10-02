"""全局 AI 助手路由：JSON 对话 / SSE 流式对话 / 会话历史。

Function Call 循环上限 4 轮；每个工具以当前登录用户身份执行，数据天然隔离。
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user
from app.services import ai_tools, deepseek
from app.schemas import ChatIn

router = APIRouter(prefix="/ai", tags=["AI助手"])

MAX_TOOL_ROUNDS = 4


def _system_prompt(user: m.User) -> str:
    now = datetime.now()
    weekday_cn = "一二三四五六日"[now.isoweekday() - 1]
    return (
        f"你是 StudyLifeOS 个人管理终端内置的 AI 助手「小析」。"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')} 周{weekday_cn}；用户：{user.nickname}。"
        "你可以调用工具查询和操作用户的课表、DDL 任务、学习打卡、空教室、财务、考研进度、知识库、健康数据。"
        "规则：涉及个人数据必须先调用工具、绝不臆造数字；回答使用简洁中文 Markdown；"
        "执行写入类工具后，在回复中复述已完成的操作结果。"
    )


def _history(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(m.AiMessage)
        .filter(m.AiMessage.session_id == session_id,
                m.AiMessage.role.in_(["user", "assistant"]),
                m.AiMessage.content.isnot(None))
        .order_by(m.AiMessage.id.desc()).limit(16).all()
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _ensure_session(db: Session, user: m.User, body: ChatIn) -> m.AiSession:
    session = None
    if body.session_id:
        session = db.get(m.AiSession, body.session_id)
        if session is None or session.user_id != user.id:
            raise HTTPException(404, "会话不存在")
    if session is None:
        session = m.AiSession(user_id=user.id,
                              title=body.message.strip()[:30] or "新对话",
                              source=body.source)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _persist_tools(db: Session, session_id: int, traces: list[dict]) -> None:
    for t in traces:
        db.add(m.AiMessage(session_id=session_id, role="tool",
                           tool_name=t["name"], tool_args=t["args"],
                           content=t["result"]))
    db.commit()


async def _tool_loop(db: Session, user_id: int, messages: list[dict]):
    """返回 (traces, final_message_or_None)。final=None 表示已达轮数上限，需要收尾生成。"""
    traces: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS):
        msg = await deepseek.chat(messages, tools=ai_tools.TOOL_SPECS)
        calls = msg.get("tool_calls")
        if not calls:
            return traces, msg
        messages.append(msg)
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            result = ai_tools.execute(db, user_id, name, args)
            traces.append({"name": name, "args": args,
                           "result": ai_tools.summarize(result)})
            messages.append({
                "role": "tool", "tool_call_id": call.get("id", ""), "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
    return traces, None


@router.post("/chat")
async def chat(body: ChatIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    session = _ensure_session(db, user, body)
    db.add(m.AiMessage(session_id=session.id, role="user", content=body.message))
    db.commit()

    messages = [{"role": "system", "content": _system_prompt(user)}] + _history(db, session.id)
    traces, final = await _tool_loop(db, user.id, messages)
    if final is None:
        final = await deepseek.chat(messages)
    reply = (final.get("content") or "（模型未返回内容）").strip()

    _persist_tools(db, session.id, traces)
    db.add(m.AiMessage(session_id=session.id, role="assistant", content=reply))
    db.commit()
    return {"reply": reply, "session_id": session.id, "tool_calls": traces,
            "ai_configured": deepseek.is_configured()}


@router.post("/chat/stream")
async def chat_stream(body: ChatIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    session = _ensure_session(db, user, body)
    db.add(m.AiMessage(session_id=session.id, role="user", content=body.message))
    db.commit()

    sid, uid, nickname_ready = session.id, user.id, user.nickname

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    async def gen():
        gdb = SessionLocal()
        try:
            yield sse("meta", {"session_id": sid})
            messages = [{"role": "system", "content": _system_prompt(gdb.get(m.User, uid))}] \
                + _history(gdb, sid)
            traces, final = await _tool_loop(gdb, uid, messages)
            for t in traces:  # 工具执行期间实时广播
                yield sse("tool", t)

            reply_text = ""
            if final is not None and final.get("content"):
                reply_text = final["content"]
                for i in range(0, len(reply_text), 24):  # 非流式结果分片下发，前端体验一致
                    yield sse("token", {"text": reply_text[i:i + 24]})
            else:
                async for piece in deepseek.stream_chat(messages):
                    if piece.startswith("[ERROR]"):
                        yield sse("error", {"message": piece})
                        return
                    reply_text += piece
                    yield sse("token", {"text": piece})

            _persist_tools(gdb, sid, traces)
            gdb.add(m.AiMessage(session_id=sid, role="assistant", content=reply_text))
            gdb.commit()
            yield sse("done", {"session_id": sid, "length": len(reply_text)})
        except Exception as exc:
            yield sse("error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            gdb.close()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    sessions = (db.query(m.AiSession)
                .filter(m.AiSession.user_id == user.id)
                .order_by(m.AiSession.id.desc()).limit(50).all())
    return [s.to_dict() for s in sessions]


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: int, db: Session = Depends(get_db),
                     user: m.User = Depends(get_current_user)):
    session = db.get(m.AiSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "会话不存在")
    return {"session": session.to_dict(), "messages": [msg.to_dict() for msg in session.messages]}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db),
                   user: m.User = Depends(get_current_user)):
    session = db.get(m.AiSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "会话不存在")
    db.delete(session)
    db.commit()
    return {"deleted": session_id}
