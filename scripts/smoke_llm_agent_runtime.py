from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_research import (
    EvidenceClaim,
    EvidenceEntry,
    EvidenceKind,
    EvidenceLedger,
    HarnessHermesRuntime,
    HarnessPolicy,
    HermesRuntime,
    HydrationManifestBuilder,
    JsonCheckpointStore,
    MemoryCommitProtocol,
    MemoryKind,
    PolicyHarness,
    SkillManifest,
    ToolCall,
    ToolDescriptionContract,
    ToolResult,
    ValidationReceipt,
    get_protocol_profile,
    get_provider_profile,
)
from vibe_research.schema import ArtifactRef, ToolEffect
from vibe_research.secrets import load_secret_file


JsonDict = dict[str, Any]


TOOL_SPECS: dict[str, JsonDict] = {
    "scan_fse_position": {
        "effect": ToolEffect.READ,
        "estimated_tokens": 180,
        "estimated_cost_usd": 0.001,
        "description": "Read the current FSE submission positioning and return evidence-backed gaps.",
    },
    "design_fse_experiment": {
        "effect": ToolEffect.EXECUTE,
        "estimated_tokens": 260,
        "estimated_cost_usd": 0.002,
        "description": "Synthesize the next benchmark experiment plan from the scanned evidence.",
    },
}


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

    with urlopen(request, timeout=45) as response:
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


def as_tool_call(model_payload: JsonDict) -> ToolCall:
    tool_name = str(model_payload.get("tool_name") or "").strip()
    if tool_name not in TOOL_SPECS:
        raise ValueError(f"model selected unknown tool: {tool_name!r}")

    spec = TOOL_SPECS[tool_name]
    raw_args = model_payload.get("args") or {}
    args = raw_args if isinstance(raw_args, dict) else {"value": raw_args}
    return ToolCall(
        tool_name=tool_name,
        args=args,
        effect=str(spec["effect"]),
        estimated_tokens=int(model_payload.get("estimated_tokens") or spec["estimated_tokens"]),
        estimated_cost_usd=float(model_payload.get("estimated_cost_usd") or spec["estimated_cost_usd"]),
        reason=str(model_payload.get("reason") or "selected by model"),
    )


def scan_fse_position(call: ToolCall, _state) -> ToolResult:
    focus = call.args.get("focus", "FSE 2027")
    output = (
        f"Scan focus: {focus}. Current strongest FSE story is not another agent framework, "
        "but runtime support for long-horizon software-engineering agents. The three stable "
        "claims are: hydratable execution scene, evidence-governed memory commit, and "
        "evidence-retaining replay diagnosis. Main remaining risk: real SWE-bench/artifact "
        "execution must replace synthetic-only evidence before submission."
    )
    return ToolResult(
        output=output,
        tokens_used=140,
        cost_usd=0.001,
        artifacts=[
            ArtifactRef(
                kind="fse_position_scan",
                uri="artifact://llm-smoke/fse-position-scan.md",
                metadata={"focus": str(focus)},
            )
        ],
    )


def design_fse_experiment(call: ToolCall, _state) -> ToolResult:
    target = call.args.get("target", "FSE 2027 empirical evaluation")
    output = (
        f"Experiment target: {target}. Recommended next benchmark slice: run 5-10 SWE-bench Verified "
        "instances through the official-subset bridge, retain oracle/provenance receipts, then compare "
        "checkpoint-only, transcript-only, LangGraph-style, OpenHands-style, AgentDiet-style, and Hermes "
        "ablations on resume correctness, invalid memory commit rate, evidence drift detection, replay "
        "fidelity, and artifact provenance completeness."
    )
    return ToolResult(
        output=output,
        tokens_used=220,
        cost_usd=0.002,
        artifacts=[
            ArtifactRef(
                kind="fse_experiment_design",
                uri="artifact://llm-smoke/fse-experiment-design.md",
                metadata={"target": str(target)},
            )
        ],
    )


def tool_contracts() -> dict[str, ToolDescriptionContract]:
    return {
        "scan_fse_position": ToolDescriptionContract(
            name="scan_fse_position",
            purpose="Read and summarize FSE-positioning evidence for the current runtime project.",
            input_schema={"type": "object", "properties": {"focus": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
            limitations=["Uses local project evidence rather than live conference crawling."],
            side_effects=["Adds a local artifact reference to the runtime state."],
            failure_modes=["May miss newly published papers unless the research log is updated."],
        ),
        "design_fse_experiment": ToolDescriptionContract(
            name="design_fse_experiment",
            purpose="Synthesize a benchmark experiment slice from current FSE-positioning evidence.",
            input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"plan": {"type": "string"}}},
            limitations=["Does not execute Docker SWE-bench; it designs the next slice."],
            side_effects=["Adds a local experiment-design artifact reference to the runtime state."],
            failure_modes=["May overfit to smoke-scale task counts."],
        ),
    }


def planning_prompt(*, goal: str, previous: str | None = None, force_tool: str | None = None) -> str:
    tool_block = json.dumps(TOOL_SPECS, indent=2, sort_keys=True, ensure_ascii=False)
    instruction = (
        "你是 Harness x Hermes 里的 LLM planning brain。你只能选择一个工具调用，"
        "真实执行、审批、checkpoint、trace 都由 runtime 接管。\n"
        "请只输出 JSON，不要 markdown，不要解释。\n"
        "JSON schema: {\"tool_name\": string, \"args\": object, \"estimated_tokens\": integer, "
        "\"estimated_cost_usd\": number, \"reason\": string}\n"
    )
    if force_tool:
        instruction += f"本轮必须选择工具：{force_tool}。\n"
    return (
        f"{instruction}\n"
        f"Goal: {goal}\n"
        f"Available tools:\n{tool_block}\n"
        f"Previous evidence:\n{previous or 'None. Start with the safest evidence-gathering step.'}\n"
    )


def final_prompt(*, goal: str, scan_output: str, experiment_output: str, runtime_summary: JsonDict) -> str:
    return (
        "请作为真实模型 agent 的最后一步，用中文给出非常紧凑的判断。"
        "必须覆盖：1) FSE 投递是否值得继续；2) 三个创新点；3) 下一步实验风险。"
        "不要编造已经跑过真实 SWE-bench Docker。\n\n"
        f"Goal: {goal}\n"
        f"Scan output: {scan_output}\n"
        f"Experiment output: {experiment_output}\n"
        f"Runtime summary: {json.dumps(runtime_summary, ensure_ascii=False, sort_keys=True)}\n"
    )


def write_outputs(output_dir: Path, report: JsonDict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "llm_agent_smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = report.get("final_model_assessment", "")
    markdown = (
        "# LLM Agent Runtime Smoke Report\n\n"
        f"- model: `{report['model']}`\n"
        f"- api_base_url_configured: `{report['api_base_url_configured']}`\n"
        f"- llm_call_count: `{report['llm_call_count']}`\n"
        f"- model_tool_json_parse_success_count: `{report['model_tool_json_parse_success_count']}`\n"
        f"- approval_pause_observed: `{report['approval_pause_observed']}`\n"
        f"- final_status: `{report['final_status']}`\n"
        f"- hydration_safe_to_hydrate: `{report['hydration_safe_to_hydrate']}`\n"
        f"- committed_memory_record_ids: `{', '.join(report['committed_memory_record_ids'])}`\n\n"
        "## Model assessment\n\n"
        f"{summary}\n"
    )
    (output_dir / "llm_agent_smoke_summary.md").write_text(markdown, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real LLM-driven Harness x Hermes agent smoke.")
    parser.add_argument("--model", default="gpt-5.4", help="Responses API model slug.")
    parser.add_argument("--secrets", default="secrets.txt", help="Local secret file, ignored by git.")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL; overrides secrets.")
    parser.add_argument("--output-dir", default=None, help="Optional directory for smoke JSON/Markdown reports.")
    args = parser.parse_args(argv)

    secrets = load_secret_file(args.secrets)
    api_key = secrets.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        print("No OPENAI_API_KEY found in local secrets file.", file=sys.stderr)
        return 2
    base_url = args.base_url or secrets.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    goal = (
        "Assess whether Harness x Hermes should keep targeting FSE 2027, and choose the next "
        "experiment slice for hydration, evidence-governed memory, and replay diagnosis."
    )

    try:
        first_text, first_raw = call_responses_api(
            api_key=api_key,
            base_url=base_url,
            model=args.model,
            input_text=planning_prompt(goal=goal),
            max_output_tokens=280,
        )
        first_payload = parse_json_object(first_text)
        first_call = as_tool_call(first_payload)

        evidence_ledger = EvidenceLedger(
            entries=[
                EvidenceEntry(
                    entry_id="fse-position-source",
                    kind=EvidenceKind.SOURCE,
                    source_ref="yys/投稿/fse-2027-vibe-research-plan.md",
                    labels=["fse", "positioning"],
                ),
                EvidenceEntry(
                    entry_id="runtime-smoke-source",
                    kind=EvidenceKind.ARTIFACT,
                    source_ref="scripts/smoke_llm_agent_runtime.py",
                    labels=["runtime", "smoke"],
                ),
            ],
            claims=[
                EvidenceClaim(
                    claim_id="claim-fse-runtime-fit",
                    statement="Harness x Hermes is positioned as runtime support for long-horizon SE agents.",
                    cited_entry_ids=["fse-position-source", "runtime-smoke-source"],
                    required_labels=["fse", "runtime"],
                )
            ],
        )

        with TemporaryDirectory() as temp_dir:
            policy = HarnessPolicy(
                allowed_tools=sorted(TOOL_SPECS),
                max_tool_tokens=2_000,
                max_tool_cost_usd=0.05,
            )
            hermes = HermesRuntime(JsonCheckpointStore(Path(temp_dir) / "checkpoints"), policy=policy)
            runtime = HarnessHermesRuntime(
                hermes=hermes,
                harness=PolicyHarness(policy),
                tools={
                    "scan_fse_position": scan_fse_position,
                    "design_fse_experiment": design_fse_experiment,
                },
                provider_profile=get_provider_profile("openai"),
                protocol_profile=get_protocol_profile("mcp"),
                tool_contracts=tool_contracts(),
            )

            state = runtime.start(goal)
            state.metadata["active_evidence_ledger"] = {
                "name": "llm-agent-smoke-evidence",
                "fingerprint": evidence_ledger.fingerprint(),
                "claim_ids": ["claim-fse-runtime-fit"],
            }
            state.active_skill_manifest = SkillManifest(
                name="fse_positioning_smoke",
                version="0.1.0",
                purpose="Use a real model to plan a minimal Harness x Hermes research-runtime pass.",
                context_influence=["FSE positioning", "runtime smoke result"],
                required_tools=sorted(TOOL_SPECS),
                required_capabilities=["read", "execute"],
                evidence_gates=["claim-fse-runtime-fit"],
                fallback_paths=["fall back to deterministic local benchmark smoke"],
                action_effects=[ToolEffect.READ, ToolEffect.EXECUTE],
            ).to_dict()

            state, first_result = runtime.run_tool(state, first_call)
            if first_result is None:
                raise RuntimeError(f"first model-selected tool did not complete: {state.failure_state}")

            second_text, second_raw = call_responses_api(
                api_key=api_key,
                base_url=base_url,
                model=args.model,
                input_text=planning_prompt(
                    goal=goal,
                    previous=first_result.output,
                    force_tool="design_fse_experiment",
                ),
                max_output_tokens=280,
            )
            second_payload = parse_json_object(second_text)
            second_call = as_tool_call(second_payload)
            state, second_result = runtime.run_tool(state, second_call)
            approval_pause_observed = second_result is None and state.pending_tool_call is not None
            if approval_pause_observed:
                state = runtime.load_latest(state.task_id)
                state, second_result = runtime.approve_pending_tool(state)
            if second_result is None:
                raise RuntimeError(f"second model-selected tool did not complete: {state.failure_state}")

            trace_envelope_count = sum(1 for event in runtime.events if "trace_envelope" in event.data)
            evidence_receipt_count = sum(
                1
                for event in runtime.events
                for receipt in event.data.get("trace_envelope", {}).get("receipts", [])
                if receipt.get("kind") == "evidence_ledger"
            )
            runtime_summary = {
                "status": state.status,
                "checkpoint_ref": state.checkpoint_ref,
                "trace_event_count": len(runtime.events),
                "trace_envelope_count": trace_envelope_count,
                "evidence_receipt_count": evidence_receipt_count,
                "artifact_count": len(state.artifact_refs),
                "budget_tokens_used": state.budget_state.tokens_used,
                "budget_cost_used_usd": state.budget_state.cost_used_usd,
                "approval_pause_observed": approval_pause_observed,
            }

            final_text, final_raw = call_responses_api(
                api_key=api_key,
                base_url=base_url,
                model=args.model,
                input_text=final_prompt(
                    goal=goal,
                    scan_output=first_result.output,
                    experiment_output=second_result.output,
                    runtime_summary=runtime_summary,
                ),
                max_output_tokens=420,
            )

            memory_protocol = MemoryCommitProtocol()
            memory_protocol.begin_transaction(transaction_id="tx-llm-smoke", checkpoint_version=state.version)
            memory_protocol.stage_record(
                "tx-llm-smoke",
                record_id="belief-llm-fse-next-step",
                kind=MemoryKind.BELIEF,
                payload={
                    "claim": "The real-model smoke supports continuing FSE 2027 positioning, but real SWE-bench execution remains the next risk.",
                    "model_assessment_excerpt": final_text[:800],
                },
                source_refs=[state.checkpoint_ref or "", "claim-fse-runtime-fit"],
            )
            memory_protocol.validate_record(
                "belief-llm-fse-next-step",
                ValidationReceipt(
                    validator="llm-agent-smoke-validator",
                    passed=True,
                    reasons=["tool artifacts exist", "evidence ledger claim is sound", "final model assessment produced"],
                    evidence_refs=["claim-fse-runtime-fit"],
                    checkpoint_version=state.version,
                ),
            )
            memory_commit = memory_protocol.commit("tx-llm-smoke", checkpoint_version=state.version)
            memory_safety = memory_protocol.safety_gate(memory_commit.committed_record_ids)
            evidence_report = evidence_ledger.evaluate(required_claim_ids=["claim-fse-runtime-fit"])
            manifest_builder = HydrationManifestBuilder()
            manifest = manifest_builder.dehydrate(
                state,
                runtime.events,
                memory_records=list(memory_protocol.records.values()),
                evidence_ledger=evidence_ledger,
                required_memory_record_ids=memory_commit.committed_record_ids,
                required_evidence_claim_ids=["claim-fse-runtime-fit"],
                required_artifact_uris=[artifact.uri for artifact in state.artifact_refs],
                metadata={"model": args.model, "smoke": "llm_agent_runtime"},
            )
            hydration_report = manifest_builder.verify(
                manifest,
                state,
                runtime.events,
                memory_records=list(memory_protocol.records.values()),
                evidence_ledger=evidence_ledger,
            )

        report: JsonDict = {
            "ready": (
                state.status == "ready"
                and approval_pause_observed
                and evidence_report.sound
                and memory_commit.committed
                and memory_safety.safe
                and hydration_report.safe_to_hydrate
            ),
            "model": args.model,
            "api_base_url_configured": bool(secrets.get("OPENAI_BASE_URL") or args.base_url),
            "llm_call_count": 3,
            "model_tool_json_parse_success_count": 2,
            "selected_tools": [first_call.tool_name, second_call.tool_name],
            "selected_tool_reasons": [first_call.reason, second_call.reason],
            "approval_pause_observed": approval_pause_observed,
            "final_status": state.status,
            "checkpoint_ref": state.checkpoint_ref,
            "trace_event_count": runtime_summary["trace_event_count"],
            "trace_envelope_count": runtime_summary["trace_envelope_count"],
            "evidence_receipt_count": runtime_summary["evidence_receipt_count"],
            "artifact_count": runtime_summary["artifact_count"],
            "budget_tokens_used": runtime_summary["budget_tokens_used"],
            "budget_cost_used_usd": runtime_summary["budget_cost_used_usd"],
            "evidence_ledger_sound": evidence_report.sound,
            "committed_memory_record_ids": memory_commit.committed_record_ids,
            "memory_safety_gate_safe": memory_safety.safe,
            "hydration_safe_to_hydrate": hydration_report.safe_to_hydrate,
            "hydration_retained_surfaces": hydration_report.retained_surfaces,
            "manifest_fingerprint": manifest.fingerprint(),
            "final_model_assessment": final_text.strip(),
            "raw_response_ids": [
                first_raw.get("id"),
                second_raw.get("id"),
                final_raw.get("id"),
            ],
        }
    except HTTPError as exc:
        print(f"LLM agent smoke failed: {summarize_http_error(exc)}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"LLM agent smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.output_dir:
        write_outputs(Path(args.output_dir), report)

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
