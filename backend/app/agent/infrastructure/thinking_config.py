"""Resolve agent thinking-mode flags for upstream chat requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

_KNOWN_THINKING_KEYS: frozenset[str] = frozenset(
    {"enable_thinking", "thinking_budget", "reasoning_effort"}
)


def _extract_thinking_fragment(parsed: Mapping[str, Any]) -> dict[str, Any]:
    """从解析后的模型配置中取仅 thinking 相关的键。"""
    return {k: parsed[k] for k in _KNOWN_THINKING_KEYS if k in parsed}


def _parse_model_config_json(model_config_raw: str | None) -> dict[str, Any]:
    """解析 model_config JSON；非法或非标量对象当作空映射。"""
    if model_config_raw is None:
        return {}
    stripped = model_config_raw.strip()
    if not stripped:
        return {}
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return dict(data)


def _build_extra_body(fragment: Mapping[str, Any]) -> dict[str, Any]:
    """仅保留已知字段；若启用但无字段则默认为 enable_thinking=True。"""
    body = _extract_thinking_fragment(fragment)
    if "enable_thinking" not in body:
        body = {**body, "enable_thinking": True}
    return body


@dataclass(frozen=True)
class ThinkingConfig:
    """Agent 单次调用的 thinking 开关与传给上游的 extra_body 片段。"""

    enabled: bool
    """为 True 时请求思考模式，并附带 extra_body。"""
    extra_body: dict[str, Any]
    """上游扩展参数（仅已知键）；关闭时为空字典。"""


def resolve_agent_thinking_config(
    *,
    run_flag: bool | None,
    model_config_raw: str | None,
    settings: Any,
) -> ThinkingConfig:
    """按优先级合并 thinking 配置：run_flag > model.enable_thinking > settings.agent_enable_thinking。

    * ``run_flag`` 非 ``None`` 时直接决定是否启用；禁用时 ``extra_body`` 恒为空。
      启用时上游 ``enable_thinking`` 一律为 ``True``，其它已知键取自 model JSON。
    * ``run_flag`` 为 ``None`` 时，若 model JSON 含 ``enable_thinking`` 则用其布尔值；
      否则用 ``settings.agent_enable_thinking``。
    * 启用时 ``extra_body`` 含 ``enable_thinking``、``thinking_budget``、``reasoning_effort``
      （自 model 中出现的键）；若启用且 model 未提供任一已知键则 ``extra_body`` 为 ``{"enable_thinking": True}``.
    """
    parsed = _parse_model_config_json(model_config_raw)

    env_default = bool(getattr(settings, "agent_enable_thinking", False))

    if run_flag is not None:
        enabled = bool(run_flag)
        if not enabled:
            return ThinkingConfig(enabled=False, extra_body={})
        body = _extract_thinking_fragment(parsed)
        body["enable_thinking"] = True
        return ThinkingConfig(enabled=True, extra_body=body)

    if "enable_thinking" in parsed:
        enabled = bool(parsed["enable_thinking"])
    else:
        enabled = env_default

    if not enabled:
        return ThinkingConfig(enabled=False, extra_body={})

    body = _build_extra_body(parsed)
    return ThinkingConfig(enabled=True, extra_body=body)
