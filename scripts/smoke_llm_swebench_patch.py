from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import SweBenchLocalPatchExecutor
from vibe_research.secrets import load_secret_file


JsonDict = dict[str, Any]


def extract_text(payload: JsonDict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
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


def call_responses_api(
    *,
    api_key: str,
    base_url: str,
    model: str,
    input_text: str,
    max_output_tokens: int,
) -> tuple[str, JsonDict]:
    body = {
        "model": model,
        "input": input_text,
        "max_output_tokens": max_output_tokens,
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

    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return extract_text(payload), payload


def parse_json_object(text: str) -> JsonDict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped.strip(), flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("model did not return a JSON object")
    return payload


def clean_patch(raw_patch: object) -> str:
    patch = str(raw_patch or "").strip()
    if patch.startswith("```"):
        patch = re.sub(r"^```(?:diff|patch)?", "", patch.strip(), flags=re.IGNORECASE).strip()
        patch = re.sub(r"```$", "", patch).strip()
    diff_start = patch.find("diff --git ")
    if diff_start > 0:
        patch = patch[diff_start:]
    return patch.rstrip() + ("\n" if patch.strip() else "")


def safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe[:120] or "instance"


def read_repo_files(repo_path: Path, *, max_chars: int = 12_000) -> str:
    blocks: list[str] = []
    total = 0
    for file_path in sorted(path for path in repo_path.rglob("*.py") if path.is_file()):
        rel = file_path.relative_to(repo_path).as_posix()
        content = file_path.read_text(encoding="utf-8")
        block = f"### {rel}\n```python\n{content}\n```\n"
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n".join(blocks)


def patch_prompt(*, instance, repo_files: str) -> str:
    return (
        "You are the patch-generation brain inside the Harness x Hermes runtime.\n"
        "The harness will apply the regression test patch first, then apply your candidate patch, "
        "then run the test command. Return a source-code fix only.\n\n"
        "Output JSON only, no markdown. Schema:\n"
        "{\"patch\": string, \"reason\": string, \"risk\": string}\n\n"
        "Patch requirements:\n"
        "- The patch must be a unified git diff applicable from the repository root by `git apply`.\n"
        "- Do not edit test files; the harness already owns the regression test patch.\n"
        "- Prefer the smallest correct source change.\n\n"
        f"Instance id: {instance.instance_id}\n"
        f"Problem statement: {instance.problem_statement}\n"
        f"Regression test patch that will be applied before your patch:\n{instance.test_patch}\n"
        f"Current repository files:\n{repo_files}\n"
    )


def write_outputs(output_dir: Path, report: JsonDict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "llm_swebench_patch_smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = [
        "# LLM SWE-bench-style Patch Smoke Report",
        "",
        f"- model: `{report['model']}`",
        f"- ready: `{report['ready']}`",
        f"- model_call_count: `{report['model_call_count']}`",
        f"- model_json_parse_success_count: `{report['model_json_parse_success_count']}`",
        f"- executor_contract_ready: `{report['executor_contract_ready']}`",
        f"- instance_count: `{report['instance_count']}`",
        f"- tests_passed_count: `{report['tests_passed_count']}`",
        f"- all_model_patches_tests_passed: `{report['all_model_patches_tests_passed']}`",
        f"- hydration_safe_count: `{report['hydration_safe_count']}`",
        f"- evidence_sound_count: `{report['evidence_sound_count']}`",
        f"- patch_equal_to_gold_count: `{report['patch_equal_to_gold_count']}`",
        f"- mean_patch_line_jaccard: `{report['mean_patch_line_jaccard']}`",
        "",
        "## Instance outcomes",
        "",
    ]
    for result in report["instance_results"]:
        lines.extend(
            [
                f"- `{result['instance_id']}`: tests_passed=`{result['tests_passed']}`, "
                f"patch_equal_to_gold=`{result['patch_equal_to_gold']}`, "
                f"hydration_safe=`{result['hydration_safe']}`",
            ]
        )
    lines.append("")
    if report["model_failures"]:
        lines.extend(["## Model failures", ""])
        lines.extend(f"- {failure}" for failure in report["model_failures"])
        lines.append("")
    (output_dir / "llm_swebench_patch_smoke_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-LLM patch generation through the local SWE-bench-style executor.")
    parser.add_argument("--model", default="gpt-5.4", help="Responses API model slug.")
    parser.add_argument("--secrets", default="secrets.txt", help="Local secret file, ignored by git.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL; overrides secrets.")
    parser.add_argument("--limit", type=int, default=2, help="Number of local demo instances to solve.")
    parser.add_argument(
        "--output-dir",
        default="yys/all/0802/llm_swebench_patch_smoke",
        help="Directory for reports and executor artifacts.",
    )
    args = parser.parse_args()

    secrets = load_secret_file(args.secrets)
    api_key = secrets.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("No OPENAI_API_KEY found in local secrets file.", file=sys.stderr)
        return 2
    base_url = args.base_url or secrets.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    output_dir = Path(args.output_dir).resolve()
    source_repo_root = output_dir / "source_repos"
    instances = SweBenchLocalPatchExecutor.demo_instances(source_repo_root)[: max(0, args.limit)]
    generated_instances = []
    predictions: list[JsonDict] = []
    model_failures: list[str] = []
    parse_success_count = 0

    for instance in instances:
        repo_path = Path(str(instance.metadata["local_repo_path"]))
        prompt = patch_prompt(instance=instance, repo_files=read_repo_files(repo_path))
        try:
            text, raw_payload = call_responses_api(
                api_key=api_key,
                base_url=base_url,
                model=args.model,
                input_text=prompt,
                max_output_tokens=1400,
            )
            model_payload = parse_json_object(text)
            parse_success_count += 1
            candidate_patch = clean_patch(model_payload.get("patch") or model_payload.get("model_patch"))
            reason = str(model_payload.get("reason") or "")
            risk = str(model_payload.get("risk") or "")
            response_id = str(raw_payload.get("id") or "")
        except (HTTPError, URLError) as exc:
            if isinstance(exc, HTTPError):
                model_failures.append(f"{instance.instance_id}: {summarize_http_error(exc)}")
            else:
                model_failures.append(f"{instance.instance_id}: {exc}")
            candidate_patch = ""
            reason = ""
            risk = ""
            response_id = ""
        except Exception as exc:
            model_failures.append(f"{instance.instance_id}: {exc}")
            candidate_patch = ""
            reason = ""
            risk = ""
            response_id = ""

        patch_ref = output_dir / "model_patches" / f"{safe_name(instance.instance_id)}.patch"
        patch_ref.parent.mkdir(parents=True, exist_ok=True)
        patch_ref.write_text(candidate_patch, encoding="utf-8")
        predictions.append(
            {
                "instance_id": instance.instance_id,
                "model": args.model,
                "response_id": response_id,
                "candidate_patch_ref": str(patch_ref),
                "candidate_patch_line_count": len([line for line in candidate_patch.splitlines() if line.strip()]),
                "reason": reason,
                "risk": risk,
            }
        )
        generated_instances.append(
            replace(
                instance,
                candidate_patch=candidate_patch,
                metadata={
                    **instance.metadata,
                    "candidate_patch_source": "real_llm",
                    "candidate_patch_model": args.model,
                    "candidate_patch_ref": str(patch_ref),
                    "candidate_response_id": response_id,
                },
            )
        )

    executor_report = SweBenchLocalPatchExecutor(generated_instances).run(output_dir / "runs")
    instance_results = [result.to_dict() for result in executor_report.instance_results]
    all_tests_passed = (
        executor_report.instance_count > 0
        and executor_report.tests_passed_count == executor_report.instance_count
    )
    ready = not model_failures and executor_report.ready_for_swebench_executor
    report = {
        "ready": ready,
        "model": args.model,
        "api_base_url_configured": bool(secrets.get("OPENAI_BASE_URL") or args.base_url),
        "model_call_count": len(instances),
        "model_json_parse_success_count": parse_success_count,
        "model_failures": model_failures,
        "executor_contract_ready": executor_report.ready_for_swebench_executor,
        "instance_count": executor_report.instance_count,
        "tests_passed_count": executor_report.tests_passed_count,
        "all_model_patches_tests_passed": all_tests_passed,
        "hydration_safe_count": executor_report.hydration_safe_count,
        "evidence_sound_count": executor_report.evidence_sound_count,
        "phase_gate_passed_count": executor_report.phase_gate_passed_count,
        "patch_equal_to_gold_count": executor_report.candidate_patch_equal_count,
        "mean_patch_line_jaccard": executor_report.mean_patch_line_jaccard,
        "mean_behavioral_divergence_score": executor_report.mean_behavioral_divergence_score,
        "executor_run_fingerprint": executor_report.run_fingerprint,
        "predictions": predictions,
        "executor_failures": executor_report.failures,
        "executor_warnings": executor_report.warnings,
        "instance_results": instance_results,
    }
    write_outputs(output_dir, report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "ready",
                    "model",
                    "model_call_count",
                    "model_json_parse_success_count",
                    "executor_contract_ready",
                    "instance_count",
                    "tests_passed_count",
                    "all_model_patches_tests_passed",
                    "hydration_safe_count",
                    "evidence_sound_count",
                    "patch_equal_to_gold_count",
                    "mean_patch_line_jaccard",
                    "mean_behavioral_divergence_score",
                    "model_failures",
                    "executor_failures",
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
