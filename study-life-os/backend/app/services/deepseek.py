"""DeepSeek 开放 API 客户端：chat（含 Function Call）与 SSE 流式；无 Key 时降级为 mock。"""
import json
from typing import AsyncIterator, Optional

import httpx

from app.core.config import settings


class DeepSeekError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.DEEPSEEK_API_KEY)


def _url(path: str) -> str:
    return settings.DEEPSEEK_BASE_URL.rstrip("/") + path


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }


MOCK_HINT = (
    "⚠️ AI 降级模式：后端未配置 DEEPSEEK_API_KEY（backend/.env），"
    "无法进行模型推理与工具规划。其余全部功能（课表/DDL/教室/打卡/财务/健康/知识库）不受影响；"
    "配置 Key 后重启服务即可启用完整 AI 助手。"
)


async def chat(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.7,
) -> dict:
    """非流式对话。返回 OpenAI 兼容 message dict（可能含 tool_calls）。"""
    if not is_configured():
        return {"role": "assistant", "content": MOCK_HINT, "tool_calls": None}

    body: dict = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
        resp = await client.post(_url("/chat/completions"), headers=_headers(), json=body)
        if resp.status_code != 200:
            raise DeepSeekError(f"DeepSeek {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
    return data["choices"][0]["message"]


async def stream_chat(messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]:
    """流式对话，逐段产出文本增量。"""
    if not is_configured():
        for i in range(0, len(MOCK_HINT), 16):
            yield MOCK_HINT[i:i + 16]
        return

    body = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10)) as client:
        async with client.stream("POST", _url("/chat/completions"), headers=_headers(), json=body) as resp:
            if resp.status_code != 200:
                text = (await resp.aread()).decode("utf-8", "ignore")
                yield f"[ERROR] DeepSeek {resp.status_code}: {text[:300]}"
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        yield piece
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
