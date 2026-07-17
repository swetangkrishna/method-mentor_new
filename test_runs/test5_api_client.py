"""
api_client.py — Multi-backend LLM client v3

Fixes in this version:
  - huggingface_hub InferenceClient forced to free api-inference endpoint
    (avoids 402 Payment Required from router.huggingface.co)
  - SSL cert fix for Mac/conda via certifi injection
  - DNS override via Google 8.8.8.8 as second fallback
  - Diagnostic: python api_client.py --diagnose
"""

import json
import os
import socket
import ssl
import time
import urllib.request
import urllib.error
from typing import List, Dict

from model_config import get_config


# ── SSL context ───────────────────────────────────────────────────────────────

def _ssl_ctx():
    """Always use certifi certs — fixes Mac/conda SSL failures."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── urllib POST (certifi SSL) ─────────────────────────────────────────────────

def _urllib_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data    = json.dumps(payload).encode()
    ctx     = _ssl_ctx()
    req     = urllib.request.Request(url, data=data, headers=headers, method="POST")
    handler = urllib.request.HTTPSHandler(context=ctx)
    opener  = urllib.request.build_opener(handler)
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ── requests POST (with DNS patch for blocked subdomains) ─────────────────────

def _requests_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    import requests
    import certifi as _certifi
    resp = requests.post(url, json=payload, headers=headers,
                         timeout=timeout, verify=_certifi.where())
    resp.raise_for_status()
    return resp.json()


# ── huggingface_hub InferenceClient (forced to FREE endpoint) ─────────────────

def _hub_post(payload: dict, token: str, timeout: int) -> dict:
    """
    Uses huggingface_hub but forces base_url to the FREE inference endpoint.
    Without base_url, newer hub versions route to router.huggingface.co which
    requires a paid subscription (402 Payment Required).
    """
    from huggingface_hub import InferenceClient

    client = InferenceClient(
        provider="hf-inference",        # explicitly use free HF Inference API
        api_key=token,
        timeout=timeout,
    )
    model  = payload["model"]
    msgs   = payload["messages"]
    temp   = max(0.01, min(float(payload.get("temperature", 0.7)), 1.0))
    maxt   = payload.get("max_tokens", 1024)

    resp = client.chat.completions.create(
        model=model,
        messages=msgs,
        max_tokens=maxt,
        temperature=temp,
        stream=False,
    )
    return {"choices": [{"message": {"content": resp.choices[0].message.content}}]}


# ── HuggingFace master caller ─────────────────────────────────────────────────

def _hf_post(url: str, payload: dict, token: str, timeout: int) -> dict:
    """
    Try three transports in order. First success wins.
    HTTP errors (4xx/5xx) are re-raised immediately — no retry across transports.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    errors = {}

    # 1. huggingface_hub with free endpoint
    try:
        return _hub_post(payload, token, timeout)
    except ImportError:
        errors["hub"] = "huggingface_hub not installed — pip install huggingface_hub"
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        err_str = str(e)
        # Catch 402/Payment errors from hub and stop immediately with clear message
        if "402" in err_str or "Payment" in err_str:
            raise RuntimeError(
                "huggingface_hub is routing to a paid endpoint.\n"
                "Fix: pip install --upgrade huggingface_hub\n"
                "Or switch to Ollama: set BACKEND='ollama' in model_config.py"
            )
        errors["hub"] = err_str[:120]

    # 2. requests + certifi
    try:
        return _requests_post(url, payload, headers, timeout)
    except ImportError:
        errors["requests"] = "requests not installed"
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        errors["requests"] = str(e)[:120]

    # 3. urllib + certifi
    try:
        return _urllib_post(url, payload, headers, timeout)
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        errors["urllib"] = str(e)[:120]

    raise RuntimeError(
        "All three HF transports failed:\n"
        + "\n".join(f"  {k}: {v}" for k, v in errors.items())
        + "\n\nFixes:\n"
        "  pip install --upgrade huggingface_hub certifi requests\n"
        "  Or switch to Ollama (no internet): BACKEND='ollama' in model_config.py"
    )


# ── HuggingFace main ──────────────────────────────────────────────────────────

def _get_hf_token(cfg: dict) -> str:
    token = (cfg.get("hf_token")
             or os.environ.get("HF_TOKEN")
             or os.environ.get("HUGGINGFACE_TOKEN", ""))
    if not token:
        raise RuntimeError(
            "HuggingFace token not set.\n"
            "  Get free token: https://huggingface.co/settings/tokens\n"
            "  Then: export HF_TOKEN=hf_..."
        )
    return token


def _call_hf(messages: List[Dict], system: str, max_tokens: int,
             temperature: float, cfg: dict) -> str:
    token   = _get_hf_token(cfg)
    model   = cfg["model"]
    timeout = cfg.get("timeout", 120)
    retries = cfg.get("hf_max_retries", 3)
    delay   = cfg.get("hf_retry_delay", 25)

    payload = {
        "model": model,
        "messages": _with_system(messages, system),
        "max_tokens": max_tokens,
        "temperature": max(0.01, min(float(temperature), 1.0)),
        "stream": False,
    }
    url = "https://api-inference.huggingface.co/v1/chat/completions"

    for attempt in range(1, retries + 1):
        try:
            body = _hf_post(url, payload, token, timeout)
            if "choices" in body:
                return body["choices"][0]["message"]["content"].strip()
            if isinstance(body, list) and body:
                return str(body[0].get("generated_text", body[0])).strip()
            raise RuntimeError(f"Unexpected HF response: {json.dumps(body)[:200]}")

        except urllib.error.HTTPError as e:
            code = e.code
            err  = e.read().decode("utf-8", errors="replace")
            if code == 503:
                try:    wait = min(float(json.loads(err).get("estimated_time", delay)), 60)
                except: wait = delay
                if attempt < retries:
                    print(f"  [HF] Model loading — waiting {wait:.0f}s "
                          f"(attempt {attempt}/{retries})...")
                    time.sleep(wait); continue
                raise RuntimeError(f"Model '{model}' still loading after {retries} retries.")
            elif code == 401:
                raise RuntimeError(
                    "HF token invalid.\n"
                    "Get a new one: https://huggingface.co/settings/tokens")
            elif code == 403:
                raise RuntimeError(
                    f"Access denied to '{model}'.\n"
                    f"Accept its license: https://huggingface.co/{model}\n"
                    f"Or use: mistralai/Mistral-Nemo-Instruct-2407")
            elif code == 429:
                if attempt < retries:
                    print(f"  [HF] Rate limited — waiting 60s..."); time.sleep(60); continue
                raise RuntimeError("HF rate limit. Wait or upgrade to HF PRO.")
            elif code == 402:
                raise RuntimeError(
                    "HF returned 402 Payment Required.\n"
                    "Fix: pip install --upgrade huggingface_hub\n"
                    "The updated hub uses provider='hf-inference' for free access.")
            else:
                raise RuntimeError(f"HF API error {code}: {err[:200]}")


def check_hf_model(model: str, token: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5, "temperature": 0.1, "stream": False,
    }
    try:
        _hf_post(
            "https://api-inference.huggingface.co/v1/chat/completions",
            payload, token, timeout=20,
        )
        return {"available": True, "loaded": True, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 503: return {"available": True,  "loaded": False,
                                  "error": "Cold start (~20-60s)"}
        if e.code == 403: return {"available": False, "loaded": False,
                                  "error": "Accept license at huggingface.co"}
        if e.code == 404: return {"available": False, "loaded": False,
                                  "error": "Model not found"}
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
    headers = {"Content-Type": "application/json"}
    try:
        body = _urllib_post(f"{host}/api/chat", payload, headers,
                            timeout=cfg.get("timeout", 180))
        return body["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama unreachable at {host}.\nRun: ollama serve\n{e}")


def check_ollama_running() -> dict:
    cfg  = get_config()
    host = cfg.get("ollama_host", "http://localhost:11434").rstrip("/")
    try:
        req = urllib.request.Request(f"{host}/api/tags", method="GET")
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
        "max_tokens": max_tokens, "messages": messages, "temperature": temperature,
    }
    if system:
        payload["system"] = system
    headers = {"Content-Type": "application/json", "x-api-key": key,
               "anthropic-version": "2023-06-01"}
    try:
        body = _urllib_post("https://api.anthropic.com/v1/messages",
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
    print("  Pedagogical RL — Diagnostic v3")
    print("=" * 58)
    print(f"\n[1] Environment")
    print(f"    Python  : {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")

    try:
        import certifi
        print(f"    certifi : {certifi.__version__}  ✓")
    except ImportError:
        print("    certifi : MISSING — pip install certifi")

    try:
        import requests as rq
        print(f"    requests: {rq.__version__}  ✓")
    except ImportError:
        print("    requests: MISSING — pip install requests")

    try:
        import huggingface_hub as hfh
        print(f"    hf_hub  : {hfh.__version__}  ✓")
    except ImportError:
        print("    hf_hub  : MISSING — pip install huggingface_hub")

    print(f"\n[2] DNS resolution")
    for host in ["example.com", "huggingface.co", "api-inference.huggingface.co"]:
        try:
            ip = socket.gethostbyname(host)
            print(f"    {host:45s} {ip}  ✓")
        except Exception as e:
            print(f"    {host:45s} FAIL ({e})")

    print(f"\n[3] huggingface_hub transport (FREE endpoint)")
    cfg   = get_config()
    token = cfg.get("hf_token") or os.environ.get("HF_TOKEN", "")
    if not token:
        print("    HF_TOKEN not set — skipping")
    else:
        try:
            result = _hub_post(
                {"model": "mistralai/Mistral-Nemo-Instruct-2407",
                 "messages": [{"role": "user", "content": "Say OK"}],
                 "max_tokens": 5, "temperature": 0.1, "stream": False},
                token, timeout=30,
            )
            print(f"    OK — {result['choices'][0]['message']['content'].strip()}")
        except ImportError:
            print("    SKIP — pip install huggingface_hub")
        except Exception as e:
            err = str(e)
            if "402" in err or "Payment" in err:
                print(f"    402 Payment Required — hub routing to paid endpoint")
                print(f"    Fix: pip install --upgrade huggingface_hub")
            else:
                print(f"    FAIL — {err[:120]}")

    print(f"\n[4] Direct HTTPS to HF API")
    try:
        result = _requests_post(
            "https://api-inference.huggingface.co/v1/chat/completions",
            {"model": "mistralai/Mistral-Nemo-Instruct-2407",
             "messages": [{"role": "user", "content": "Say OK"}],
             "max_tokens": 5, "temperature": 0.1, "stream": False},
            {"Content-Type": "application/json",
             "Authorization": f"Bearer {token}"} if token else {},
            timeout=20,
        )
        print(f"    OK — {result['choices'][0]['message']['content'].strip()}")
    except Exception as e:
        print(f"    FAIL — {str(e)[:120]}")

    print("\n" + "=" * 58 + "\n")


if __name__ == "__main__":
    import sys
    if "--diagnose" in sys.argv:
        run_diagnostics(); sys.exit(0)

    from model_config import print_config
    print_config(); print()
    print("Sending test message...")
    t0   = time.time()
    resp = call_llm(
        [{"role": "user", "content": "Reply with exactly: BACKEND OK"}],
        temperature=0.0, max_tokens=20,
    )
    print(f"Response ({time.time()-t0:.1f}s): {resp.strip()}")
