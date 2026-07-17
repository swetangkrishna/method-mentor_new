"""
api_client.py — Multi-backend LLM client v5

SSL fix for Mac/conda:
  huggingface_hub InferenceClient uses requests internally.
  On Mac/conda the system SSL store does not trust the HF CDN certificate.
  Fix: inject certifi CA bundle via REQUESTS_CA_BUNDLE + SSL_CERT_FILE env vars
  BEFORE any requests session is created, and patch the session directly.
"""

import json
import os
import ssl
import time
import urllib.request
import urllib.error
from typing import List, Dict

# ── SSL fix: inject certifi BEFORE any requests/huggingface_hub import ────────
# This must happen at module level before any session is created.
try:
    import certifi as _certifi
    _ca = _certifi.where()
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    os.environ.setdefault("SSL_CERT_FILE", _ca)
    os.environ.setdefault("CURL_CA_BUNDLE", _ca)
except ImportError:
    pass
# ─────────────────────────────────────────────────────────────────────────────

from model_config import get_config

# Free HF Inference API endpoint — always use this, never the router
_HF_FREE_BASE    = "https://api-inference.huggingface.co"
_HF_FREE_CHAT_URL = f"{_HF_FREE_BASE}/v1/chat/completions"


# ── SSL context (certifi) ─────────────────────────────────────────────────────

def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── urllib POST ───────────────────────────────────────────────────────────────

def _urllib_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data    = json.dumps(payload).encode()
    ctx     = _ssl_ctx()
    req     = urllib.request.Request(url, data=data, headers=headers, method="POST")
    handler = urllib.request.HTTPSHandler(context=ctx)
    opener  = urllib.request.build_opener(handler)
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ── requests POST ─────────────────────────────────────────────────────────────

def _requests_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    import requests
    try:
        import certifi as _c
        verify = _c.where()
    except ImportError:
        verify = True
    resp = requests.post(url, json=payload, headers=headers,
                         timeout=timeout, verify=verify)
    resp.raise_for_status()
    return resp.json()


# ── huggingface_hub InferenceClient (FREE endpoint forced via base_url) ───────

def _hub_chat(model: str, messages: list, max_tokens: int,
              temperature: float, token: str, timeout: int) -> str:
    """
    Uses huggingface_hub InferenceClient.

    CRITICAL: base_url MUST be set to force the FREE api-inference endpoint.
    Without base_url, hf_hub 0.29.x reads the HF_PROVIDER env/config and may
    route to a paid provider (together, fireworks, etc.) → 402 Payment Required.

    base_url="https://api-inference.huggingface.co/v1" forces the free path
    in both 0.29.x (uses base_url kwarg) and newer versions.
    """
    from huggingface_hub import InferenceClient

    # In 0.29.x, base_url and model= are aliases — pass ONLY base_url.
    # model= goes in chat.completions.create() as an HTTP request body field.
    client = InferenceClient(
        base_url=f"{_HF_FREE_BASE}/v1",
        token=token,
        timeout=timeout,
    )

    # Patch the internal requests session to use certifi certs.
    # Fixes SSL errors on Mac/conda where the system CA store is incomplete.
    try:
        import certifi as _c
        _ca = _c.where()
        for _attr in ("_session", "session"):
            _sess = getattr(client, _attr, None)
            if _sess is not None and hasattr(_sess, "verify"):
                _sess.verify = _ca
                break
    except Exception:
        pass

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=max(0.01, min(float(temperature), 1.0)),
        stream=False,
    )
    return resp.choices[0].message.content.strip()


# ── Master HF caller (tries all transports) ───────────────────────────────────

def _call_hf(messages: List[Dict], system: str, max_tokens: int,
             temperature: float, cfg: dict) -> str:
    token   = _get_hf_token(cfg)
    model   = cfg["model"]
    timeout = cfg.get("timeout", 120)
    retries = cfg.get("hf_max_retries", 3)
    delay   = cfg.get("hf_retry_delay", 25)
    msgs    = _with_system(messages, system)

    def _try_all(attempt: int) -> str:
        errors = {}

        # Transport 1: huggingface_hub (best — handles DNS issues)
        try:
            return _hub_chat(model, msgs, max_tokens, temperature, token, timeout)
        except ImportError:
            errors["hub"] = "pip install huggingface_hub"
        except Exception as e:
            err = str(e)
            # Catch any remaining 402 and give an actionable message
            if "402" in err or "Payment" in err:
                raise RuntimeError(
                    f"402 Payment Required — huggingface_hub is still routing to a paid endpoint.\n"
                    f"Fix: check that HF_PROVIDER is NOT set in model_config.py or environment.\n"
                    f"Current model: {model}\n"
                    f"Detail: {err[:200]}"
                )
            errors["hub"] = err[:120]

        # Transport 2: requests + certifi
        try:
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {token}"}
            body = _requests_post(
                _HF_FREE_CHAT_URL,
                {"model": model, "messages": msgs, "max_tokens": max_tokens,
                 "temperature": max(0.01, min(float(temperature), 1.0)),
                 "stream": False},
                headers, timeout,
            )
            if "choices" in body:
                return body["choices"][0]["message"]["content"].strip()
            errors["requests"] = f"Unexpected response: {str(body)[:80]}"
        except ImportError:
            errors["requests"] = "pip install requests"
        except Exception as e:
            errors["requests"] = str(e)[:120]

        # Transport 3: urllib + certifi
        try:
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {token}"}
            body = _urllib_post(
                _HF_FREE_CHAT_URL,
                {"model": model, "messages": msgs, "max_tokens": max_tokens,
                 "temperature": max(0.01, min(float(temperature), 1.0)),
                 "stream": False},
                headers, timeout,
            )
            if "choices" in body:
                return body["choices"][0]["message"]["content"].strip()
            errors["urllib"] = f"Unexpected response: {str(body)[:80]}"
        except Exception as e:
            errors["urllib"] = str(e)[:120]

        raise RuntimeError(
            f"All HF transports failed (attempt {attempt}):\n"
            + "\n".join(f"  {k}: {v}" for k, v in errors.items())
            + "\n\nFixes:\n"
            "  1. pip install --upgrade huggingface_hub\n"
            "  2. Make sure HF_PROVIDER is not set (or remove it from model_config.py)\n"
            "  3. Switch to Ollama: BACKEND='ollama' in model_config.py"
        )

    # Retry loop (for 503 model-loading)
    for attempt in range(1, retries + 1):
        try:
            return _try_all(attempt)
        except urllib.error.HTTPError as e:
            code = e.code
            err  = e.read().decode("utf-8", errors="replace")
            if code == 503:
                try:    wait = min(float(json.loads(err).get("estimated_time", delay)), 60)
                except: wait = delay
                if attempt < retries:
                    print(f"  [HF] Model loading — waiting {wait:.0f}s (attempt {attempt}/{retries})...")
                    time.sleep(wait); continue
                raise RuntimeError(f"Model '{model}' still loading. Try again in ~1 min.")
            elif code == 401:
                raise RuntimeError("HF token invalid. Get new: https://huggingface.co/settings/tokens")
            elif code == 403:
                raise RuntimeError(
                    f"Access denied to '{model}'.\n"
                    f"Accept its license: https://huggingface.co/{model}\n"
                    f"Or switch to: mistralai/Mistral-Nemo-Instruct-2407")
            elif code == 429:
                if attempt < retries:
                    print(f"  [HF] Rate limited — waiting 60s..."); time.sleep(60); continue
                raise RuntimeError("HF rate limit. Wait or upgrade to HF PRO.")
            elif code == 402:
                raise RuntimeError(
                    "402 Payment Required.\n"
                    "Remove HF_PROVIDER from model_config.py and environment.\n"
                    f"pip install --upgrade huggingface_hub")
            else:
                raise RuntimeError(f"HF API error {code}: {err[:200]}")
        except RuntimeError:
            raise
    raise RuntimeError("Max retries exceeded.")


def _get_hf_token(cfg: dict) -> str:
    token = (cfg.get("hf_token")
             or os.environ.get("HF_TOKEN")
             or os.environ.get("HUGGINGFACE_TOKEN", ""))
    if not token:
        raise RuntimeError(
            "HuggingFace token not set.\n"
            "  Get free token: https://huggingface.co/settings/tokens\n"
            "  Then: export HF_TOKEN=hf_...")
    return token


def check_hf_model(model: str, token: str) -> dict:
    try:
        _hub_chat(model,
                  [{"role": "user", "content": "hi"}],
                  5, 0.1, token, 20)
        return {"available": True, "loaded": True, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 503: return {"available": True,  "loaded": False, "error": "Cold start (~20-60s)"}
        if e.code == 403: return {"available": False, "loaded": False, "error": "Accept license on HF"}
        if e.code == 404: return {"available": False, "loaded": False, "error": "Model not found"}
        return {"available": True, "loaded": True, "error": None}
    except RuntimeError as e:
        return {"available": False, "loaded": False, "error": str(e)[:160]}
    except Exception as e:
        return {"available": False, "loaded": False, "error": str(e)[:160]}


# ── Ollama ────────────────────────────────────────────────────────────────────

def _call_ollama(messages: List[Dict], system: str, max_tokens: int,
                 temperature: float, cfg: dict) -> str:
    host    = cfg["ollama_host"].rstrip("/")
    payload = {
        "model": cfg["model"],
        "messages": _with_system(messages, system),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "num_ctx": cfg.get("context_length", 8192)},
    }
    try:
        body = _urllib_post(f"{host}/api/chat", payload,
                            {"Content-Type": "application/json"},
                            timeout=cfg.get("timeout", 180))
        return body["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama unreachable at {host}.\nRun: ollama serve\n{e}")


def check_ollama_running() -> dict:
    cfg  = get_config()
    host = cfg.get("ollama_host", "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{host}/api/tags"), timeout=5
        ) as resp:
            body   = json.loads(resp.read().decode())
            return {"running": True,
                    "models": [m["name"] for m in body.get("models", [])],
                    "error": None}
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
        "max_tokens": max_tokens, "messages": messages, "temperature": temperature,
    }
    if system:
        payload["system"] = system
    try:
        body = _urllib_post("https://api.anthropic.com/v1/messages", payload,
                            {"Content-Type": "application/json",
                             "x-api-key": key,
                             "anthropic-version": "2023-06-01"}, timeout=60)
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
    cfg = get_config(role)
    b   = cfg["backend"]
    if   b == "huggingface": return _call_hf(messages, system, max_tokens, temperature, cfg)
    elif b == "ollama":       return _call_ollama(messages, system, max_tokens, temperature, cfg)
    elif b == "anthropic":    return _call_anthropic(messages, system, max_tokens, temperature)
    else: raise ValueError(f"Unknown backend '{b}'. Edit model_config.py.")


def call_llm_precise(messages: List[Dict], system: str = "",
                     max_tokens: int = 1024, role: str = "scorer") -> str:
    return call_llm(messages, system=system, max_tokens=max_tokens,
                    temperature=0.05, role=role)


call_claude          = call_llm
call_claude_low_temp = call_llm_precise


# ── Diagnostic ────────────────────────────────────────────────────────────────

def run_diagnostics():
    import sys, platform
    print("=" * 58)
    print("  Pedagogical RL — Diagnostic v4")
    print("=" * 58)
    print(f"\n[1] Environment")
    print(f"    Python  : {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")

    try:
        import certifi; print(f"    certifi : {certifi.__version__}  ✓")
    except ImportError:
        print("    certifi : MISSING — pip install certifi")
    try:
        import requests as rq; print(f"    requests: {rq.__version__}  ✓")
    except ImportError:
        print("    requests: MISSING — pip install requests")
    try:
        import huggingface_hub as hfh; print(f"    hf_hub  : {hfh.__version__}  ✓")
    except ImportError:
        print("    hf_hub  : MISSING — pip install huggingface_hub")

    import socket
    print(f"\n[2] DNS resolution")
    for host in ["example.com", "huggingface.co", "api-inference.huggingface.co"]:
        try:
            ip = socket.gethostbyname(host)
            print(f"    {host:45s} {ip}  ✓")
        except Exception as e:
            print(f"    {host:45s} FAIL ({e})")

    print(f"\n[3] model_config.py — checking for provider issues")
    from model_config import get_config
    cfg = get_config()
    print(f"    Backend : {cfg['backend']}")
    print(f"    Model   : {cfg['model']}")
    provider_val = getattr(__import__('model_config'), 'HF_PROVIDER', None)
    env_provider  = os.environ.get("HF_PROVIDER", "")
    if provider_val and provider_val not in ("hf-inference", ""):
        print(f"    ⚠ HF_PROVIDER='{provider_val}' in model_config — causes 402!")
        print(f"      Fix: remove HF_PROVIDER from model_config.py")
    elif env_provider and env_provider not in ("hf-inference", ""):
        print(f"    ⚠ HF_PROVIDER env='{env_provider}' — causes 402! Run: unset HF_PROVIDER")
    else:
        print(f"    HF_PROVIDER : not set  ✓  (free endpoint forced via base_url)")

    print(f"\n[4] huggingface_hub transport test (base_url forced to free endpoint)")
    token = cfg.get("hf_token") or os.environ.get("HF_TOKEN", "")
    if not token:
        print("    HF_TOKEN not set — skipping")
    else:
        test_model = "mistralai/Mistral-Nemo-Instruct-2407"
        print(f"    Testing model: {test_model}")
        try:
            result = _hub_chat(
                test_model,
                [{"role": "user", "content": "Reply with exactly: OK"}],
                10, 0.1, token, 30,
            )
            print(f"    ✓ Response: {result.strip()}")
            print(f"    huggingface_hub transport working correctly!")
        except Exception as e:
            err = str(e)
            if "402" in err or "Payment" in err:
                print(f"    ✗ 402 Payment Required — base_url fix not working")
                print(f"      Try: pip install --upgrade huggingface_hub")
            elif "503" in err or "loading" in err.lower():
                print(f"    ⚠ Model loading (cold start) — this is normal, will retry automatically")
            else:
                print(f"    ✗ {err[:150]}")

    print(f"\n[5] Testing configured model: {cfg.get('model', '?')}")
    if token and cfg.get("model"):
        st = check_hf_model(cfg["model"], token)
        if st["loaded"]:
            print(f"    ✓ Model ready")
        elif st["available"]:
            print(f"    ⚠ {st['error']} — first call will be slow")
        else:
            print(f"    ✗ {st['error']}")
            print(f"      Try model: Qwen/Qwen2.5-7B-Instruct or mistralai/Mistral-Nemo-Instruct-2407")

    print("\n" + "=" * 58 + "\n")


if __name__ == "__main__":
    import sys
    if "--diagnose" in sys.argv:
        run_diagnostics(); sys.exit(0)
    from model_config import print_config
    print_config(); print()
    print("Sending test message...")
    t0   = time.time()
    resp = call_llm([{"role": "user", "content": "Reply with exactly: BACKEND OK"}],
                    temperature=0.0, max_tokens=20)
    print(f"Response ({time.time()-t0:.1f}s): {resp.strip()}")
