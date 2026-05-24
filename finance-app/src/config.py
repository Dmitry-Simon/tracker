"""Unified secrets loader.

Works under Streamlit (reads st.secrets) and headless (reads env vars / .env).
All other modules should go through this rather than importing streamlit directly,
so the same code paths run in both contexts.
"""
import os
import json
from functools import lru_cache

try:
    import streamlit as st
    _HAS_ST = True
except Exception:
    _HAS_ST = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _from_st(path):
    """Lookup a nested key in st.secrets. Returns None on any failure
    (no Streamlit, no secrets.toml, missing key, type errors)."""
    if not _HAS_ST:
        return None
    try:
        node = st.secrets
        for key in path:
            node = node[key]
        return node
    except Exception:
        return None


@lru_cache(maxsize=1)
def gcp_service_account():
    val = _from_st(("gcp_service_account",))
    if val is not None:
        try:
            return dict(val)
        except Exception:
            return None
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


@lru_cache(maxsize=1)
def gemini_api_key():
    return (
        _from_st(("GEMINI_API_KEY",))
        or _from_st(("gemini", "api_key"))
        or os.environ.get("GEMINI_API_KEY")
    )


@lru_cache(maxsize=1)
def user_profile():
    val = _from_st(("user_profile",))
    if val is not None:
        return {
            "card_patterns": dict(val.get("card_patterns", {})),
            "spender_names": list(val.get("spender_names", ["Joint"])),
            "context": str(val.get("context", "")),
        }
    return {
        "card_patterns": json.loads(os.environ.get("CARD_PATTERNS_JSON", "{}")),
        "spender_names": json.loads(os.environ.get("SPENDER_NAMES_JSON", '["Joint"]')),
        "context": os.environ.get("USER_CONTEXT", ""),
    }


def in_streamlit() -> bool:
    """True iff we're inside a `streamlit run ...` process (not just imported)."""
    if not _HAS_ST:
        return False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def cached(ttl: int = 60):
    """Decorator: st.cache_data when in Streamlit, no-op when headless."""
    if _HAS_ST and in_streamlit():
        try:
            return st.cache_data(ttl=ttl)
        except Exception:
            pass

    def passthrough(fn):
        return fn
    return passthrough
