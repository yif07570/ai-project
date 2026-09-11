"""LLM client with automatic mock fallback (used by all sessions).

Priority: OPENAI_API_KEY > ANTHROPIC_API_KEY > DEEPSEEK_API_KEY > mock.
`mock` may be a string or a callable(system, user) -> str, so every demo
runs deterministically without any key.

Provider selection is exposed through `llm_provider()` / `llm_model()` so callers
never have to re-implement the "which key is set?" check. Doing that inline is how
you end up with one stage calling a real API while another silently stays on mocks
(see demo-openclaw/demo_openclaw.py, which used to have exactly that bug).

Network calls are bounded by LLM_TIMEOUT seconds (default 60) and retried at most
LLM_MAX_RETRIES times (default 1). A live demo must fail fast, not hang.

Two entry points:
  call_llm()        text in, text out — sessions 3-12
  call_llm_tools()  one turn of a tool-calling conversation — session 13 builds
                    the loop (validate -> guardrails -> execute -> feed back) on it
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# load_dotenv() with no argument resolves relative to the *caller's* directory —
# except in a REPL or a Jupyter kernel, where __main__ has no __file__ and it
# silently falls back to os.getcwd(). A notebook launched from the repo root
# would therefore never see course-demos/.env, and "why is it still in mock
# mode" becomes a five-minute mystery on stage. Load the shared file by an
# absolute path so it works from any working directory.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"      # course-demos/.env

load_dotenv()                       # a .env nearer the caller wins, if there is one
load_dotenv(ENV_PATH)               # then the shared course-demos one (never overrides)

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "deepseek": "deepseek-chat",
}


def _timeout() -> float:
    return float(os.environ.get("LLM_TIMEOUT", "60"))


def _max_retries() -> int:
    return int(os.environ.get("LLM_MAX_RETRIES", "1"))


def llm_provider() -> str:
    """Which backend a call_llm() right now would use: openai|anthropic|deepseek|mock."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    return "mock"


def llm_model() -> str:
    """Model id for the active provider. DEMO_MODEL overrides it."""
    provider = llm_provider()
    if provider == "mock":
        return "mock"
    return os.environ.get("DEMO_MODEL") or DEFAULT_MODELS[provider]


def llm_available() -> bool:
    return llm_provider() != "mock"


def call_llm(system: str, user: str, mock=None, temperature: float = 0.3) -> str:
    provider = llm_provider()

    if provider in ("openai", "deepseek"):
        # DeepSeek's API is OpenAI-compatible: same SDK, different base_url/key.
        from openai import OpenAI
        client = (OpenAI(timeout=_timeout(), max_retries=_max_retries())
                  if provider == "openai" else
                  OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                         base_url="https://api.deepseek.com",
                         timeout=_timeout(), max_retries=_max_retries()))
        r = client.chat.completions.create(
            model=llm_model(),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature)
        return r.choices[0].message.content

    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(timeout=_timeout(),
                                max_retries=_max_retries()).messages.create(
            model=llm_model(), max_tokens=1500, system=system,
            messages=[{"role": "user", "content": user}])
        return r.content[0].text

    if mock is None:
        raise RuntimeError("No API key set and no mock provided for offline mode")
    # stderr, not stdout: session 14's MCP server speaks JSON-RPC on stdout, and a
    # stray line there corrupts the stream — the client just sees the server die.
    # Diagnostics belong on stderr in anything that might be piped.
    print("  [mock LLM] no API key found, using deterministic mock output", file=sys.stderr)
    return mock(system, user) if callable(mock) else mock


def call_llm_tools(system: str, messages: list, tools: list,
                   mock=None, temperature: float = 0.3) -> dict:
    """One turn of a tool-calling conversation. Session 13 builds the loop on top.

    `messages` / `tools` use the OpenAI shape, because it is the one most students
    will meet first; the Anthropic branch translates on the way in and out so the
    caller never has to branch on provider (same rule as call_llm).

    Returns a provider-independent dict:
        {"content": str | None, "tool_calls": [{"id", "name", "arguments": dict}]}

    An empty `tool_calls` means the model answered instead of reaching for a tool —
    that is the loop's termination condition, not an error.

    `mock` is a callable(system, messages, tools) -> that same dict. Offline it is
    the *only* thing that runs, so tool-calling logic stays testable with no key.
    """
    provider = llm_provider()

    if provider in ("openai", "deepseek"):
        from openai import OpenAI
        client = (OpenAI(timeout=_timeout(), max_retries=_max_retries())
                  if provider == "openai" else
                  OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"],
                         base_url="https://api.deepseek.com",
                         timeout=_timeout(), max_retries=_max_retries()))
        r = client.chat.completions.create(
            model=llm_model(), temperature=temperature, tools=tools,
            messages=[{"role": "system", "content": system}] + messages)
        msg = r.choices[0].message
        return {"content": msg.content,
                "tool_calls": [{"id": c.id, "name": c.function.name,
                                "arguments": _loads_or_empty(c.function.arguments)}
                               for c in (msg.tool_calls or [])]}

    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(timeout=_timeout(),
                                max_retries=_max_retries()).messages.create(
            model=llm_model(), max_tokens=1500, system=system,
            tools=[{"name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"]["parameters"]} for t in tools],
            messages=_to_anthropic_messages(messages))
        text = "".join(b.text for b in r.content if b.type == "text") or None
        return {"content": text,
                "tool_calls": [{"id": b.id, "name": b.name, "arguments": b.input}
                               for b in r.content if b.type == "tool_use"]}

    if mock is None:
        raise RuntimeError("No API key set and no mock provided for offline mode")
    return mock(system, messages, tools)


def _loads_or_empty(raw: str) -> dict:
    """Models occasionally emit malformed argument JSON. Session 13's validator is
    the right place to complain about that, so hand it {} rather than raising here."""
    import json
    try:
        return json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}


def _to_anthropic_messages(messages: list) -> list:
    """OpenAI-shaped history -> Anthropic content blocks.

    The two APIs disagree on where tool traffic lives: OpenAI puts calls on the
    assistant message and results in their own `role: "tool"` messages, Anthropic
    puts both inside content blocks (tool_use / tool_result, the latter on a *user*
    message). Keeping that translation in one place is the same rule as having a
    single llm_provider().
    """
    import json
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                 "content": m["content"]}]})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"],
                        "input": c["arguments"] if isinstance(c["arguments"], dict)
                        else json.loads(c["arguments"])}
                       for c in m["tool_calls"]]
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


def call_llm_safe(system: str, user: str, mock, temperature: float = 0.3) -> str:
    """call_llm, but a failing/slow API degrades to the mock instead of raising.

    For live demos only. Course sessions should use call_llm() so students see
    real errors instead of silently grading a mock.
    """
    try:
        return call_llm(system=system, user=user, mock=mock, temperature=temperature)
    except Exception as exc:                                    # noqa: BLE001
        print(f"  [fallback] {llm_provider()} call failed "
              f"({type(exc).__name__}: {exc}); using offline mock")
        return mock(system, user) if callable(mock) else mock
