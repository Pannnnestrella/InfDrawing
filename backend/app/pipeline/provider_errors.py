"""Classify upstream provider failures (quota / balance) into user-facing copy."""

from __future__ import annotations

import re

# Codes and fragments seen from DashScope / OpenAI / DeepSeek billing failures.
_QUOTA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"arrearage", re.I),
    re.compile(r"insufficient[_\s-]?balance", re.I),
    re.compile(r"insufficient[_\s-]?quota", re.I),
    re.compile(r"allocation.?quota", re.I),
    re.compile(r"free.?tier", re.I),
    re.compile(r"billing_not_active", re.I),
    re.compile(r"exceeded.?your.?current.?quota", re.I),
    re.compile(r"quota.?exceeded", re.I),
    re.compile(r"余额不足"),
    re.compile(r"欠费"),
    re.compile(r"可用额度"),
    re.compile(r"免费额度"),
    re.compile(r"access denied.*balance", re.I),
    re.compile(r"is_available['\"]?\s*:\s*false", re.I),
)


def is_quota_error(message: str) -> bool:
    """Return True when ``message`` looks like a balance / quota failure."""
    text = (message or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _QUOTA_PATTERNS)


def format_provider_error(message: str) -> str:
    """Rewrite quota failures into a stable Chinese hint; pass other errors through."""
    text = (message or "").strip() or "上游服务调用失败"
    if not is_quota_error(text):
        return text
    provider = _guess_provider(text)
    if provider == "dashscope":
        return "阿里云 DashScope 余额不足或欠费，请充值后重试"
    if provider == "openai":
        return "OpenAI 额度不足或账单未激活，请检查账户后重试"
    if provider == "deepseek":
        return "DeepSeek 余额不足，请充值后重试"
    return "API 余额或额度不足，请充值后重试"


def _guess_provider(message: str) -> str:
    lower = message.lower()
    if "dashscope" in lower or "阿里" in message or "qwen" in lower or "wanx" in lower:
        return "dashscope"
    if "openai" in lower or "insufficient_quota" in lower:
        return "openai"
    if "deepseek" in lower:
        return "deepseek"
    return ""
