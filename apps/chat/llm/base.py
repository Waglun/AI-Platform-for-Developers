"""Single provider-neutral entry point with a shared network slot and context budget."""
import json
import re

from django.conf import settings
from django.db import connection

from .prompt import SYSTEM_INSTRUCTION


class LLMError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def redact(text, context):
    # Known contacts are removed even when not formatted as a phone/email.
    contacts = context.get("contact", {})
    for key in ("name", "phone", "email"):
        value = contacts.get(key)
        if isinstance(value, str) and value.strip():
            text = re.sub(re.escape(value.strip()), "[контакт скрыт]", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[\w-]+", "[email скрыт]", text)
    return re.sub(r"(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)", "[номер скрыт]", text)


def build_messages(conversation, tools=None):
    context = conversation.context
    # Only known preferences and shown public catalogue IDs; never contact/legacy.
    preferences = {k: v for k, v in context.get("preferences", {}).items()
                   if k in {"rooms", "budget", "min_area", "max_area", "min_floor", "max_floor", "building_id", "finishing"}
                   and (type(v) in (int, float) or isinstance(v, str))}
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "system", "content": "required=" + json.dumps(preferences) +
                 "; preferred=" + json.dumps({k: v for k, v in context.get("preferred", {}).items()
                                              if k in {"rooms", "budget", "min_area", "max_area", "min_floor", "max_floor", "building_id", "finishing"}}) +
                 "; shown IDs=" + json.dumps(context.get("last_search", {}).get("apartment_ids", []))}]
    rows = conversation.messages.filter(role__in=["visitor", "assistant"]).order_by("-created_at", "-id")
    history = []
    remaining = settings.LLM_NUM_CTX - settings.LLM_MAX_OUTPUT_TOKENS - prompt_bound(messages, tools)
    for row in rows[:settings.LLM_HISTORY_MESSAGES]:
        if row.metadata.get("type") in {"llm_error", "saved_not_processed"}:
            continue
        content = redact(row.content, context)
        if not history and row.role == 'visitor' and len(content.encode('utf-8')) + 32 > remaining:
            raise LLMError('context_budget')
        # Qwen byte-level BPE: at most one token per UTF-8 byte. Never split a codepoint.
        content = content.encode("utf-8")[:max(0, remaining - 32)].decode("utf-8", errors="ignore")
        if content:
            history.append({"role": "user" if row.role == "visitor" else "assistant", "content": content})
            remaining -= len(content.encode("utf-8")) + 32
        if remaining <= 32:
            break
    return messages + list(reversed(history))


def prompt_bound(messages, tools=None):
    # 256 tokens for the fixed Qwen chat template/generation prefix, plus per-role framing.
    return (256 + sum(32 + len(m.get("content", "").encode("utf-8")) +
                      (len(json.dumps(m["tool_calls"], ensure_ascii=False).encode("utf-8")) + 64
                       if "tool_calls" in m else 0) for m in messages) +
            (256 + len(json.dumps(tools, ensure_ascii=False).encode("utf-8")) if tools else 0))


class LLMClient:
    def complete(self, messages, tools=None):
        if connection.in_atomic_block:
            raise LLMError("transaction_active")
        if not settings.LLM_ENABLED or not settings.LLM_MODEL:
            raise LLMError("not_configured")
        if prompt_bound(messages, tools) + settings.LLM_MAX_OUTPUT_TOKENS > settings.LLM_NUM_CTX:
            raise LLMError("context_budget")
        from .ollama import OllamaAdapter
        # Session-level lock spans the network, but no transaction does. Shared by workers.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(320026, 1)")
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise LLMError("busy")
        try:
            adapter = OllamaAdapter()
            try:
                return adapter.complete(messages, tools=tools) if tools else adapter.complete(messages)
            finally:
                self.metrics = getattr(adapter, "metrics", {})
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(320026, 1)")
