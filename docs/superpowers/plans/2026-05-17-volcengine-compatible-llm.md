# Volcengine Compatible LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace volcengine placeholder with `VolcengineCompatibleStrategy` (AsyncOpenAI → Ark) and default HTTP `stream=true`.

**Architecture:** Mirror `openai_compatible.py` in new `volcengine_compatible.py`; register in `strategies/__init__.py`; set `ChatCompletionRequest.stream` default to `True`.

**Tech Stack:** Python 3, FastAPI, `openai` AsyncOpenAI, pytest

**Spec:** `docs/superpowers/specs/2026-05-17-volcengine-compatible-llm-design.md`

---

### Task 1: Volcengine strategy

**Files:**
- Create: `backend/app/llm/strategies/volcengine_compatible.py`
- Delete: `backend/app/llm/strategies/volcengine_placeholder.py`
- Modify: `backend/app/llm/strategies/__init__.py`

- [ ] Implement `VolcengineCompatibleStrategy` (complete + stream)
- [ ] Wire registry key `volcengine`

### Task 2: HTTP default stream

**Files:**
- Modify: `backend/app/llm/api/schemas.py` — `stream: bool = True`

### Task 3: Tests

**Files:**
- Modify: `backend/tests/test_llm.py`

- [ ] Replace 501 tests with mock AsyncOpenAI success tests
- [ ] Run: `pytest backend/tests/test_llm.py -q`

### Task 4: Docs

**Files:**
- Modify: `docs/ai-api.md`
