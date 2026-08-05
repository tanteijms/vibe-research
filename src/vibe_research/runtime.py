from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Callable
from uuid import uuid4

from .harness import PolicyHarness
from .hermes import HermesRuntime
from .process_lifecycle import ProcessStage
from .provider_profiles import ProviderProfile
from .protocol_profiles import ProtocolProfile
from .skill_manifest import SkillManifest
from .schema import ArtifactRef, RunStatus, RuntimeState, ToolCall, TraceEvent
from .tool_contracts import ToolDescriptionContract
from .trace_contract import (
    ReceiptKind,
    TraceBoundary,
    TraceEnvelope,
    hash_payload,
    make_action_receipt,
    make_capability_receipt,
    make_evidence_receipt,
    make_skill_receipt,
)


@dataclass(slots=True)
class ToolResult:
    output: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


ToolFn = Callable[[ToolCall, RuntimeState], ToolResult]


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


class HarnessHermesRuntime:
    """Coordinates Hermes state continuity with Harness governance."""

    def __init__(
        self,
        *,
        hermes: HermesRuntime,
        harness: PolicyHarness,
        tools: dict[str, ToolFn],
        provider_profile: ProviderProfile | None = None,
        protocol_profile: ProtocolProfile | None = None,
        tool_contracts: dict[str, ToolDescriptionContract] | None = None,
    ):
        self.hermes = hermes
        self.harness = harness
        self.tools = dict(tools)
        self.provider_profile = provider_profile
        self.protocol_profile = protocol_profile
        self.tool_contracts = dict(tool_contracts or {})
        self.events: list[TraceEvent] = []

    def start(self, goal: str) -> RuntimeState:
        return self.hermes.start_task(goal)

    def load_latest(self, task_id: str) -> RuntimeState:
        bundle = self.hermes.resume_latest(task_id)
        self.events = bundle.events
        return bundle.state

    def run_tool(self, state: RuntimeState, call: ToolCall, *, approved: bool = False) -> tuple[RuntimeState, ToolResult | None]:
        decision = self.harness.authorize_tool(state, call, approved=approved)

        if decision.pause_for_approval:
            state.status = RunStatus.AWAITING_APPROVAL
            state.process_stage = ProcessStage.WAITING
            state.pending_tool_call = call.to_dict()
            state.approval_token = f"approval_{uuid4().hex[:12]}"
            self._record(state, "tool_paused", {"tool": call.tool_name, "reason": decision.reason}, call=call)
            self.hermes.checkpoint(state, self.events, reason="approval_required")
            return state, None

        if not decision.allowed:
            state.status = RunStatus.BLOCKED
            state.process_stage = ProcessStage.SUSPENDED
            state.failure_state = {"reason": decision.reason, "tool": call.tool_name}
            self._record(state, "tool_blocked", state.failure_state, call=call)
            self.hermes.checkpoint(state, self.events, reason="harness_blocked")
            return state, None

        if call.tool_name not in self.tools:
            state.status = RunStatus.FAILED
            state.process_stage = ProcessStage.SUSPENDED
            state.failure_state = {"reason": "unknown tool", "tool": call.tool_name}
            self._record(state, "tool_failed", state.failure_state, call=call)
            self.hermes.checkpoint(state, self.events, reason="unknown_tool")
            return state, None

        state.status = RunStatus.RUNNING
        state.process_stage = ProcessStage.ACTIVE
        self._record(
            state,
            "tool_started",
            {
                "tool": call.tool_name,
                "effect": call.effect,
                "args_hash": stable_hash(call.args),
            },
            call=call,
        )
        result = self.tools[call.tool_name](call, state)
        if isinstance(result.output, str):
            result.output = self.harness.sanitize_output(result.output)

        self.harness.spend_budget(state, tokens=result.tokens_used, cost_usd=result.cost_usd)
        state.artifact_refs.extend(result.artifacts)
        state.pending_tool_call = None
        state.approval_token = None
        state.status = RunStatus.READY
        state.process_stage = ProcessStage.ACTIVE
        state.active_step = call.tool_name
        state.execution_cursor = f"after:{call.tool_name}:{state.version + 1}"

        self._record(
            state,
            "tool_completed",
            {
                "tool": call.tool_name,
                "args_hash": stable_hash(call.args),
                "output_hash": stable_hash(result.output),
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
            },
            call=call,
            output_payload=result.output,
            artifact_refs=[artifact.uri for artifact in result.artifacts],
        )
        self.hermes.checkpoint(state, self.events, reason="tool_completed")
        return state, result

    def approve_pending_tool(self, state: RuntimeState) -> tuple[RuntimeState, ToolResult | None]:
        if not state.pending_tool_call:
            state.failure_state = {"reason": "no pending tool call"}
            return state, None
        call = ToolCall.from_dict(state.pending_tool_call)
        state.pending_tool_call = None
        state.status = RunStatus.READY
        return self.run_tool(state, call, approved=True)

    def _record(
        self,
        state: RuntimeState,
        kind: str,
        data: dict[str, object],
        *,
        call: ToolCall | None = None,
        output_payload: object | None = None,
        artifact_refs: list[str] | None = None,
    ) -> None:
        event_data = dict(data)
        if call is not None and self.provider_profile is not None:
            envelope = self._build_trace_envelope(
                state,
                call,
                output_payload=output_payload,
                artifact_refs=artifact_refs or [],
            )
            event_data["trace_envelope"] = envelope.to_dict()
            event_data["trace_envelope_fingerprint"] = envelope.fingerprint()

        self.events.append(
            TraceEvent(
                event_id=f"event_{uuid4().hex[:12]}",
                task_id=state.task_id,
                run_id=state.run_id,
                cursor=state.execution_cursor,
                kind=kind,
                data=event_data,
            )
        )

    def _build_trace_envelope(
        self,
        state: RuntimeState,
        call: ToolCall,
        *,
        output_payload: object | None,
        artifact_refs: list[str],
    ) -> TraceEnvelope:
        if self.provider_profile is None:
            raise ValueError("provider_profile is required for trace envelopes")

        provider_fingerprint = self.provider_profile.fingerprint()
        protocol_fingerprint = self.protocol_profile.fingerprint() if self.protocol_profile else None
        tool_contract = self.tool_contracts.get(call.tool_name)
        tool_contract_fingerprint = tool_contract.fingerprint() if tool_contract else None
        skill_manifest = self._skill_manifest_snapshot(state)
        skill_manifest_fingerprint = skill_manifest.fingerprint() if skill_manifest else None
        evidence_snapshot = self._evidence_ledger_snapshot(state)
        evidence_ledger_name = evidence_snapshot["name"] if evidence_snapshot else None
        evidence_ledger_fingerprint = evidence_snapshot["fingerprint"] if evidence_snapshot else None
        evidence_claim_ids = evidence_snapshot["claim_ids"] if evidence_snapshot else []
        receipts = [
            make_action_receipt(
                action_name=call.tool_name,
                input_payload=call.args,
                output_payload=output_payload,
            ),
            make_capability_receipt(
                kind=ReceiptKind.PROVIDER_CAPABILITY,
                name=self.provider_profile.name,
                fingerprint=provider_fingerprint,
            ),
        ]
        if self.protocol_profile is not None and protocol_fingerprint is not None:
            receipts.append(
                make_capability_receipt(
                    kind=ReceiptKind.PROTOCOL_CAPABILITY,
                    name=self.protocol_profile.name,
                    fingerprint=protocol_fingerprint,
                )
            )
        if tool_contract_fingerprint is not None:
            receipts.append(
                make_capability_receipt(
                    kind=ReceiptKind.TOOL_CONTRACT,
                    name=call.tool_name,
                    fingerprint=tool_contract_fingerprint,
                )
            )
        if skill_manifest is not None:
            receipts.append(
                make_skill_receipt(
                    skill_name=skill_manifest.name,
                    fingerprint=skill_manifest_fingerprint or skill_manifest.fingerprint(),
                )
            )
        if evidence_ledger_name is not None and evidence_ledger_fingerprint is not None:
            receipts.append(
                make_evidence_receipt(
                    ledger_name=evidence_ledger_name,
                    fingerprint=evidence_ledger_fingerprint,
                    claim_ids=evidence_claim_ids,
                )
            )

        return TraceEnvelope(
            boundary=TraceBoundary.TOOL,
            task_id=state.task_id,
            run_id=state.run_id,
            cursor=state.execution_cursor,
            provider_name=self.provider_profile.name,
            provider_fingerprint=provider_fingerprint,
            protocol_name=self.protocol_profile.name if self.protocol_profile else None,
            protocol_fingerprint=protocol_fingerprint,
            policy_fingerprint=hash_payload(self.harness.policy.to_dict()),
            tool_contract_fingerprint=tool_contract_fingerprint,
            skill_name=skill_manifest.name if skill_manifest else None,
            skill_manifest_fingerprint=skill_manifest_fingerprint,
            evidence_ledger_fingerprint=evidence_ledger_fingerprint,
            evidence_claim_ids=evidence_claim_ids,
            action_name=call.tool_name,
            action_effect=call.effect,
            input_hash=hash_payload(call.args),
            output_hash=hash_payload(output_payload) if output_payload is not None else None,
            artifact_refs=list(artifact_refs),
            receipts=receipts,
            metadata={
                "estimated_tokens": call.estimated_tokens,
                "estimated_cost_usd": call.estimated_cost_usd,
                "timeout_s": call.timeout_s,
            },
        )

    def _skill_manifest_snapshot(self, state: RuntimeState) -> SkillManifest | None:
        raw = state.active_skill_manifest or state.metadata.get("active_skill_manifest")
        if not raw:
            return None
        if isinstance(raw, SkillManifest):
            return raw
        if isinstance(raw, dict):
            return SkillManifest(**raw)
        raise TypeError("active_skill_manifest must be a SkillManifest or dict snapshot")

    def _evidence_ledger_snapshot(self, state: RuntimeState) -> dict[str, object] | None:
        """Returns a stable evidence-ledger snapshot attached to the active trace.

        The runtime intentionally accepts plain metadata rather than importing the
        ledger object. This keeps evidence governance portable across notebook,
        sandbox, MCP, and external evidence-store implementations.
        """

        raw = state.metadata.get("active_evidence_ledger")
        if isinstance(raw, dict):
            fingerprint = raw.get("fingerprint")
            if not fingerprint:
                return None
            claim_ids = raw.get("claim_ids", [])
            if isinstance(claim_ids, str):
                normalized_claim_ids = [claim_ids]
            elif isinstance(claim_ids, (list, tuple, set)):
                normalized_claim_ids = [str(claim_id) for claim_id in claim_ids]
            else:
                normalized_claim_ids = [str(claim_ids)]
            return {
                "name": str(raw.get("name") or "evidence-ledger"),
                "fingerprint": str(fingerprint),
                "claim_ids": sorted(set(normalized_claim_ids)),
            }

        fingerprint = state.metadata.get("active_evidence_ledger_fingerprint")
        if not fingerprint:
            return None
        raw_claim_ids = state.metadata.get("active_evidence_claim_ids", [])
        if isinstance(raw_claim_ids, str):
            claim_ids = [raw_claim_ids]
        elif isinstance(raw_claim_ids, (list, tuple, set)):
            claim_ids = [str(claim_id) for claim_id in raw_claim_ids]
        else:
            claim_ids = [str(raw_claim_ids)]
        return {
            "name": str(state.metadata.get("active_evidence_ledger_name") or "evidence-ledger"),
            "fingerprint": str(fingerprint),
            "claim_ids": sorted(set(claim_ids)),
        }
