"""aiteam 实验室适配层：把 REALM-Bench 的 OpenAI 调用切到 opencode-go（OpenAI 兼容端点）。

设计原则：默认（不设 AITEAM_COMPAT=1）行为与上游完全一致；设了才切换。
切换依据（2026-10-02 实测）：
- opencode-go 端点 = https://opencode.ai/zen/go/v1，OpenAI 兼容
- 必须带 x-opencode-session 请求头，否则 400 MissingSessionID
- 模型名用 opencode-go 目录里的（deepseek-v4.1-flash 等），gpt-4o 之类不存在
"""
import os


def _lab_headers() -> dict:
    return {
        "x-opencode-session": os.environ.get("OPENCODE_SESSION", "aiteam-lab"),
        "x-opencode-client": "aiteam-lab",
    }


_USAGE_HANDLER = None


def _usage_handler():
    """langchain 回调：每次 LLM 调用结束把 token 用量追加进 JSONL（AITEAM_USAGE_LOG）。

    上游 runner 不采集 token 用量（results 里 token_usage 恒为空），斗蛐蛐要记账，
    所以在适配层统一挂回调。"""
    global _USAGE_HANDLER
    if _USAGE_HANDLER is not None:
        return _USAGE_HANDLER
    from langchain_core.callbacks import BaseCallbackHandler

    path = os.environ.get("AITEAM_USAGE_LOG", "D:/aiteam-lab/realm-usage.jsonl")

    class _H(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            try:
                import json
                import datetime
                # response 是 LLMResult：用量在 llm_output 或各代消息的 usage_metadata 里
                usage = dict(getattr(response, "llm_output", None) or {}).get("token_usage") or {}
                model = (getattr(response, "llm_output", None) or {}).get("model_name", "")
                if not usage:
                    for gens in getattr(response, "generations", None) or []:
                        for gen in gens:
                            msg = getattr(gen, "message", None)
                            um = getattr(msg, "usage_metadata", None)
                            if um:
                                usage = dict(um)
                                model = model or (getattr(msg, "response_metadata", None) or {}).get("model_name", "")
                rec = {
                    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                    "model": model,
                    "usage": usage,
                }
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass

    _USAGE_HANDLER = _H()
    return _USAGE_HANDLER


def lab_model(**kwargs):
    """langchain_openai.ChatOpenAI 的替身工厂。AITEAM_COMPAT!=1 时原样构造。"""
    from langchain_openai import ChatOpenAI

    if os.environ.get("AITEAM_COMPAT") != "1":
        return ChatOpenAI(**kwargs)
    kwargs["model"] = os.environ.get("REALMBENCH_MODEL", "deepseek-v4.1-flash")
    kwargs["temperature"] = kwargs.get("temperature", 0)
    if os.environ.get("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    kwargs["default_headers"] = _lab_headers()
    kwargs["callbacks"] = [_usage_handler()]
    return ChatOpenAI(**kwargs)


def lab_swarm_client():
    """swarm.Swarm(client=...) 用的 OpenAI 客户端。"""
    from openai import OpenAI

    client_kwargs = {}
    if os.environ.get("OPENAI_BASE_URL"):
        client_kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    if os.environ.get("AITEAM_COMPAT") == "1":
        client_kwargs["default_headers"] = _lab_headers()
    return OpenAI(**client_kwargs)


def lab_model_override():
    """swarm run 的 model_override；未开适配时返回 None（沿用 agent.model 默认）。"""
    if os.environ.get("AITEAM_COMPAT") == "1":
        return os.environ.get("REALMBENCH_MODEL", "deepseek-v4.1-flash")
    return None
