"""선택 사항: Claude API로 JSON 응답 받기.

ANTHROPIC_API_KEY 가 없거나 호출이 실패하면 None 을 돌려주고,
호출한 쪽은 규칙 기반 결과를 그대로 쓴다. (해커톤 현장 네트워크가 불안해도 데모가 멈추지 않게)
모델은 PLACELIST_MODEL 환경변수로 바꿀 수 있다.
"""
import json
import os
import re
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"


def ask_json(prompt, max_tokens=600):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = {
        "model": os.environ.get("PLACELIST_MODEL", "claude-haiku-5-5"),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = "".join(b.get("text", "") for b in json.load(r).get("content", []))
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None
