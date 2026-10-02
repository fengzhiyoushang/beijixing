"""DeepSeek SDK 封装（OpenAI 兼容协议）。

统一对外能力：
- `chat`         基础对话 / Function Call（tools 参数）
- `stream_chat`  流式对话（SSE）
- `vision`       多模态图像识别（deepseek-vl）
- `embeddings`   文本向量化（远端 provider，可选）
- `is_configured` / `status`

未配置 API Key 时全部走 mock 降级，保证项目开箱可跑、可联调。
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.ai import prompts
from app.core.config import settings

logger = logging.getLogger("polaris.ai")

MOCK_HINT = "未配置 DEEPSEEK_API_KEY，当前为演示模式"


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self) -> None:
        self.base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = settings.DEEPSEEK_MODEL
        self.vl_model = settings.DEEPSEEK_VL_MODEL
        self.timeout = settings.DEEPSEEK_TIMEOUT
        self.max_retries = 2

    # ── 状态 ──
    @property
    def is_configured(self) -> bool:
        return settings.deepseek_configured

    def status(self) -> dict:
        return {
            "configured": self.is_configured,
            "mode": "live" if self.is_configured else "mock",
            "base_url": self.base_url,
            "model": self.model,
            "vl_model": self.vl_model,
            "hint": None if self.is_configured else MOCK_HINT,
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

    # ── 基础对话 ──
    async def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
        response_format: dict | None = None,
        max_tokens: int = 2048,
    ) -> dict:
        """返回 OpenAI 风格 message 字典：{role, content, tool_calls?}"""
        if not self.is_configured:
            return self._mock_chat(messages, tools)

        payload: dict = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format

        data = await self._post("/chat/completions", payload)
        return data["choices"][0]["message"]

    # ── 流式对话 ──
    async def stream_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """逐块产出 {"type": "token"|"done"|"error", ...}。"""
        if not self.is_configured:
            text = self._mock_chat(messages, None).get("content") or ""
            for i in range(0, len(text), 6):
                yield {"type": "token", "content": text[i:i + 6]}
                await asyncio.sleep(0.01)
            yield {"type": "done", "content": text}
            return

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        yield {"type": "error", "message": f"DeepSeek {resp.status_code}: {body[:200]}"}
                        return
                    buffer = ""
                    full = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                yield {"type": "done", "content": full}
                                return
                            try:
                                delta = json.loads(data)["choices"][0].get("delta", {})
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                            piece = delta.get("content")
                            if piece:
                                full += piece
                                yield {"type": "token", "content": piece}
            yield {"type": "done", "content": full}
        except Exception as exc:  # pragma: no cover - 网络相关
            logger.warning("流式对话失败：%s", exc)
            yield {"type": "error", "message": str(exc)}

    # ── 多模态图像识别 ──
    async def vision(self, image_base64: str, *, prompt: str | None = None,
                     model: str | None = None) -> str:
        """图片 base64 → 识别结果文本（要求模型输出 JSON）。"""
        prompt = prompt or prompts.VISION_PROMPT
        if not self.is_configured:
            return json.dumps(
                {"status": "free", "occupied_ratio": 0.18, "confidence": 0.62,
                 "seats_visible": 48, "occupied_seats": 9,
                 "reason": f"演示模式：{MOCK_HINT}，返回启发式估计值"},
                ensure_ascii=False,
            )
        data_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
        payload = {
            "model": model or self.vl_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 512,
        }
        result = await self._post("/chat/completions", payload)
        return result["choices"][0]["message"].get("content") or ""

    # ── 向量化 ──
    async def embeddings(self, texts: list[str], *, model: str | None = None) -> list[list[float]] | None:
        """远端向量化；未配置或接口不可用时返回 None（调用方回退本地向量）。"""
        if not self.is_configured or settings.EMBEDDING_PROVIDER != "deepseek":
            return None
        try:
            data = await self._post(
                "/embeddings",
                {"model": model or settings.EMBEDDING_MODEL, "input": texts},
            )
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as exc:  # pragma: no cover
            logger.warning("远端 embedding 失败，回退本地向量：%s", exc)
            return None

    # ── 内部：HTTP 与重试 ──
    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
                if resp.status_code >= 400:
                    raise DeepSeekError(f"DeepSeek {resp.status_code}: {resp.text[:300]}")
                return resp.json()
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
        raise DeepSeekError(str(last_error))

    def _mock_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """演示模式：可选触发一个工具调用，便于验证 Function Call 链路。"""
        user_text = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "") or ""
        if tools and any(k in user_text for k in ("今天", "课", "DDL", "任务", "教室", "进度", "预算", "健康")):
            name = "get_dashboard_summary"
            if "教室" in user_text:
                name = "classroom_predict"
            elif "DDL" in user_text or "任务" in user_text:
                name = "list_ddl_tasks"
            elif "进度" in user_text:
                name = "get_study_progress"
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"call_mock_{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": "{}"},
                }],
            }
        return {
            "role": "assistant",
            "content": prompts.MOCK_REPLY.format(question=user_text[:60] or "你好"),
            "tool_calls": None,
        }


deepseek = DeepSeekClient()
