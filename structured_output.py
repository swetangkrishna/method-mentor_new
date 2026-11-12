"""Strict JSON decoding with optional enclosing Markdown code fences."""
import json
import re


def clean_json_response(text: str) -> str:
    text = text.strip()
    match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text,
                         flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else text


def parse_json_response(text: str) -> dict:
    value = json.loads(clean_json_response(text))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value
