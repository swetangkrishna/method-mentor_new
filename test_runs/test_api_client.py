"""
api_client.py — Multi-backend LLM client (HuggingFace / Ollama / Anthropic)

Fixes for Mac/conda Errno 8 DNS failure:
  1. Injects certifi SSL certs when available (fixes most conda SSL issues)
  2. Falls back to 'requests' library if urllib DNS resolution fails
  3. Diagnostic mode: python api_client.py --diagnose
"""

import json
import os
import ssl
import time
import urllib.request
import urllib.error
from typing import List, Dict

from model_config import get_config


# ── SSL fix for Mac/conda environments ───────────────────────────────────────
# Conda on Mac often ships with stale certs. certifi provides up-to-date ones.
def _make_ssl_context():
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        return ctx
    except ImportError:
        # certifi not installed — use default (may fail on some Mac/conda setups)
        return ssl.create_default_context()


def _http_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """
    POST with automatic fallback:
      1. Try urllib with certifi SSL context
      2. If DNS/SSL fails, try 'requests' library (handles Mac SSL better)
      3. If both fail, raise a clear error with fix instructions
    """
    data = json.dumps(payload).encode("utf-8")

    # Attempt 1: urllib + certifi SSL
    try:
        ctx = _make_ssl_context()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        handler = urllib.request.HTTPSHandler(context=ctx)
        opener  = urllib.request.build_opener(handler)
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError:
        raise   # real HTTP errors (4xx/5xx) — don't suppress, re-raise as-is

    except (urllib.error.URLError, OSError) as urllib_err:
        # DNS/SSL/network failure — try requests as fallback
        try:
            import requests as req_lib
            resp = req_lib.post(url, json=payload, headers={
                k: v for k, v in headers.items()
            }, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except ImportError:
            # requests not installed — give specific fix instructions
            raise RuntimeError(
                f"Network error calling {url}\n\n"
                f"urllib error: {urllib_err}\n\n"
                f"FIX — run ONE of these:\n"
                f"  conda install -c conda-forge certifi   (recommended)\n"
                f"  pip install certifi requests            (alternative)\n\n"
                f"Then restart the server."
            )
        except Exception as req_err:
            raise RuntimeError(
                f"Both urllib and requests failed.\n"
                f"urllib: {urllib_err}\n"
                f"requests: {req_err}\n\n"
                f"Check your internet connection:\n"
                f"  curl -I https://api-inference.huggingface.co\n\n"
                f"If on VPN, try disconnecting it."
            )


# ── HuggingFace ───────────────────────────────────────────────────────────────

def _get_hf_token(cfg: dict) -> str:
    token = (cfg.get("hf_token")
             or os.environ.get("HF_TOKEN")
             or os.environ.get("HUGGINGFACE_TOKEN", ""))
    if not token:
        raise RuntimeError(
            "HuggingFace token not set.\n"
            "  Get a free token: https://huggingface.co/settings/tokens\n"
            "  Then run: export HF_TOKEN=hf_..."
        )
    return token


def _call_hf(messages: List[Dict], system: str, max_tokens: int,
             temperature: float, cfg: dict) -> str:
    token   = _get_hf_token(cfg)
    model   = cfg["model"]
    timeout = cfg.get("timeout", 120)
    retries = cfg.get("hf_max_retries", 3)
    delay   = cfg.get("hf_retry_delay", 25)
    temp    = max(0.01, min(float(temperature), 1.0))

    payload = {
        "model": model,
        "messages": _with_system(messages, system),
        "max_tokens": max_tokens,
        "temperature": temp,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    url = "https://api-inference.huggingface.co/v1/chat/completions"

    for attempt in range(1, retries + 1):
        try:
            body = _http_post(url, payload, headers, timeout)

            if "choices" in body:
                return body["choices"][0]["message"]["content"].strip()
            if isinstance(body, list) and body:
                return str(body[0].get("generated_text", body[0])).strip()
            raise RuntimeError(f"Unexpected HF response format: {json.dumps(body)[:200]}")

        except urllib.error.HTTPError as e:
            code = e.code
            err  = e.read().decode("utf-8", errors="replace")
            if code == 503:
                try:    wait = min(float(json.loads(err).get("estimated_time", delay)), 60)
                except: wait = delay
                if attempt < retries:
                    print(f"  [HF] Model loading — waiting {wait:.0f}s "
                          f"(attempt {attempt}/{retries})...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Model '{model}' still loading after {retries} retries.\n"
                    f"Try again in ~1 minute, or switch to a smaller model."
                )
            elif code == 401:
                raise RuntimeError(
                    "HF token is invalid or expired.\n"
                    "Get a new one: https://huggingface.co/settings/tokens"
                )
            elif code == 403:
                raise RuntimeError(
                    f"Access denied to '{model}'.\n"
                    f"This model requires accepting its license.\n"
                    f"Visit: https://huggingface.co/{model}\n"
                    f"Or switch to: mistralai/Mistral-Nemo-Instruct-2407 (no gate)"
                )
            elif code == 429:
                if attempt < retries:
                    print(f"  [HF] Rate limited — waiting 60s "
                          f"(attempt {attempt}/{retries})...")
                    time.sleep(60)
                    continue
                raise RuntimeError(
                    "HF free tier rate limit hit.\n"
                    "Options:\n"
                    "  1. Wait ~60s and retry\n"
                    "  2. Upgrade to HF PRO ($9/mo) for 1000 req/hr\n"
                    "  3. Switch BACKEND='ollama' in model_config.py"
                )
            elif code == 422:
                raise RuntimeError(
                    f"HF rejected request (422) for model '{model}'.\n"
                    f"This model may not support chat/system prompts.\n"
                    f"Switch HF_MODEL to: Qwen/Qwen2.5-14B-Instruct\n"
                    f"Detail: {err[:200]}"
                )
            else:
                raise RuntimeError(f"HF API error {code}: {err[:200]}")


def check_hf_model(model: str, token: str) -> dict:
    """Quick check: is the model available and loaded?"""
    url = "https://api-inference.huggingface.co/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "temperature": 0.1,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        _http_post(url, payload, headers, timeout=15)
        return {"available": True, "loaded": True, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 503: return {"available": True,  "loaded": False,
                                  "error": "Cold start (loading ~20-60s)"}
        if e.code == 403: return {"available": False, "loaded": False,
                                  "error": "Access denied — accept license on HF"}
        if e.code == 404: return {"available": False, "loaded": False,
                                  "error": "Model not found"}
        return {"available": True, "loaded": True, "error": None}
    except RuntimeError as e:
        return {"available": False, "loaded": False, "error": str(e)[:120]}
    except Exception as e:
        return {"available": False, "loaded": False, "error": str(e)[:120]}


# ── Ollama ────────────────────────────────────────────────────────────────────

def _call_ollama(messages: List[Dict], system: str, max_tokens: int,
                 temperature: float, cfg: dict) -> str:
    host    = cfg["ollama_host"].rstrip("/")
    payload = {
        "model": cfg["model"],
        "messages": _with_system(messages, system),
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": cfg.get("context_length", 8192),
        },
    }
    headers = {"Content-Type": "application/json"}
    try:
        body = _http_post(f"{host}/api/chat", payload, headers,
                          timeout=cfg.get("timeout", 180))
        return body["message"]["content"]
    except RuntimeError as e:
        raise RuntimeError(
            f"Ollama unreachable at {host}.\n"
            f"Fix: run  ollama serve  in a terminal.\n"
            f"Detail: {e}"
        )


def check_ollama_running() -> dict:
    cfg  = get_config()
    host = cfg.get("ollama_host", "http://localhost:11434").rstrip("/")
    try:
        req = urllib.request.Request(f"{host}/api/tags", method="GET")
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=5) as resp:
            body   = json.loads(resp.read().decode())
            models = [m["name"] for m in body.get("models", [])]
            return {"running": True, "models": models, "error": None}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)}


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _call_anthropic(messages: List[Dict], system: str, max_tokens: int,
                    temperature: float) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")
    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system:
        payload["system"] = system
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    try:
        body = _http_post("https://api.anthropic.com/v1/messages",
                          payload, headers, timeout=60)
        return body["content"][0]["text"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic error {e.code}: {e.read().decode()}")


# ── Shared ────────────────────────────────────────────────────────────────────

def _with_system(messages: List[Dict], system: str) -> List[Dict]:
    if not system:
        return list(messages)
    return [{"role": "system", "content": system}] + list(messages)


# ── Public interface ──────────────────────────────────────────────────────────

def call_llm(messages: List[Dict], system: str = "", max_tokens: int = 1024,
             temperature: float = 0.7, role: str = "default") -> str:
    """Universal LLM call. Backend selected via model_config.py."""
    cfg = get_config(role)
    b   = cfg["backend"]
    if   b == "huggingface": return _call_hf(messages, system, max_tokens, temperature, cfg)
    elif b == "ollama":       return _call_ollama(messages, system, max_tokens, temperature, cfg)
    elif b == "anthropic":    return _call_anthropic(messages, system, max_tokens, temperature)
    else: raise ValueError(f"Unknown backend '{b}'. Edit model_config.py.")


def call_llm_precise(messages: List[Dict], system: str = "",
                     max_tokens: int = 1024, role: str = "scorer") -> str:
    """Low-temperature for structured outputs (JSON, scoring)."""
    return call_llm(messages, system=system, max_tokens=max_tokens,
                    temperature=0.05, role=role)


# backwards-compat aliases
call_claude          = call_llm
call_claude_low_temp = call_llm_precise


# ── Diagnostic runner ─────────────────────────────────────────────────────────

def run_diagnostics():
    """
    Run from terminal:  python api_client.py --diagnose
    Checks network, SSL certs, token validity, and model availability.
    """
    import sys
    print("=" * 56)
    print("  Pedagogical RL — Network & API Diagnostic")
    print("=" * 56)

    # 1. Python & SSL
    import platform, ssl as ssl_mod
    print(f"\n[1] Python  : {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")
    print(f"    SSL     : {ssl_mod.OPENSSL_VERSION}")
    try:
        import certifi
        print(f"    certifi : {certifi.__version__} — {certifi.where()}")
    except ImportError:
        print("    certifi : NOT installed  ← install with:  pip install certifi")

    # 2. Basic internet
    print("\n[2] Internet check (example.com)...")
    try:
        ctx = _make_ssl_context()
        req = urllib.request.Request("https://example.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            print(f"    OK — HTTP {r.status}")
    except Exception as e:
        print(f"    FAIL — {e}")
        print("    Check your wifi or VPN settings.")

    # 3. HF endpoint reachable
    print("\n[3] HuggingFace API endpoint reachable...")
    try:
        ctx = _make_ssl_context()
        req = urllib.request.Request(
            "https://api-inference.huggingface.co",
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            print(f"    OK — HTTP {r.status}")
    except Exception as e:
        print(f"    FAIL — {e}")
        print("    The HF API hostname could not be resolved.")
        print("    Fix options:")
        print("      conda install -c conda-forge certifi")
        print("      pip install certifi requests")
        print("      Or: disconnect VPN and retry")

    # 4. HF token
    print("\n[4] HuggingFace token...")
    cfg   = get_config()
    token = cfg.get("hf_token") or os.environ.get("HF_TOKEN", "")
    if not token:
        print("    NOT SET — export HF_TOKEN=hf_...")
    else:
        print(f"    Found: {token[:8]}... (length {len(token)})")

    # 5. Model check
    if token:
        model = cfg.get("model", "?")
        print(f"\n[5] Model check: {model}")
        status = check_hf_model(model, token)
        if status["available"] and status["loaded"]:
            print("    OK — model loaded and ready")
        elif status["available"] and not status["loaded"]:
            print(f"    COLD START — {status['error']}")
            print("    First call will wait ~20-60s. That is normal.")
        else:
            print(f"    FAIL — {status['error']}")
            print("    Try: mistralai/Mistral-Nemo-Instruct-2407 (no license gate)")

    # 6. requests library
    print("\n[6] 'requests' library (fallback)...")
    try:
        import requests as rq
        print(f"    Installed — v{rq.__version__}  (used as fallback if urllib fails)")
    except ImportError:
        print("    Not installed — install for better Mac/conda compatibility:")
        print("      pip install requests")

    print("\n" + "=" * 56)
    print("  Quick fixes for Errno 8:")
    print("    1. pip install certifi requests")
    print("    2. conda install -c conda-forge certifi")
    print("    3. Disconnect VPN / check wifi")
    print("    4. Switch to Ollama: set BACKEND='ollama' in model_config.py")
    print("=" * 56 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--diagnose" in sys.argv:
        run_diagnostics()
        sys.exit(0)

    from model_config import print_config
    print_config(); print()
    cfg = get_config()

    if cfg["backend"] == "huggingface":
        tok = _get_hf_token(cfg)
        st  = check_hf_model(cfg["model"], tok)
        print(f"Model: {st}")

    print("\nSending test message...")
    t0   = time.time()
    resp = call_llm(
        [{"role": "user", "content": "Reply with exactly three words: BACKEND IS OK"}],
        temperature=0.0, max_tokens=20,
    )
    print(f"Response ({time.time()-t0:.1f}s): {resp.strip()}")
