from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research.secrets import load_secret_file


def extract_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks)


def summarize_http_error(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception:
        return f"HTTP {exc.code}"

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    error_type = error.get("type", "unknown_error")
    error_code = error.get("code", "unknown_code")
    param = error.get("param")
    return f"HTTP {exc.code}: type={error_type}, code={error_code}, param={param}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiny OpenAI Responses API smoke test.")
    parser.add_argument("--model", default="gpt-5.4", help="Model slug to test; default follows local project note.")
    parser.add_argument("--secrets", default="secrets.txt", help="Local secret file, ignored by git.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL.")
    args = parser.parse_args()

    secrets = load_secret_file(args.secrets)
    api_key = secrets.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("No OPENAI_API_KEY found in local secrets file.", file=sys.stderr)
        return 2
    base_url = args.base_url or secrets.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    body = {
        "model": args.model,
        "input": "Reply with exactly: OK",
        "max_output_tokens": 8,
    }
    request = Request(
        f"{base_url.rstrip('/')}/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"OpenAI smoke test failed: {summarize_http_error(exc)}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"OpenAI smoke test failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"model": args.model, "text": extract_text(payload)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
