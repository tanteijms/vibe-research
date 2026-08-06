from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research.secrets import load_secret_file


JsonDict = dict[str, Any]


def _safe_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _safe_body_summary(payload: object) -> JsonDict:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return {
                "error_type": error.get("type"),
                "error_code": error.get("code"),
                "error_param": error.get("param"),
                "error_message": str(error.get("message", ""))[:240],
            }
        return {"keys": sorted(payload)[:20]}
    if isinstance(payload, list):
        return {"list_length": len(payload)}
    text = str(payload)
    return {
        "text": text[:240],
        "looks_like_html": "<html" in text.lower() or "<!doctype html" in text.lower(),
    }


def request_once(
    *,
    url: str,
    method: str,
    headers: JsonDict,
    body: JsonDict | None,
    timeout: int,
) -> JsonDict:
    request = Request(
        url,
        data=_safe_json_bytes(body) if body is not None else None,
        headers={str(key): str(value) for key, value in headers.items()},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw
            summary = _safe_body_summary(payload)
            looks_like_html = bool(summary.get("looks_like_html")) if isinstance(summary, dict) else False
            return {
                "ok": not looks_like_html,
                "status": response.status,
                "summary": summary,
            }
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return {
            "ok": False,
            "status": exc.code,
            "summary": _safe_body_summary(payload),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": None,
            "summary": {"url_error": str(exc.reason)},
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "summary": {
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc)[:240],
            },
        }


def probe_report(
    *,
    api_key: str,
    base_url: str,
    models: list[str],
    timeout: int,
) -> JsonDict:
    probes: list[JsonDict] = []
    normalized_base = base_url.rstrip("/")
    common_headers = {
        "Content-Type": "application/json",
    }
    header_variants = [
        (
            "authorization_bearer",
            {
                **common_headers,
                "Authorization": f"Bearer {api_key}",
            },
        ),
        (
            "x_api_key",
            {
                **common_headers,
                "x-api-key": api_key,
            },
        ),
        (
            "both_headers",
            {
                **common_headers,
                "Authorization": f"Bearer {api_key}",
                "x-api-key": api_key,
            },
        ),
    ]
    path_specs = [
        ("GET", "/models", None),
        ("GET", "/v1/models", None),
        ("POST", "/responses", {"model": models[0], "input": "Reply with exactly: OK", "max_output_tokens": 8}),
        ("POST", "/v1/responses", {"model": models[0], "input": "Reply with exactly: OK", "max_output_tokens": 8}),
        (
            "POST",
            "/chat/completions",
            {
                "model": models[0],
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 8,
            },
        ),
        (
            "POST",
            "/v1/chat/completions",
            {
                "model": models[0],
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 8,
            },
        ),
    ]

    for header_name, headers in header_variants:
        for method, path, body in path_specs:
            item: JsonDict = {
                "header_variant": header_name,
                "method": method,
                "path": path,
            }
            item.update(
                request_once(
                    url=f"{normalized_base}{path}",
                    method=method,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )
            )
            probes.append(item)

    model_checks: list[JsonDict] = []
    for model in models:
        body = {"model": model, "input": "Reply with exactly: OK", "max_output_tokens": 8}
        result = request_once(
            url=f"{normalized_base}/responses",
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body=body,
            timeout=timeout,
        )
        model_checks.append({"model": model, **result})

    return {
        "base_url": normalized_base,
        "probe_count": len(probes),
        "probes": probes,
        "model_checks": model_checks,
        "any_success": any(item["ok"] for item in probes) or any(item["ok"] for item in model_checks),
    }


def write_report(output_dir: Path, report: JsonDict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "endpoint_probe_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = [
        "# Endpoint Probe Report",
        "",
        f"- base_url: `{report['base_url']}`",
        f"- probe_count: `{report['probe_count']}`",
        f"- any_success: `{report['any_success']}`",
        "",
        "## Model Checks",
        "",
    ]
    for item in report["model_checks"]:
        lines.append(
            f"- `{item['model']}`: ok=`{item['ok']}`, status=`{item['status']}`, summary=`{json.dumps(item['summary'], ensure_ascii=False)}`"
        )
    lines.extend(["", "## Path/Header Probe", ""])
    for item in report["probes"]:
        lines.append(
            f"- `{item['header_variant']} {item['method']} {item['path']}`: ok=`{item['ok']}`, status=`{item['status']}`, summary=`{json.dumps(item['summary'], ensure_ascii=False)}`"
        )
    lines.append("")
    (output_dir / "endpoint_probe_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe an OpenAI-compatible endpoint with multiple paths and auth styles.")
    parser.add_argument("--secrets", default="secrets.txt", help="Local secret file, ignored by git.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL; overrides secrets.")
    parser.add_argument("--models", nargs="+", default=["gpt-5.4", "gpt-5.5"], help="Model slugs to probe.")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--output-dir",
        default="yys/all/0802/endpoint_probe",
        help="Directory for the probe report.",
    )
    args = parser.parse_args(argv)

    secrets = load_secret_file(args.secrets)
    api_key = os.environ.get("OPENAI_API_KEY") or secrets.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("No OPENAI_API_KEY found in local secrets file.", file=sys.stderr)
        return 2
    base_url = os.environ.get("OPENAI_BASE_URL") or args.base_url or secrets.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    report = probe_report(
        api_key=api_key,
        base_url=base_url,
        models=args.models,
        timeout=args.timeout,
    )
    write_report(Path(args.output_dir).resolve(), report)
    print(
        json.dumps(
            {
                "base_url": report["base_url"],
                "probe_count": report["probe_count"],
                "any_success": report["any_success"],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["any_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
