from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4

from .process_lifecycle import ProcessStage
from .schema import BudgetState, HarnessPolicy, RuntimeState, TraceEvent


@dataclass(frozen=True, slots=True)
class CheckpointBundle:
    state: RuntimeState
    events: list[TraceEvent]


class JsonCheckpointStore:
    """Small local checkpoint store for deterministic resume and replay tests."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, state: RuntimeState, events: list[TraceEvent]) -> str:
        task_dir = self.root / state.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_ref = f"{state.task_id}/ckpt_{state.version:06d}.json"
        payload = {
            "state": state.to_dict(),
            "events": [event.to_dict() for event in events],
        }
        checkpoint_path = self.root / checkpoint_ref
        checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        (task_dir / "latest").write_text(checkpoint_ref, encoding="utf-8")
        return checkpoint_ref

    def load(self, checkpoint_ref: str) -> CheckpointBundle:
        checkpoint_path = self.root / checkpoint_ref
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return CheckpointBundle(
            state=RuntimeState.from_dict(payload["state"]),
            events=[TraceEvent.from_dict(item) for item in payload.get("events", [])],
        )

    def load_latest(self, task_id: str) -> CheckpointBundle:
        latest_ref = (self.root / task_id / "latest").read_text(encoding="utf-8").strip()
        return self.load(latest_ref)


class HermesRuntime:
    """Owns task/session identity, checkpoints, and rehydration."""

    def __init__(self, store: JsonCheckpointStore, policy: HarnessPolicy | None = None):
        self.store = store
        self.policy = policy or HarnessPolicy()

    def start_task(self, goal: str, *, budget_state: BudgetState | None = None) -> RuntimeState:
        task_id = f"task_{uuid4().hex[:12]}"
        state = RuntimeState(
            task_id=task_id,
            session_id=f"sess_{uuid4().hex[:12]}",
            run_id=f"run_{uuid4().hex[:12]}",
            trace_id=f"trace_{uuid4().hex[:12]}",
            goal=goal,
            process_stage=ProcessStage.ACTIVE,
            budget_state=budget_state or BudgetState(),
            policy_snapshot=self.policy.to_dict(),
        )
        self.checkpoint(state, [], reason="task_started")
        return state

    def checkpoint(self, state: RuntimeState, events: list[TraceEvent], *, reason: str) -> str:
        state.version += 1
        state.metadata["checkpoint_reason"] = reason
        checkpoint_ref = self.store.save(state, events)
        state.checkpoint_ref = checkpoint_ref
        self.store.save(state, events)
        return checkpoint_ref

    def resume_latest(self, task_id: str) -> CheckpointBundle:
        return self.store.load_latest(task_id)
