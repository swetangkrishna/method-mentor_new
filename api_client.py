"""
api_client.py — Multi-backend LLM client

HuggingFace backend now has three transport layers (tried in order):
  1. huggingface_hub InferenceClient  — best, handles DNS/auth natively
  2. requests with explicit DNS override via socket patching
  3. urllib + certifi SSL context (original)

Run diagnostic:  python api_client.py --diagnose
"""

import json
import re
import os
import socket
import ssl
import time
import urllib.request
import urllib.error
from typing import List, Dict

from model_config import get_config


# ── SSL context (certifi if available) ───────────────────────────────────────

def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── Transport layer (three fallback levels) ───────────────────────────────────

def _post_huggingface_hub(url: str, payload: dict, token: str, timeout: int) -> dict:
    """
    Level 1: huggingface_hub InferenceClient.
    Uses HF's own HTTP client — handles DNS, auth, retries internally.
    Install: pip install huggingface_hub
    """
    from huggingface_hub import InferenceClient
    model = payload["model"]
    msgs  = payload["messages"]
    temp  = payload.get("temperature", 0.7)
    maxt  = payload.get("max_tokens", 1024)

    provider = payload.get("provider") or os.environ.get("HF_PROVIDER", "auto")
    client = InferenceClient(model=model, provider=provider, token=token, timeout=timeout)
    resp   = client.chat_completion(
        messages=msgs,
        max_tokens=maxt,
        temperature=temp,
        stream=False,
    )
    return {"choices": [{"message": {"content": resp.choices[0].message.content}}]}


def _post_requests_dns_override(url: str, payload: dict, headers: dict,
                                 timeout: int) -> dict:
    """
    Level 2: requests with socket-level DNS override to 8.8.8.8.
    Works when local DNS blocks the HF subdomain but Google DNS doesn't.
    """
    import requests

    # Patch socket.getaddrinfo to use Google DNS for the HF host
    _orig_getaddrinfo = socket.getaddrinfo
    hf_host = "api-inference.huggingface.co"

    def _patched_getaddrinfo(host, port, *args, **kwargs):
        if host == hf_host:
            # Resolve via Google DNS using a direct UDP socket
            try:
                ip = _resolve_via_google_dns(hf_host)
                return _orig_getaddrinfo(ip, port, *args, **kwargs)
            except Exception:
                pass
        return _orig_getaddrinfo(host, port, *args, **kwargs)

    socket.getaddrinfo = _patched_getaddrinfo
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout,
                             verify=True)
        resp.raise_for_status()
        return resp.json()
    finally:
        socket.getaddrinfo = _orig_getaddrinfo


def _resolve_via_google_dns(hostname: str) -> str:
    """
    Minimal DNS-over-UDP resolver querying 8.8.8.8.
    Returns the first A record IP string.
    """
    import struct

    # Build a minimal DNS query packet for hostname A record
    def _encode_name(name):
        parts = name.encode().split(b".")
        return b"".join(bytes([len(p)]) + p for p in parts) + b"\x00"

    tx_id    = os.urandom(2)
    flags    = b"\x01\x00"          # standard query, recursion desired
    counts   = b"\x00\x01" + b"\x00\x00" * 3
    question = _encode_name(hostname) + b"\x00\x01\x00\x01"   # type A, class IN
    packet   = tx_id + flags + counts + question

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    try:
        sock.sendto(packet, ("8.8.8.8", 53))
        data, _ = sock.recvfrom(512)
    finally:
        sock.close()

    # Parse: skip header (12B) + question section, find first answer
    pos = 12
    # Skip question name
    while pos < len(data) and data[pos] != 0:
        if data[pos] & 0xC0 == 0xC0:   # pointer
            pos += 2; break
        pos += data[pos] + 1
    else:
        pos += 1
    pos += 4   # skip QTYPE + QCLASS

    # Skip answer name (may be pointer)
    if data[pos] & 0xC0 == 0xC0:
        pos += 2
    else:
        while data[pos] != 0:
            pos += data[pos] + 1
        pos += 1

    pos += 10  # skip TYPE(2) CLASS(2) TTL(4) RDLENGTH(2)
    ip = ".".join(str(b) for b in data[pos:pos+4])
    return ip


def _post_urllib(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    """Level 3: urllib + certifi. Original transport."""
    data    = json.dumps(payload).encode()
    ctx     = _ssl_ctx()
    req     = urllib.request.Request(url, data=data, headers=headers, method="POST")
    handler = urllib.request.HTTPSHandler(context=ctx)
    opener  = urllib.request.build_opener(handler)
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _hf_post(url: str, payload: dict, token: str, timeout: int,
             use_hub: bool = True) -> dict:
    """
    Try all three transports in order. Return first success.
    Raises RuntimeError with clear fix instructions if all fail.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    errors = {}

    # Level 1: huggingface_hub
    if use_hub:
        try:
            return _post_huggingface_hub(url, payload, token, timeout)
        except ImportError:
            errors["hub"] = "huggingface_hub not installed"
        except Exception as e:
            errors["hub"] = str(e)[:120]

    # Level 2: requests + DNS override
    try:
        return _post_requests_dns_override(url, payload, headers, timeout)
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        errors["requests_dns"] = str(e)[:120]

    # Level 3: urllib + certifi
    try:
        return _post_urllib(url, payload, headers, timeout)
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        errors["urllib"] = str(e)[:120]

    raise RuntimeError(
        f"All three HF transports failed:\n"
        + "\n".join(f"  {k}: {v}" for k, v in errors.items())
        + "\n\nFixes:\n"
        "  pip install huggingface_hub          ← best fix\n"
        "  Or switch to Ollama (no internet needed):\n"
        "    Set BACKEND='ollama' in model_config.py\n"
        "    Install: https://ollama.com → ollama pull qwen2.5:7b"
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
    temp    = max(0.01, min(float(temperature), 1.0))

    payload = {
        "model": model,
        "messages": _with_system(messages, system),
        "max_tokens": max_tokens,
        "temperature": temp,
        "stream": False,
        "provider": cfg.get("provider") or os.environ.get("HF_PROVIDER", "auto"),
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
                raise RuntimeError(
                    f"Model '{model}' still loading. Try again in ~1 min.")
            elif code == 401:
                raise RuntimeError(
                    "HF token invalid. Get a new one: "
                    "https://huggingface.co/settings/tokens")
            elif code == 403:
                raise RuntimeError(
                    f"Access denied to '{model}'.\n"
                    f"Accept its license: https://huggingface.co/{model}\n"
                    f"Or switch to: mistralai/Mistral-Nemo-Instruct-2407")
            elif code == 429:
                if attempt < retries:
                    print(f"  [HF] Rate limited — waiting 60s..."); time.sleep(60); continue
                raise RuntimeError("HF rate limit hit. Wait or upgrade to HF PRO.")
            else:
                raise RuntimeError(f"HF API error {code}: {err[:200]}")


def check_hf_model(model: str, token: str) -> dict:
    url = "https://api-inference.huggingface.co/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5, "temperature": 0.1, "stream": False,
    }
    try:
        _hf_post(url, payload, token, timeout=20)
        return {"available": True, "loaded": True, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 503: return {"available": True, "loaded": False,
                                  "error": "Cold start (loading ~20-60s)"}
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
                 temperature: float, cfg: dict, prefill: str = "") -> str:
    host    = cfg["ollama_host"].rstrip("/")
    full_messages = _with_system(messages, system)
    if prefill:
        # Assistant prefill: Ollama continues from this partial assistant turn,
        # so the model's first generated token follows `prefill`. The API returns
        # only the continuation, so we prepend the prefill back for the parser.
        full_messages = full_messages + [{"role": "assistant", "content": prefill}]
    payload = {
        "model": cfg["model"],
        "messages": full_messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens,
                    "num_ctx": cfg.get("context_length", 8192)},
    }
    headers = {"Content-Type": "application/json"}
    try:
        body = _post_urllib(f"{host}/api/chat", payload, headers,
                            timeout=cfg.get("timeout", 180))
        content = body["message"]["content"]
        return (prefill + content) if prefill else content
    except Exception as e:
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
        with urllib.request.urlopen(req, timeout=5) as resp:
            body   = json.loads(resp.read().decode())
            models = [m["name"] for m in body.get("models", [])]
            return {"running": True, "models": models, "error": None}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)}
# ── Azure AI Foundry ─────────────────────────────────────────────────────────

class AzureBackendError(RuntimeError):
    """Safe machine-readable diagnostics; never includes response bodies or keys."""
    def __init__(self, category, status=None, diagnostics=None):
        self.category=category
        self.status=status
        self.diagnostics=diagnostics or {}
        super().__init__('Azure request failed: '+category)


def _filter_diagnostics(body, phase):
    """Retain only documented filter labels; never provider text or prompts."""
    categories = {'hate', 'sexual', 'violence', 'self_harm', 'jailbreak',
                  'indirect_attack', 'protected_material_text', 'protected_material_code',
                  'custom_blocklists', 'profanity', 'pii', 'groundedness'}
    filters = []
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in categories and isinstance(item, dict):
                    safe = {'category': key}
                    for flag in ('filtered', 'detected', 'blocked'):
                        if type(item.get(flag)) is bool:
                            safe[flag] = item[flag]
                    if item.get('severity') in ('safe', 'low', 'medium', 'high'):
                        safe['severity'] = item['severity']
                    if len(safe) > 1 and safe not in filters:
                        filters.append(safe)
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(body)
    # Foundry's Meta deployment can return labels inside a fixed error message
    # instead of structured category annotations. Extract only known labels.
    labels = {'Jailbreak': 'jailbreak', 'Hate': 'hate', 'Sexual': 'sexual',
              'Violence': 'violence', 'SelfHarm': 'self_harm', 'Self-harm': 'self_harm'}
    def labelled_errors(value):
        if isinstance(value, dict):
            error = value.get('error')
            if isinstance(error, dict) and error.get('code') == 'content_filter':
                match = re.fullmatch(r"Response content blocked by label '([^']+)'\.", str(error.get('message', '')))
                if match and match.group(1) in labels:
                    item = {'category': labels[match.group(1)], 'filtered': True}
                    if item not in filters:
                        filters.append(item)
            for item in value.values():
                if isinstance(item, (dict, list)):
                    labelled_errors(item)
        elif isinstance(value, list):
            for item in value:
                labelled_errors(item)
    labelled_errors(body)
    return {'phase': phase, 'filters': filters}


def _filter_error(body, phase, status=None):
    diagnostic = _filter_diagnostics(body, phase)
    print('AZURE_FILTER_DIAGNOSTIC ' + json.dumps(diagnostic, sort_keys=True), flush=True)
    return AzureBackendError('content_filter', status, diagnostic)


def _tutor_json_to_protocol(content):
    """Validate model-generated fields and decode their transport representation."""
    fields = ('SKILL', 'TUTOR_MOVE', 'REASONING', 'STAGE',
              'STAGE_COMPLETE', 'TASK_SOLVED', 'RESPONSE')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate tutor protocol field')
            result[key] = value
        return result
    data = json.loads(content, object_pairs_hook=unique_pairs)
    if not isinstance(data, dict) or set(data) != set(fields):
        raise ValueError('Incomplete tutor protocol')
    for field in ('SKILL', 'TUTOR_MOVE'):
        if not isinstance(data[field], str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', data[field]):
            raise ValueError('Invalid tutor action field')
    stage = data['STAGE']
    if not ((type(stage) is int and 1 <= stage <= 6) or
            (isinstance(stage, str) and re.fullmatch(r'[1-6]', stage))):
        raise ValueError('Invalid tutor stage')
    for field in ('STAGE_COMPLETE', 'TASK_SOLVED'):
        if data[field] not in ('YES', 'NO'):
            raise ValueError('Invalid tutor completion field')
    if not isinstance(data['REASONING'], str) or not data['REASONING'].strip() or '\n' in data['REASONING'] or '\r' in data['REASONING']:
        raise ValueError('Invalid tutor reasoning field')
    if not isinstance(data['RESPONSE'], str) or not data['RESPONSE'].strip():
        raise ValueError('Empty tutor response')
    if re.search(r'(?im)^\s*(?:SKILL|TUTOR_MOVE|REASONING|STAGE|STAGE_COMPLETE|TASK_SOLVED|RESPONSE)\s*:', data['RESPONSE']):
        raise ValueError('Tutor metadata cannot appear inside the response body')
    # The policy/action and quality checks in agent_turn still validate these
    # generated values. Never fill missing fields from the requested action.
    return '\n'.join(field + ': ' + str(data[field]) for field in fields)


class PrefillContractError(RuntimeError):
    """A generated response did not preserve the requested semantic prefix."""


def _call_azure_foundry(
    messages: List[Dict],
    system: str,
    max_tokens: int,
    temperature: float,
    cfg: dict,
    prefill: str = "",
) -> str:
    """
    Call Microsoft Foundry through its OpenAI-compatible chat-completions API.

    The deployment name is supplied as `model`, e.g. `llama70b`.
    """

    endpoint = cfg["endpoint"].rstrip("/")
    api_key = cfg["api_key"]

    tutor_json = prefill == 'SKILL: '
    if tutor_json:
        system += (
            '\n\nTransport encoding for this response: Return a single JSON object '
            'containing exactly these seven fields representing the tutor protocol '
            'defined above: SKILL (string), TUTOR_MOVE (string), REASONING (one-line '
            'string), STAGE (one digit from 1 to 6 as a string), STAGE_COMPLETE (string YES or NO), '
            'TASK_SOLVED (string YES or NO), RESPONSE (learner-facing string). '
            'Generate every field. The application displays only RESPONSE. Use '
            'JSON without Markdown fences or any text outside the object.'
        )
    elif prefill:
        # Foundry has no native assistant-continuation control. Make the prefix
        # part of generation, including fixed metadata and student sentence stems.
        system += (
            "\n\nOutput format: write the complete assistant response, including the "
            "required opening text below exactly once. Continue with the remaining "
            "response fields and learner-facing text described above. If the opening "
            "ends mid-sentence, complete that sentence. Return plain text without "
            "Markdown fences or a preamble."
            "\nRequired opening text (JSON string): " + json.dumps(prefill)
        )
    msgs = _with_system(messages, system)

    reasoning_profile = cfg.get("request_profile", "classic") == "reasoning"
    token_limit_field = "max_completion_tokens" if reasoning_profile else "max_tokens"
    payload = {
        "model": cfg["model"],
        "messages": msgs,
        token_limit_field: max(1600, max_tokens) if reasoning_profile else max_tokens,
        "stream": False,
    }
    if not reasoning_profile:
        payload["temperature"] = temperature

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    if tutor_json:
        payload['response_format'] = {'type': 'json_object'}

    protocol_failures = 0
    prefix_failures=0
    length_retried=False
    for attempt in range(3):
        try:
            body = _post_urllib(f"{endpoint}/chat/completions",payload,headers,timeout=cfg.get("timeout",300))
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # Recognise provider safety refusals without exposing raw bodies.
                try:
                    failure = json.loads(e.read(65536))
                    blocked = (isinstance(failure, dict) and (
                        any(isinstance(c, dict) and c.get('finish_reason') == 'content_filter'
                            for c in (failure.get('choices') or [])) or
                        (isinstance(failure.get('error'), dict) and
                         failure['error'].get('code') == 'content_filter')))
                except (ValueError, TypeError, AttributeError):
                    blocked = False
                if blocked:
                    raise _filter_error(failure, 'request', 400) from None
            if e.code in (429,500,502,503,504) and attempt<2:
                try:delay=float(e.headers.get('Retry-After',1+attempt))
                except (ValueError,TypeError,AttributeError):delay=1+attempt
                # Honor the provider's short token-quota reset instead of
                # immediately failing a safely retryable tutoring request.
                wait_limit = 60 if e.code == 429 else 10
                if 0<=delay<=wait_limit:
                    time.sleep(delay)
                    continue
            raise AzureBackendError('http_'+str(e.code),e.code) from None
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if attempt<2:
                time.sleep(1+attempt)
                continue
            raise AzureBackendError('transport') from None
        try:
            choice=body['choices'][0]
            content=choice['message']['content']
        except (KeyError,IndexError,TypeError):
            raise AzureBackendError('invalid_response') from None
        if choice.get('finish_reason')=='content_filter':
            raise _filter_error(body, 'completion')
        if choice.get('finish_reason')=='length':
            # Retry a complete answer once; never accept truncated metadata/body.
            if not length_retried and attempt<2 and payload[token_limit_field]<4096:
                payload[token_limit_field]=min(4096,payload[token_limit_field]*2)
                length_retried=True
                continue
            raise AzureBackendError('truncated')
        if not isinstance(content,str) or not content.strip():
            raise AzureBackendError('empty_response')
        if tutor_json:
            try:
                return _tutor_json_to_protocol(content)
            except (ValueError, TypeError):
                protocol_failures += 1
                if protocol_failures >= 2 or attempt == 2:
                    raise AzureBackendError('invalid_protocol') from None
                payload['messages'] = _with_system(messages, system +
                    '\nReturn a JSON object with all seven required fields and the specified types. '
                    'Use YES or NO strings for the completion fields. No field may be omitted.')
                if not reasoning_profile:
                    payload['temperature'] = 0.0
                continue
        if not prefill or content.startswith(prefill):return content
        prefix_failures+=1
        if prefix_failures>=2 or attempt==2:
            raise PrefillContractError('Azure did not preserve the required response prefix after bounded attempts.')
        payload['messages']=_with_system(messages,system+(
            '\nYour previous attempt did not reproduce the required prefix. '
            'Copy that prefix EXACTLY, including all header values and spaces, '
            'then continue. Do not rewrite or summarize any prefix text.'))
        if not reasoning_profile:
            payload['temperature']=0.0
    raise AzureBackendError('retry_exhausted')

# ── vLLM (OpenAI-compatible local server on the cluster) ──────────────────────

# Stop sequences. Without these the model happily keeps generating past the end
# of its own turn and starts writing the OTHER speaker's lines — the mentor
# inventing the student's reply, or echoing the prompt scaffolding. Qwen2.5 was
# well-behaved here; Llama-3.1-8B is not, which is why this became visible only
# after the model swap.
#
# Two groups:
#   1. Chat-template special tokens for BOTH families (Qwen <|im_*|>, Llama
#      <|eot_id|>/<|start_header_id|>). vLLM normally stops on the model's own
#      EOS, but a prefill+continue_final_message turn can slip past it.
#   2. Conversational role headers. Neither role should EVER write these, so
#      seeing one means the model has jumped to the other speaker's turn.
DEFAULT_STOP = [
    # special tokens
    "<|im_end|>", "<|im_start|>", "<|eot_id|>", "<|start_header_id|>",
    "<|end_header_id|>", "<|endoftext|>",
    # role leaks (the model impersonating the other side)
    "\nUser:", "\nUSER:", "\nStudent:", "\nSTUDENT", "\nHuman:",
    "\nMentor:", "\nMENTOR", "\nAoife:", "\nAssistant:", "\nASSISTANT:",
    "\nTeacher:", "\nSupervisor:",
    # prompt-scaffolding echoes
    "\n## Available skills", "\nAvailable skills:",
]


def _call_vllm(messages: List[Dict], system: str, max_tokens: int,
               temperature: float, cfg: dict, prefill: str = "") -> str:
    """
    Call a local vLLM server via its OpenAI-compatible /v1/chat/completions API.

    Assistant prefill is supported through vLLM's chat-template controls: when the
    final message is an assistant message, setting `continue_final_message: true`
    and `add_generation_prompt: false` makes the model CONTINUE that message rather
    than start a new turn. The API returns only the continuation, so we prepend the
    prefill back so downstream parsers see the full text — identical contract to the
    Ollama path, so persona/agent code needs no changes.
    """
    host = cfg["vllm_host"].rstrip("/")
    msgs = _with_system(messages, system)

    extra = {}
    if prefill:
        msgs = msgs + [{"role": "assistant", "content": prefill}]
        # vLLM-specific flags passed straight through the OpenAI payload.
        extra["continue_final_message"] = True
        extra["add_generation_prompt"] = False

    payload = {
        "model": cfg["model"],
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "stop": DEFAULT_STOP,
        **extra,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', 'EMPTY')}",
    }
    try:
        body = _post_urllib(f"{host}/v1/chat/completions", payload, headers,
                            timeout=cfg.get("timeout", 300))
        content = body["choices"][0]["message"]["content"]
        return (prefill + content) if prefill else content
    except Exception as e:
        raise RuntimeError(
            f"vLLM server unreachable at {host}.\n"
            f"Fix: ensure the vLLM server launched in your Slurm job is healthy "
            f"(check the .err/.out logs and that --port matches VLLM_HOST).\n"
            f"Detail: {e}"
        )


def check_vllm_running() -> dict:
    """Health check: query the vLLM /v1/models endpoint to confirm it is serving."""
    cfg  = get_config()
    host = cfg.get("vllm_host", "http://localhost:8000").rstrip("/")
    key  = cfg.get("api_key", "EMPTY")
    try:
        req = urllib.request.Request(
            f"{host}/v1/models", method="GET",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body   = json.loads(resp.read().decode())
            models = [m.get("id", "") for m in body.get("data", [])]
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
        body = _post_urllib("https://api.anthropic.com/v1/messages",
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
             temperature: float = 0.7, role: str = "default",
             prefill: str = "") -> str:
    cfg = get_config(role)
    b   = cfg["backend"]
    if b == "azure_foundry":
        return _call_azure_foundry(messages, system, max_tokens, temperature, cfg, prefill)
    elif b == "vllm":
        return _call_vllm(messages, system, max_tokens, temperature, cfg, prefill)
    elif b == "ollama":
        return _call_ollama(messages, system, max_tokens, temperature, cfg, prefill)
    elif b == "huggingface":
        return _call_hf(messages, system, max_tokens, temperature, cfg)
    elif b == "anthropic":
        return _call_anthropic(messages, system, max_tokens, temperature)
    raise ValueError(f"Unknown backend '{b}'.")


def call_llm_precise(messages: List[Dict], system: str = "",
                     max_tokens: int = 1024, role: str = "scorer") -> str:
    return call_llm(messages, system=system, max_tokens=max_tokens,
                    temperature=0.05, role=role)


call_claude          = call_llm
call_claude_low_temp = call_llm_precise


# ── Diagnostic ────────────────────────────────────────────────────────────────

def run_diagnostics():
    import sys, platform
    print("=" * 56)
    print("  Pedagogical RL — Network & API Diagnostic v2")
    print("=" * 56)

    print(f"\n[1] Python  : {sys.version.split()[0]}  "
          f"({platform.system()} {platform.machine()})")
    try:
        import certifi
        print(f"    certifi : {certifi.__version__}")
    except ImportError:
        print("    certifi : NOT installed")

    try:
        import huggingface_hub
        print(f"    hf_hub  : {huggingface_hub.__version__}  ← preferred transport")
    except ImportError:
        print("    hf_hub  : NOT installed  ← run: pip install huggingface_hub")

    print("\n[2] DNS resolution tests...")
    for host in ["example.com", "huggingface.co", "api-inference.huggingface.co"]:
        try:
            ip = socket.gethostbyname(host)
            print(f"    {host:42s} → {ip}")
        except socket.gaierror as e:
            print(f"    {host:42s} → FAIL ({e})")

    print("\n[3] Google DNS direct resolution (8.8.8.8)...")
    for host in ["huggingface.co", "api-inference.huggingface.co"]:
        try:
            ip = _resolve_via_google_dns(host)
            print(f"    {host:42s} → {ip}  ✓")
        except Exception as e:
            print(f"    {host:42s} → FAIL ({e})")

    print("\n[4] HTTPS reachability...")
    for url, label in [
        ("https://example.com", "example.com"),
        ("https://huggingface.co", "huggingface.co"),
        ("https://api-inference.huggingface.co", "HF API endpoint"),
    ]:
        try:
            ctx = _ssl_ctx()
            req = urllib.request.Request(url, method="HEAD")
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener  = urllib.request.build_opener(handler)
            with opener.open(req, timeout=8) as r:
                print(f"    {label:42s} HTTP {r.status}  ✓")
        except Exception as e:
            print(f"    {label:42s} FAIL: {e}")

    print("\n[5] huggingface_hub transport test...")
    cfg   = get_config()
    token = cfg.get("hf_token") or os.environ.get("HF_TOKEN", "")
    if not token:
        print("    HF_TOKEN not set — skipping")
    else:
        try:
            from huggingface_hub import InferenceClient
            model = cfg.get("model", "Qwen/Qwen2.5-7B-Instruct")
            provider = cfg.get("provider") or os.environ.get("HF_PROVIDER", "auto")
            print(f"    Testing model={model} provider={provider}")
            client = InferenceClient(
                model=model, provider=provider,
                token=token, timeout=30,
            )
            resp = client.chat_completion(
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5, stream=False,
            )
            print(f"    OK — response: {resp.choices[0].message.content.strip()}")
            print("    huggingface_hub transport works! HF backend is ready.")
        except ImportError:
            print("    huggingface_hub not installed.")
            print("    Fix: pip install huggingface_hub")
        except Exception as e:
            print(f"    FAIL: {e}")

    print("\n" + "=" * 56)
    print("  Recommended fix for your setup:")
    print("    export HF_MODEL=Qwen/Qwen2.5-7B-Instruct")
    print("    export HF_PROVIDER=together")
    print("    python api_client.py --diagnose")
    print("=" * 56 + "\n")


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
