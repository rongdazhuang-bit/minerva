"""Tests for agent thinking mode resolution (run flag, model_config, env cascade)."""

from types import SimpleNamespace

from app.agent.infrastructure.thinking_config import resolve_agent_thinking_config


def test_run_flag_overrides_model_and_env():
    """run_flag 非空时优先生效；关闭时 extra_body 为空。"""
    settings = SimpleNamespace(agent_enable_thinking=True)
    cfg = resolve_agent_thinking_config(
        run_flag=False,
        model_config_raw='{"enable_thinking": true, "thinking_budget": 4096}',
        settings=settings,
    )
    assert cfg.enabled is False
    assert cfg.extra_body == {}


def test_model_config_used_when_run_flag_none():
    """run_flag 为 None 时 model_config 中的 enable_thinking 可覆盖 settings。"""
    settings = SimpleNamespace(agent_enable_thinking=False)
    cfg = resolve_agent_thinking_config(
        run_flag=None,
        model_config_raw='{"enable_thinking": true, "reasoning_effort": "medium"}',
        settings=settings,
    )
    assert cfg.enabled is True
    assert cfg.extra_body["enable_thinking"] is True
    assert cfg.extra_body["reasoning_effort"] == "medium"


def test_env_default_when_no_run_and_empty_model_config():
    """无 run 覆盖且无 model 配置项时回退到 settings.agent_enable_thinking。"""
    settings = SimpleNamespace(agent_enable_thinking=True)
    cfg = resolve_agent_thinking_config(
        run_flag=None,
        model_config_raw=None,
        settings=settings,
    )
    assert cfg.enabled is True
    assert cfg.extra_body == {"enable_thinking": True}
