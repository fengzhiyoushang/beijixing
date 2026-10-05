"""LLM SDK 封装（OpenAI 兼容协议：DeepSeek / Kimi / 通义 / Ollama 等均可）。

统一对外能力：
- `chat`         基础对话 / Function Call（tools 参数），返回 {message, usage}
- `stream_chat`  流式对话（SSE），done 事件携带 usage
- `vision`       多模态图像识别
- `embeddings`   文本向量化（远端 provider，可选）
- `is_configured` / `status` / `test_connection`

配置优先级：调用方传入的 `cfg`（用户在"模型配置"窗口自定义）> 全局 settings（.env）。
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

MOCK_HINT = "未配置 API Key，当前为演示模式"


class DeepSeekError(RuntimeError):
    pass


def _estimate_tokens(messages: list[dict] | str | None, completion_text: str = "") -> dict:
    """provider 未返回 usage 时的兜底估算（中文约 1.5 字/token，英文约 4 字符/token）。"""
    if isinstance(messages, str):
        text = messages
    else:
        text = "".join(str(m.get("content") or "") for m in (messages or []))
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    prompt = int(cjk / 1.5 + other / 4) + 4 * len(messages or [] if isinstance(messages, list) else [])
    c2 = sum(1 for ch in completion_text if "\u4e00" <= ch <= "\u9fff")
    completion = int(c2 / 1.5 + (len(completion_text) - c2) / 4)
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": prompt + completion, "estimated": True}


class DeepSeekClient:
    def __init__(self) -> None:
        self.base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.model = settings.DEEPSEEK_MODEL
        self.vl_model = settings.DEEPSEEK_VL_MODEL
        self.timeout = settings.DEEPSEEK_TIMEOUT
        self.max_retries = 2

    # ── 配置解析：用户自定义 cfg 优先于全局 settings ──
    def _resolve(self, cfg: dict | None) -> tuple[str, str, str, int]:
        cfg = cfg or {}
        base_url = (cfg.get("base_url") or self.base_url).rstrip("/")
        api_key = cfg.get("api_key") or settings.DEEPSEEK_API_KEY
        model = cfg.get("model") or self.model
        timeout = int(cfg.get("timeout") or self.timeout)
        return base_url, api_key, model, timeout

    @staticmethod
    def _is_live(api_key: str) -> bool:
        return bool((api_key or "").strip())

    # ── 状态 ──
    @property
    def is_configured(self) -> bool:
        return settings.deepseek_configured

    def status(self, cfg: dict | None = None) -> dict:
        base_url, api_key, model, _ = self._resolve(cfg)
        live = self._is_live(api_key)
        return {
            "configured": live,
            "mode": "live" if live else "mock",
            "base_url": base_url,
            "model": model,
            "vl_model": self.vl_model,
            "custom": bool(cfg and (cfg.get("api_key") or cfg.get("base_url") or cfg.get("model"))),
            "hint": None if live else MOCK_HINT,
        }

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
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
        cfg: dict | None = None,
    ) -> dict:
        """返回 {"message": OpenAI 风格 message, "usage": {...}, "model": str}"""
        base_url, api_key, default_model, timeout = self._resolve(cfg)
        used_model = model or default_model
        if not self._is_live(api_key):
            return {"message": self._mock_chat(messages, tools), "usage": None, "model": used_model}

        payload: dict = {
            "model": used_model,
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

        data = await self._post(base_url, api_key, timeout, "/chat/completions", payload)
        usage = data.get("usage")
        if usage:
            usage = {**usage, "estimated": False}
        return {"message": data["choices"][0]["message"], "usage": usage,
                "model": data.get("model") or used_model}

    # ── 流式对话 ──
    async def stream_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        model: str | None = None,
        cfg: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """逐块产出 {"type": "token"|"done"|"error", ...}；done 携带 usage。"""
        base_url, api_key, default_model, timeout = self._resolve(cfg)
        used_model = model or default_model
        if not self._is_live(api_key):
            text = self._mock_chat(messages, None).get("content") or ""
            for i in range(0, len(text), 6):
                yield {"type": "token", "content": text[i:i + 6]}
                await asyncio.sleep(0.01)
            yield {"type": "done", "content": text, "usage": None}
            return

        payload = {
            "model": used_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            # OpenAI 兼容协议：流式末尾回传 usage（DeepSeek/Kimi/通义均支持；不支持时自动忽略）
            "stream_options": {"include_usage": True},
        }
        url = f"{base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=self._headers(api_key), json=payload) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        yield {"type": "error", "message": f"LLM {resp.status_code}: {body[:200]}"}
                        return
                    buffer = ""
                    full = ""
                    usage: dict | None = None
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                continue
                            try:
                                obj = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            if obj.get("usage"):
                                usage = {**obj["usage"], "estimated": False}
                            choices = obj.get("choices") or []
                            if not choices:
                                continue
                            piece = (choices[0].get("delta") or {}).get("content")
                            if piece:
                                full += piece
                                yield {"type": "token", "content": piece}
            if usage is None:
                usage = _estimate_tokens(messages, full)
            yield {"type": "done", "content": full, "usage": usage}
        except Exception as exc:  # pragma: no cover - 网络相关
            logger.warning("流式对话失败：%s", exc)
            yield {"type": "error", "message": str(exc)}

    # ── 连通性测试（供配置窗口"测试连接"按钮） ──
    async def test_connection(self, cfg: dict) -> dict:
        base_url, api_key, model, timeout = self._resolve(cfg)
        if not self._is_live(api_key):
            return {"ok": False, "message": "请先填写 API Key"}
        try:
            async with httpx.AsyncClient(timeout=min(timeout, 20)) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers=self._headers(api_key),
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 8, "stream": False},
                )
            if resp.status_code >= 400:
                return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            data = resp.json()
            usage = data.get("usage") or {}
            return {"ok": True, "message": "连接成功", "model": data.get("model") or model,
                    "reply": (data.get("choices") or [{}])[0].get("message", {}).get("content", "")[:40],
                    "usage": usage}
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:200]}

    # ── 多模态图像识别 ──
    async def vision(self, image_base64: str, *, prompt: str | None = None,
                     model: str | None = None, cfg: dict | None = None) -> str:
        """图片 base64 → 识别结果文本（要求模型输出 JSON）。"""
        prompt = prompt or prompts.VISION_PROMPT
        base_url, api_key, _, timeout = self._resolve(cfg)
        if not self._is_live(api_key):
            return json.dumps(
                {"status": "free", "occupied_ratio": 0.18, "confidence": 0.62,
                 "seats_visible": 48, "occupied_seats": 9,
                 "reason": f"演示模式：{MOCK_HINT}，返回启发式估计值"},
                ensure_ascii=False,
            )
        data_url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
        payload = {
            "model": model or (cfg or {}).get("vl_model") or self.vl_model,
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
        result = await self._post(base_url, api_key, timeout, "/chat/completions", payload)
        return result["choices"][0]["message"].get("content") or ""

    # ── 向量化 ──
    async def embeddings(self, texts: list[str], *, model: str | None = None) -> list[list[float]] | None:
        """远端向量化；未配置或接口不可用时返回 None（调用方回退本地向量）。"""
        if not self.is_configured or settings.EMBEDDING_PROVIDER != "deepseek":
            return None
        try:
            data = await self._post(
                self.base_url, settings.DEEPSEEK_API_KEY, self.timeout,
                "/embeddings",
                {"model": model or settings.EMBEDDING_MODEL, "input": texts},
            )
            return [item["embedding"] for item in data.get("data", [])]
        except Exception as exc:  # pragma: no cover
            logger.warning("远端 embedding 失败，回退本地向量：%s", exc)
            return None

    # ── 内部：HTTP 与重试 ──
    async def _post(self, base_url: str, api_key: str, timeout: int, path: str, payload: dict) -> dict:
        url = f"{base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=self._headers(api_key), json=payload)
                if resp.status_code >= 400:
                    raise DeepSeekError(f"LLM {resp.status_code}: {resp.text[:300]}")
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
