"""Tests for provider quota/balance error classification."""

from app.pipeline.provider_errors import format_provider_error, is_quota_error


def test_detects_dashscope_arrearage() -> None:
    raw = 'DashScope task failed: {"code":"Arrearage","message":"Access denied, please make sure your account is in good standing"}'
    assert is_quota_error(raw)
    assert "DashScope" in format_provider_error(raw)


def test_detects_openai_insufficient_quota() -> None:
    raw = "OpenAI Images error (429): insufficient_quota You exceeded your current quota"
    assert is_quota_error(raw)
    assert "OpenAI" in format_provider_error(raw)


def test_detects_deepseek_balance() -> None:
    raw = "DeepSeek request failed: 余额不足"
    assert is_quota_error(raw)
    assert "DeepSeek" in format_provider_error(raw)


def test_ignores_ordinary_errors() -> None:
    raw = "Qwen edit error (400): InvalidParameter size must be multiple of 16"
    assert not is_quota_error(raw)
    assert format_provider_error(raw) == raw
