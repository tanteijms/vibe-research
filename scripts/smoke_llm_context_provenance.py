from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    CompactionVerifier,
    ContextControlPlane,
    EvidenceClaim,
    EvidenceEntry,
    EvidenceKind,
    EvidenceLedger,
    HydrationManifestBuilder,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    ProcessStage,
    ProvenanceGraphCompiler,
    RuntimeState,
    make_evidence_receipt,
)
from vibe_research.schema import ArtifactRef, TraceEvent
from vibe_research.secrets import load_secret_file
from vibe_research.trace_contract import TraceBoundary, TraceEnvelope, hash_payload, make_action_receipt


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
    return (
        f"HTTP {exc.code}: type={error.get('type', 'unknown_error')}, "
        f"code={error.get('code', 'unknown_code')}, param={error.get('param')}"
    )


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
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
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


def build_state() -> RuntimeState:
    return RuntimeState(
        task_id="task-context-provenance",
        session_id="sess-context-provenance",
        run_id="run-context-provenance",
        goal=(
            "Prepare a hydratable, evidence-governed, provenance-retaining runtime slice "
            "for Harness x Hermes before a longer FSE-oriented run."
        ),
        execution_cursor="after:analysis",
        active_step="analysis",
        process_stage=ProcessStage.ACTIVE,
        policy_snapshot={
            "allowed_tools": ["paper_scan", "benchmark_design", "analysis"],
            "require_review": True,
            "require_validation_receipt": True,
        },
        artifact_refs=[
            ArtifactRef(kind="paper_shortlist", uri="artifact://papers.json"),
            ArtifactRef(kind="benchmark_matrix", uri="artifact://benchmark-matrix.json"),
            ArtifactRef(kind="analysis_report", uri="artifact://analysis.md"),
        ],
        metadata={
            "memory_record_ids": ["mem-fse-positioning", "mem-hydration-gap"],
            "standing_risks": [
                "official SWE-bench Docker evidence is still missing",
                "artifact replication is smoke-level rather than submission-grade",
            ],
        },
    )


def build_memory_records() -> list[MemoryRecord]:
    return [
        MemoryRecord(
            record_id="mem-fse-positioning",
            kind=MemoryKind.BELIEF,
            payload={"claim": "Harness x Hermes should be framed as runtime support."},
            status=MemoryStatus.COMMITTED,
            source_refs=["artifact://analysis.md"],
        ),
        MemoryRecord(
            record_id="mem-hydration-gap",
            kind=MemoryKind.OBSERVATION,
            payload={"gap": "Need more official SWE-bench execution evidence."},
            status=MemoryStatus.COMMITTED,
            source_refs=["artifact://benchmark-matrix.json"],
        ),
    ]


def build_evidence_ledger() -> EvidenceLedger:
    return EvidenceLedger(
        entries=[
            EvidenceEntry(
                entry_id="ctx-doc",
                kind=EvidenceKind.SOURCE,
                source_ref="doc/项目上下文-2026-08-06.md",
                labels=["context", "design"],
            ),
            EvidenceEntry(
                entry_id="progress-report",
                kind=EvidenceKind.ARTIFACT,
                source_ref="artifact://analysis.md",
                labels=["analysis", "progress"],
                produced_by_transition_id="e3",
            ),
            EvidenceEntry(
                entry_id="benchmark-report",
                kind=EvidenceKind.ARTIFACT,
                source_ref="artifact://benchmark-matrix.json",
                labels=["benchmark", "artifact"],
                produced_by_transition_id="e2",
            ),
        ],
        claims=[
            EvidenceClaim(
                claim_id="claim-context-retained",
                statement="The runtime keeps explicit context pins and can rehydrate safely.",
                cited_entry_ids=["ctx-doc", "progress-report"],
                required_labels=["context", "progress"],
            ),
            EvidenceClaim(
                claim_id="claim-benchmark-gap-tracked",
                statement="The current benchmark gap is evidence-backed rather than implied.",
                cited_entry_ids=["benchmark-report"],
                required_labels=["benchmark"],
            ),
        ],
    )


def build_events(state: RuntimeState, evidence_ledger: EvidenceLedger) -> list[TraceEvent]:
    first_envelope = TraceEnvelope(
        boundary=TraceBoundary.TOOL,
        task_id=state.task_id,
        run_id=state.run_id,
        cursor="after:paper_scan",
        provider_name="openai-compatible",
        provider_fingerprint="provider-openai-compatible",
        policy_fingerprint=hash_payload(state.policy_snapshot),
        action_name="paper_scan",
        action_effect="read",
        input_hash=hash_payload({"focus": "FSE-ready runtime positioning"}),
        output_hash=hash_payload({"artifact": "artifact://papers.json"}),
        artifact_refs=["artifact://papers.json"],
        receipts=[
            make_action_receipt(
                action_name="paper_scan",
                input_payload={"focus": "FSE-ready runtime positioning"},
                output_payload={"artifact": "artifact://papers.json"},
            ),
            make_evidence_receipt(
                ledger_name="smoke-context-evidence",
                fingerprint=evidence_ledger.fingerprint(),
                claim_ids=["claim-context-retained"],
            ),
        ],
    )
    second_envelope = TraceEnvelope(
        boundary=TraceBoundary.TOOL,
        task_id=state.task_id,
        run_id=state.run_id,
        cursor="after:benchmark_design",
        provider_name="openai-compatible",
        provider_fingerprint="provider-openai-compatible",
        policy_fingerprint=hash_payload(state.policy_snapshot),
        action_name="benchmark_design",
        action_effect="read",
        input_hash=hash_payload({"artifact": "artifact://papers.json"}),
        output_hash=hash_payload({"artifact": "artifact://benchmark-matrix.json"}),
        artifact_refs=["artifact://benchmark-matrix.json"],
        receipts=[
            make_action_receipt(
                action_name="benchmark_design",
                input_payload={"artifact": "artifact://papers.json"},
                output_payload={"artifact": "artifact://benchmark-matrix.json"},
            ),
            make_evidence_receipt(
                ledger_name="smoke-context-evidence",
                fingerprint=evidence_ledger.fingerprint(),
                claim_ids=["claim-benchmark-gap-tracked"],
            ),
        ],
    )
    third_envelope = TraceEnvelope(
        boundary=TraceBoundary.TOOL,
        task_id=state.task_id,
        run_id=state.run_id,
        cursor="after:analysis",
        provider_name="openai-compatible",
        provider_fingerprint="provider-openai-compatible",
        policy_fingerprint=hash_payload(state.policy_snapshot),
        action_name="analysis",
        action_effect="read",
        input_hash=hash_payload({"artifact": "artifact://benchmark-matrix.json"}),
        output_hash=hash_payload({"artifact": "artifact://analysis.md"}),
        artifact_refs=["artifact://analysis.md"],
        receipts=[
            make_action_receipt(
                action_name="analysis",
                input_payload={"artifact": "artifact://benchmark-matrix.json"},
                output_payload={"artifact": "artifact://analysis.md"},
            ),
            make_evidence_receipt(
                ledger_name="smoke-context-evidence",
                fingerprint=evidence_ledger.fingerprint(),
                claim_ids=["claim-context-retained", "claim-benchmark-gap-tracked"],
            ),
        ],
    )
    return [
        TraceEvent(
            event_id="e1",
            task_id=state.task_id,
            run_id=state.run_id,
            cursor="after:paper_scan",
            kind="tool_completed",
            data={
                "tool": "paper_scan",
                "artifact_refs": ["artifact://papers.json"],
                "trace_envelope": first_envelope.to_dict(),
                "trace_envelope_fingerprint": first_envelope.fingerprint(),
            },
        ),
        TraceEvent(
            event_id="e2",
            task_id=state.task_id,
            run_id=state.run_id,
            cursor="after:benchmark_design",
            kind="tool_completed",
            data={
                "tool": "benchmark_design",
                "artifact_refs": ["artifact://benchmark-matrix.json"],
                "parent_transition_ids": ["e1"],
                "trace_envelope": second_envelope.to_dict(),
                "trace_envelope_fingerprint": second_envelope.fingerprint(),
            },
        ),
        TraceEvent(
            event_id="e3",
            task_id=state.task_id,
            run_id=state.run_id,
            cursor="after:analysis",
            kind="tool_completed",
            data={
                "tool": "analysis",
                "artifact_refs": ["artifact://analysis.md"],
                "parent_transition_ids": ["e2"],
                "trace_envelope": third_envelope.to_dict(),
                "trace_envelope_fingerprint": third_envelope.fingerprint(),
            },
        ),
    ]


def planning_prompt(state: RuntimeState, memory_records: list[MemoryRecord], evidence_ledger: EvidenceLedger) -> str:
    state_summary = {
        "goal": state.goal,
        "artifacts": [ref.uri for ref in state.artifact_refs],
        "policy_snapshot": state.policy_snapshot,
        "memory_record_ids": [record.record_id for record in memory_records],
        "evidence_claim_ids": sorted(evidence_ledger.claims),
        "standing_risks": list(state.metadata.get("standing_risks", [])),
    }
    schema = {
        "retains": [
            {
                "pin_id": "policy-snapshot",
                "surface": "harness_policy",
                "source_path": "policy_snapshot",
                "description": "Keep the exact policy snapshot alive.",
            }
        ],
        "pins": [
            {
                "pin_id": "artifact-lineage",
                "surface": "artifact_lineage",
                "value": "artifact://analysis.md",
                "description": "Keep the latest analysis artifact live.",
                "required": True,
            }
        ],
        "branch_reason": "Short reason",
        "compacted_summary": "1-2 sentence compacted summary",
        "rehydrated_summary": "1-2 sentence restored summary",
        "analysis": "Why these actions preserve the scene",
    }
    return (
        "You are planning explicit context actions for a long-horizon agent runtime.\n"
        "Return JSON only, no markdown.\n"
        "Prefer 1-2 retains and 1-3 pins. Keep values short and concrete.\n"
        "Required schema example:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Current runtime slice:\n{json.dumps(state_summary, ensure_ascii=False, indent=2)}\n"
    )


def diagnosis_prompt(
    *,
    dashboard: JsonDict,
    compaction_safe: bool,
    hydration_safe: bool,
    provenance_summary: JsonDict,
) -> str:
    return (
        "You are reviewing a context-control and provenance smoke report.\n"
        "Return JSON only, no markdown.\n"
        "Schema: {\"diagnosis\": string, \"next_checks\": [string], \"confidence\": string}\n\n"
        f"Context dashboard:\n{json.dumps(dashboard, ensure_ascii=False, indent=2)}\n\n"
        f"Compaction safe to resume: {json.dumps(compaction_safe)}\n"
        f"Hydration safe to hydrate: {json.dumps(hydration_safe)}\n"
        f"Provenance summary:\n{json.dumps(provenance_summary, ensure_ascii=False, indent=2)}\n"
    )


def apply_model_plan(state: RuntimeState, plan: JsonDict) -> tuple[list[JsonDict], JsonDict]:
    plane = ContextControlPlane(state)
    receipts: list[JsonDict] = []

    for item in plan.get("retains", [])[:2]:
        if not isinstance(item, dict):
            continue
        pin_id = str(item.get("pin_id") or "retain-pin")
        source_path = str(item.get("source_path")) if item.get("source_path") else None
        value = item.get("value")
        try:
            receipt = plane.retain(
                pin_id=pin_id,
                surface=str(item.get("surface") or "context"),
                value=value,
                source_path=source_path,
                description=str(item.get("description") or ""),
                reason="model-selected retain action",
            )
            receipts.append(receipt.to_dict())
        except ValueError:
            if value is None:
                continue
            receipt = plane.pin(
                pin_id=pin_id,
                surface=str(item.get("surface") or "context"),
                value=value,
                required=bool(item.get("required", True)),
                description=str(item.get("description") or ""),
                reason="fallback from invalid retain to explicit pin",
            )
            receipts.append(receipt.to_dict())

    for item in plan.get("pins", [])[:3]:
        if not isinstance(item, dict):
            continue
        receipt = plane.pin(
            pin_id=str(item.get("pin_id") or "pin"),
            surface=str(item.get("surface") or "context"),
            value=item.get("value"),
            required=bool(item.get("required", True)),
            description=str(item.get("description") or ""),
            reason="model-selected pin action",
        )
        receipts.append(receipt.to_dict())

    branch_receipt = plane.branch(reason=str(plan.get("branch_reason") or "branch the governed scene"))
    receipts.append(branch_receipt.to_dict())

    compact_receipt = plane.compress(
        str(plan.get("compacted_summary") or "Compacted context while keeping the critical pins."),
        retained_pin_ids=plane.dashboard().pinned_pin_ids,
        reason="model-selected compaction step",
    )
    receipts.append(compact_receipt.to_dict())

    rehydrate_receipt = plane.rehydrate(
        source_ref="checkpoint://context-provenance-smoke/compact",
        branch_id=branch_receipt.branch_id,
        restored_pin_ids=plane.dashboard().pinned_pin_ids,
        summary=str(plan.get("rehydrated_summary") or "Restored the context from compact form."),
        reason="model-selected rehydration step",
    )
    receipts.append(rehydrate_receipt.to_dict())
    return receipts, plane.dashboard().to_dict()


def write_outputs(output_dir: Path, report: JsonDict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "llm_context_provenance_smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_lines = [
        "# LLM Context/Provenance Smoke Report",
        "",
        f"- model: `{report['model']}`",
        f"- llm_call_count: `{report['llm_call_count']}`",
        f"- model_json_parse_success_count: `{report['model_json_parse_success_count']}`",
        f"- context_action_count: `{report['context_action_count']}`",
        f"- active_pin_count: `{report['active_pin_count']}`",
        f"- compaction_safe_to_resume: `{report['compaction_safe_to_resume']}`",
        f"- hydration_safe_to_hydrate: `{report['hydration_safe_to_hydrate']}`",
        f"- provenance_replay_ready: `{report['provenance_replay_ready']}`",
        "",
        "## Diagnosis",
        "",
        report["diagnosis_payload"]["diagnosis"],
        "",
        "## Next Checks",
        "",
    ]
    summary_lines.extend(
        f"- {item}" for item in report["diagnosis_payload"].get("next_checks", [])
    )
    summary_lines.append("")
    (output_dir / "llm_context_provenance_smoke_summary.md").write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )


def write_failure_output(
    output_dir: Path,
    *,
    model: str,
    base_url_configured: bool,
    stage: str,
    error_summary: str,
) -> None:
    report = {
        "model": model,
        "api_base_url_configured": base_url_configured,
        "failure_stage": stage,
        "error_summary": error_summary,
        "ready": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "llm_context_provenance_smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "llm_context_provenance_smoke_summary.md").write_text(
        "\n".join(
            [
                "# LLM Context/Provenance Smoke Report",
                "",
                f"- model: `{model}`",
                f"- ready: `False`",
                f"- failure_stage: `{stage}`",
                f"- error_summary: `{error_summary}`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real-LLM context/provenance smoke for Harness x Hermes.")
    parser.add_argument("--model", default="gpt-5.4", help="Responses API model slug.")
    parser.add_argument("--secrets", default="secrets.txt", help="Local secret file, ignored by git.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL; overrides secrets.")
    parser.add_argument(
        "--output-dir",
        default="yys/all/0802/llm_context_provenance_smoke",
        help="Directory for report artifacts.",
    )
    args = parser.parse_args(argv)

    secrets = load_secret_file(args.secrets)
    api_key = os.environ.get("OPENAI_API_KEY") or secrets.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("No OPENAI_API_KEY found in local secrets file.", file=sys.stderr)
        return 2
    base_url = os.environ.get("OPENAI_BASE_URL") or args.base_url or secrets.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    state = build_state()
    memory_records = build_memory_records()
    evidence_ledger = build_evidence_ledger()
    events = build_events(state, evidence_ledger)

    output_dir = Path(args.output_dir).resolve()

    try:
        plan_text, plan_raw = call_responses_api(
            api_key=api_key,
            base_url=base_url,
            model=args.model,
            input_text=planning_prompt(state, memory_records, evidence_ledger),
            max_output_tokens=700,
        )
        plan_payload = parse_json_object(plan_text)
    except HTTPError as exc:
        error_summary = summarize_http_error(exc)
        write_failure_output(
            output_dir,
            model=args.model,
            base_url_configured=bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
            stage="planning_call",
            error_summary=error_summary,
        )
        print(f"context/provenance planning call failed: {error_summary}", file=sys.stderr)
        return 1
    except URLError as exc:
        error_summary = str(exc)
        write_failure_output(
            output_dir,
            model=args.model,
            base_url_configured=bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
            stage="planning_call",
            error_summary=error_summary,
        )
        print(f"context/provenance planning call failed: {error_summary}", file=sys.stderr)
        return 1

    try:
        receipts, dashboard = apply_model_plan(state, plan_payload)
        compaction_report = CompactionVerifier().verify(state, RuntimeState.from_dict(state.to_dict()))
        hydration_builder = HydrationManifestBuilder()
        hydration_manifest = hydration_builder.dehydrate(
            state,
            events,
            memory_records=memory_records,
            evidence_ledger=evidence_ledger,
            required_artifact_uris=["artifact://analysis.md"],
            required_evidence_claim_ids=["claim-context-retained"],
        )
        hydration_report = hydration_builder.verify(
            hydration_manifest,
            state,
            events,
            memory_records=memory_records,
            evidence_ledger=evidence_ledger,
        )
        provenance_report = ProvenanceGraphCompiler().compile(
            events,
            state=state,
            memory_records=memory_records,
            evidence_ledger=evidence_ledger,
        )

        diagnosis_input = {
            "branch_id": dashboard["branch_id"],
            "pinned_pin_ids": dashboard["pinned_pin_ids"],
            "retention_budget_bytes": dashboard["retention_budget_bytes"],
            "hydration_safe_to_hydrate": hydration_report.safe_to_hydrate,
            "provenance_replay_ready": provenance_report.replay_summary["replay_ready"],
            "provenance_claim_count": provenance_report.replay_summary["evidence_claim_count"],
            "warnings": provenance_report.warnings,
        }
    except Exception as exc:
        error_summary = f"{exc.__class__.__name__}: {exc}"
        write_failure_output(
            output_dir,
            model=args.model,
            base_url_configured=bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
            stage="local_context_execution",
            error_summary=error_summary,
        )
        print(f"context/provenance local execution failed: {error_summary}", file=sys.stderr)
        return 1

    try:
        diagnosis_text, diagnosis_raw = call_responses_api(
            api_key=api_key,
            base_url=base_url,
            model=args.model,
            input_text=diagnosis_prompt(
                dashboard=dashboard,
                compaction_safe=compaction_report.safe_to_resume,
                hydration_safe=hydration_report.safe_to_hydrate,
                provenance_summary=diagnosis_input,
            ),
            max_output_tokens=320,
        )
        diagnosis_payload = parse_json_object(diagnosis_text)
    except HTTPError as exc:
        error_summary = summarize_http_error(exc)
        write_failure_output(
            output_dir,
            model=args.model,
            base_url_configured=bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
            stage="diagnosis_call",
            error_summary=error_summary,
        )
        print(f"context/provenance diagnosis call failed: {error_summary}", file=sys.stderr)
        return 1
    except URLError as exc:
        error_summary = str(exc)
        write_failure_output(
            output_dir,
            model=args.model,
            base_url_configured=bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
            stage="diagnosis_call",
            error_summary=error_summary,
        )
        print(f"context/provenance diagnosis call failed: {error_summary}", file=sys.stderr)
        return 1

    report = {
        "model": args.model,
        "api_base_url_configured": bool(os.environ.get("OPENAI_BASE_URL") or secrets.get("OPENAI_BASE_URL") or args.base_url),
        "llm_call_count": 2,
        "model_json_parse_success_count": 2,
        "planning_response_id": str(plan_raw.get("id") or ""),
        "diagnosis_response_id": str(diagnosis_raw.get("id") or ""),
        "context_action_count": len(receipts),
        "active_pin_count": len(dashboard["pinned_pin_ids"]),
        "branch_id": dashboard["branch_id"],
        "context_dashboard": dashboard,
        "model_plan": plan_payload,
        "context_receipts": receipts,
        "compaction_safe_to_resume": compaction_report.safe_to_resume,
        "compaction_report": compaction_report.to_dict(),
        "hydration_safe_to_hydrate": hydration_report.safe_to_hydrate,
        "hydration_manifest_fingerprint": hydration_manifest.fingerprint(),
        "hydration_report": hydration_report.to_dict(),
        "provenance_replay_ready": provenance_report.replay_summary["replay_ready"],
        "provenance_report": provenance_report.to_dict(),
        "diagnosis_payload": diagnosis_payload,
    }
    write_outputs(Path(args.output_dir).resolve(), report)
    print(
        json.dumps(
            {
                "model": args.model,
                "context_action_count": len(receipts),
                "hydration_safe_to_hydrate": hydration_report.safe_to_hydrate,
                "provenance_replay_ready": provenance_report.replay_summary["replay_ready"],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
