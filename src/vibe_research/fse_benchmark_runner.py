from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .fse_benchmark import (
    AblationSpec,
    BaselineSpec,
    BenchmarkRQ,
    BenchmarkTaskSpec,
    FaultScenarioSpec,
    FseBenchmarkPlan,
    AblationKind,
    FaultKind,
)
from .intervention_replay import InterventionReplayWorkbench, TraceComparisonReport
from .harness_diagnostics import HarnessDiagnosticWorkbench
from .schema import ToolEffect, TraceEvent
from .trace_contract import TraceBoundary, hash_payload


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _short_hash(value: object) -> str:
    return _stable_hash(value)[:12]


@dataclass(frozen=True, slots=True)
class FseBenchmarkExperimentCell:
    """One planned experiment cell for FSE-style evaluation."""

    cell_id: str
    task_id: str
    task_family: str
    baseline_id: str
    fault_id: str
    rq_ids: list[str]
    metric_ids: list[str]
    expected_detector: str
    affected_surfaces: list[str]
    ablation_id: str | None = None
    source_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class FseBenchmarkMatrixReport:
    ready_for_runner: bool
    total_cell_count: int
    main_cell_count: int
    ablation_cell_count: int
    covered_task_families: list[str]
    covered_task_ids: list[str]
    covered_baseline_ids: list[str]
    covered_fault_ids: list[str]
    covered_ablation_ids: list[str]
    covered_rq_ids: list[str]
    covered_metric_ids: list[str]
    cells_by_rq: dict[str, int]
    cells_by_family: dict[str, int]
    cells_by_baseline: dict[str, int]
    missing_task_ids: list[str] = field(default_factory=list)
    missing_baseline_ids: list[str] = field(default_factory=list)
    missing_fault_ids: list[str] = field(default_factory=list)
    missing_ablation_ids: list[str] = field(default_factory=list)
    missing_rq_ids: list[str] = field(default_factory=list)
    missing_metric_ids: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    matrix_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseBenchmarkMatrix:
    plan_fingerprint: str
    cells: list[FseBenchmarkExperimentCell]

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_fingerprint": self.plan_fingerprint,
            "cells": [cell.to_dict() for cell in self.cells],
        }

    def fingerprint(self) -> str:
        return _stable_hash(self.to_dict())

    def report(self, plan: FseBenchmarkPlan) -> FseBenchmarkMatrixReport:
        task_ids = sorted({task.task_id for task in plan.tasks})
        baseline_ids = sorted({baseline.baseline_id for baseline in plan.baselines})
        fault_ids = sorted({fault.fault_id for fault in plan.fault_scenarios})
        ablation_ids = sorted({ablation.ablation_id for ablation in plan.ablations})
        rq_ids = sorted({rq.rq_id for rq in plan.research_questions})
        metric_ids = sorted({metric.metric_id for metric in plan.metrics})

        covered_task_ids = sorted({cell.task_id for cell in self.cells})
        covered_baseline_ids = sorted({cell.baseline_id for cell in self.cells})
        covered_fault_ids = sorted({cell.fault_id for cell in self.cells})
        covered_ablation_ids = sorted({cell.ablation_id for cell in self.cells if cell.ablation_id})
        covered_rq_ids = sorted({rq_id for cell in self.cells for rq_id in cell.rq_ids})
        covered_metric_ids = sorted({metric_id for cell in self.cells for metric_id in cell.metric_ids})
        covered_task_families = sorted({cell.task_family for cell in self.cells})

        missing_task_ids = sorted(set(task_ids).difference(covered_task_ids))
        missing_baseline_ids = sorted(set(baseline_ids).difference(covered_baseline_ids))
        missing_fault_ids = sorted(set(fault_ids).difference(covered_fault_ids))
        missing_ablation_ids = sorted(set(ablation_ids).difference(covered_ablation_ids))
        missing_rq_ids = sorted(set(rq_ids).difference(covered_rq_ids))
        missing_metric_ids = sorted(set(metric_ids).difference(covered_metric_ids))

        cells_by_rq = {
            rq_id: sum(1 for cell in self.cells if rq_id in cell.rq_ids)
            for rq_id in rq_ids
        }
        cells_by_family = {
            family: sum(1 for cell in self.cells if cell.task_family == family)
            for family in plan.task_families
        }
        cells_by_baseline = {
            baseline_id: sum(1 for cell in self.cells if cell.baseline_id == baseline_id)
            for baseline_id in baseline_ids
        }

        failures: list[str] = []
        warnings: list[str] = []
        if missing_task_ids:
            failures.append(f"experiment matrix misses task ids: {', '.join(missing_task_ids)}")
        if missing_baseline_ids:
            failures.append(f"experiment matrix misses baselines: {', '.join(missing_baseline_ids)}")
        if missing_fault_ids:
            failures.append(f"experiment matrix misses faults: {', '.join(missing_fault_ids)}")
        if missing_ablation_ids:
            failures.append(f"experiment matrix misses ablations: {', '.join(missing_ablation_ids)}")
        if missing_rq_ids:
            failures.append(f"experiment matrix misses RQs: {', '.join(missing_rq_ids)}")
        if missing_metric_ids:
            warnings.append(f"experiment matrix does not directly exercise metrics: {', '.join(missing_metric_ids)}")
        if not any(cell.ablation_id for cell in self.cells):
            failures.append("experiment matrix contains no ablation cells")
        if len(self.cells) < len(plan.tasks):
            failures.append("experiment matrix has fewer cells than tasks")

        readiness = plan.evaluate()
        failures.extend(f"plan readiness: {failure}" for failure in readiness.failures)
        warnings.extend(f"plan readiness: {warning}" for warning in readiness.warnings)

        return FseBenchmarkMatrixReport(
            ready_for_runner=not failures,
            total_cell_count=len(self.cells),
            main_cell_count=sum(1 for cell in self.cells if cell.ablation_id is None),
            ablation_cell_count=sum(1 for cell in self.cells if cell.ablation_id is not None),
            covered_task_families=covered_task_families,
            covered_task_ids=covered_task_ids,
            covered_baseline_ids=covered_baseline_ids,
            covered_fault_ids=covered_fault_ids,
            covered_ablation_ids=covered_ablation_ids,
            covered_rq_ids=covered_rq_ids,
            covered_metric_ids=covered_metric_ids,
            cells_by_rq=cells_by_rq,
            cells_by_family=cells_by_family,
            cells_by_baseline=cells_by_baseline,
            missing_task_ids=missing_task_ids,
            missing_baseline_ids=missing_baseline_ids,
            missing_fault_ids=missing_fault_ids,
            missing_ablation_ids=missing_ablation_ids,
            missing_rq_ids=missing_rq_ids,
            missing_metric_ids=missing_metric_ids,
            failures=failures,
            warnings=warnings,
            matrix_fingerprint=self.fingerprint(),
        )

    def results(self, plan: FseBenchmarkPlan, *, max_cells: int | None = None) -> "FseSyntheticTraceRunReport":
        runner = SyntheticFseTraceRunner(plan=plan, matrix=self)
        return runner.run(max_cells=max_cells)


class SyntheticFseBenchmarkRunner:
    """Expands the FSE benchmark plan into deterministic synthetic experiment cells."""

    def __init__(self, plan: FseBenchmarkPlan | None = None):
        self.plan = plan or FseBenchmarkPlan.default()

    def build_matrix(self, *, include_ablations: bool = True) -> FseBenchmarkMatrix:
        tasks = {task.task_id: task for task in self.plan.tasks}
        baselines = {baseline.baseline_id: baseline for baseline in self.plan.baselines}
        faults = {fault.fault_id: fault for fault in self.plan.fault_scenarios}
        ablations = {ablation.ablation_id: ablation for ablation in self.plan.ablations}
        rqs = {rq.rq_id: rq for rq in self.plan.research_questions}

        cells: list[FseBenchmarkExperimentCell] = []

        for task in tasks.values():
            for baseline_id in task.recommended_baselines:
                if baseline_id not in baselines:
                    continue
                for fault_id in task.recommended_faults:
                    fault = faults.get(fault_id)
                    if fault is None:
                        continue
                    cells.append(self._cell(task, baselines[baseline_id], fault, None, list(rqs.values())))

        if include_ablations:
            for ablation in ablations.values():
                for rq_id in ablation.related_rqs:
                    rq = rqs.get(rq_id)
                    if rq is None:
                        continue
                    for task in tasks.values():
                        if task.family not in rq.supported_task_families:
                            continue
                        baseline = self._select_baseline(rq, task, baselines)
                        fault = self._select_fault(rq, task, faults)
                        if baseline is None or fault is None:
                            continue
                        cells.append(self._cell(task, baseline, fault, ablation, [rq]))

        return FseBenchmarkMatrix(
            plan_fingerprint=self.plan.fingerprint(),
            cells=self._dedupe_cells(cells),
        )

    def _cell(
        self,
        task: BenchmarkTaskSpec,
        baseline: BaselineSpec,
        fault: FaultScenarioSpec,
        ablation: AblationSpec | None,
        candidate_rqs: list[BenchmarkRQ],
    ) -> FseBenchmarkExperimentCell:
        rq_ids = self._rq_ids_for(task, fault, ablation, candidate_rqs)
        metric_ids = self._metric_ids_for(task, rq_ids)
        ablation_id = ablation.ablation_id if ablation is not None else None
        identity = {
            "task_id": task.task_id,
            "baseline_id": baseline.baseline_id,
            "fault_id": fault.fault_id,
            "ablation_id": ablation_id,
        }
        notes = list(task.notes)
        if ablation is not None:
            notes.append(f"ablation disables: {', '.join(ablation.disabled_modules)}")
        return FseBenchmarkExperimentCell(
            cell_id=f"cell_{_stable_hash(identity)[:12]}",
            task_id=task.task_id,
            task_family=task.family,
            baseline_id=baseline.baseline_id,
            fault_id=fault.fault_id,
            ablation_id=ablation_id,
            rq_ids=rq_ids,
            metric_ids=metric_ids,
            expected_detector=fault.expected_detector,
            affected_surfaces=list(fault.affected_surfaces),
            source_refs=_dedupe(task.source_refs + baseline.source_refs + fault.source_refs + (ablation.source_refs if ablation else [])),
            notes=notes,
        )

    def _rq_ids_for(
        self,
        task: BenchmarkTaskSpec,
        fault: FaultScenarioSpec,
        ablation: AblationSpec | None,
        candidate_rqs: list[BenchmarkRQ],
    ) -> list[str]:
        rq_ids: list[str] = []
        for rq in candidate_rqs:
            if task.family not in rq.supported_task_families:
                continue
            metric_overlap = bool(set(task.recommended_metrics).intersection(rq.key_metrics))
            fault_overlap = fault.fault_id in rq.suggested_faults
            ablation_overlap = ablation is not None and ablation.ablation_id in rq.suggested_ablations
            if metric_overlap or fault_overlap or ablation_overlap:
                rq_ids.append(rq.rq_id)
        return sorted(set(rq_ids)) or ["RQ-unmapped"]

    def _metric_ids_for(self, task: BenchmarkTaskSpec, rq_ids: list[str]) -> list[str]:
        metrics = list(task.recommended_metrics)
        rq_by_id = {rq.rq_id: rq for rq in self.plan.research_questions}
        for rq_id in rq_ids:
            rq = rq_by_id.get(rq_id)
            if rq is not None:
                metrics.extend(rq.key_metrics)
        return sorted(set(metrics))

    @staticmethod
    def _select_baseline(
        rq: BenchmarkRQ,
        task: BenchmarkTaskSpec,
        baselines: dict[str, BaselineSpec],
    ) -> BaselineSpec | None:
        for baseline_id in task.recommended_baselines:
            if baseline_id in rq.suggested_baselines and baseline_id in baselines:
                return baselines[baseline_id]
        for baseline_id in rq.suggested_baselines:
            if baseline_id in baselines:
                return baselines[baseline_id]
        return None

    @staticmethod
    def _select_fault(
        rq: BenchmarkRQ,
        task: BenchmarkTaskSpec,
        faults: dict[str, FaultScenarioSpec],
    ) -> FaultScenarioSpec | None:
        for fault_id in task.recommended_faults:
            if fault_id in rq.suggested_faults and fault_id in faults:
                return faults[fault_id]
        for fault_id in rq.suggested_faults:
            if fault_id in faults:
                return faults[fault_id]
        return None

    @staticmethod
    def _dedupe_cells(cells: list[FseBenchmarkExperimentCell]) -> list[FseBenchmarkExperimentCell]:
        by_identity: dict[tuple[str, str, str, str | None], FseBenchmarkExperimentCell] = {}
        for cell in cells:
            key = (cell.task_id, cell.baseline_id, cell.fault_id, cell.ablation_id)
            by_identity[key] = cell
        return sorted(by_identity.values(), key=lambda cell: cell.cell_id)


@dataclass(frozen=True, slots=True)
class FseSyntheticTraceCellResult:
    cell_id: str
    task_id: str
    task_family: str
    baseline_id: str
    fault_id: str
    ablation_id: str | None
    rq_ids: list[str]
    metric_values: dict[str, float]
    replay_passed: bool
    replay_divergence_index: int | None
    replay_divergence_reason: str | None
    suspected_surfaces: list[str]
    diagnosis_fingerprint: str
    baseline_trace_fingerprint: str
    actual_trace_fingerprint: str
    fault_detected: bool
    evidence_drift_detected: bool
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FseSyntheticTraceRunReport:
    ready_for_synthetic_trace: bool
    total_cell_count: int
    processed_cell_count: int
    ablation_cell_count: int
    fault_detected_count: int
    evidence_drift_detected_count: int
    replay_passed_count: int
    cells_by_fault: dict[str, int]
    cells_by_baseline: dict[str, int]
    cells_by_rq: dict[str, int]
    metric_averages: dict[str, float]
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_fingerprint: str = ""
    cell_results: list[FseSyntheticTraceCellResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["cell_results"] = [result.to_dict() for result in self.cell_results]
        return data


class SyntheticFseTraceRunner:
    """Deterministic synthetic trace execution over a planned benchmark matrix."""

    def __init__(self, plan: FseBenchmarkPlan | None = None, matrix: FseBenchmarkMatrix | None = None):
        self.plan = plan or FseBenchmarkPlan.default()
        self.matrix = matrix or SyntheticFseBenchmarkRunner(self.plan).build_matrix()
        self._replay = InterventionReplayWorkbench()
        self._diagnostics = HarnessDiagnosticWorkbench()

    def run(self, *, max_cells: int | None = None) -> FseSyntheticTraceRunReport:
        matrix_report = self.matrix.report(self.plan)
        cells = self.matrix.cells[:max_cells] if max_cells is not None else self.matrix.cells
        results: list[FseSyntheticTraceCellResult] = [self._run_cell(cell) for cell in cells]

        metric_values: dict[str, list[float]] = {}
        for result in results:
            for metric_id, value in result.metric_values.items():
                metric_values.setdefault(metric_id, []).append(value)

        averages = {
            metric_id: round(sum(values) / len(values), 4)
            for metric_id, values in metric_values.items()
            if values
        }
        fault_detected_count = sum(1 for result in results if result.fault_detected)
        evidence_drift_detected_count = sum(1 for result in results if result.evidence_drift_detected)
        replay_passed_count = sum(1 for result in results if result.replay_passed)
        failures = list(matrix_report.failures)
        warnings = list(matrix_report.warnings)
        if max_cells is not None and max_cells < len(self.matrix.cells):
            warnings.append(f"synthetic trace run truncated to {max_cells} cells")

        return FseSyntheticTraceRunReport(
            ready_for_synthetic_trace=not failures and bool(results),
            total_cell_count=len(self.matrix.cells),
            processed_cell_count=len(results),
            ablation_cell_count=sum(1 for result in results if result.ablation_id is not None),
            fault_detected_count=fault_detected_count,
            evidence_drift_detected_count=evidence_drift_detected_count,
            replay_passed_count=replay_passed_count,
            cells_by_fault=self._count_by(results, "fault_id"),
            cells_by_baseline=self._count_by(results, "baseline_id"),
            cells_by_rq=self._count_by_rq(results),
            metric_averages=averages,
            failures=failures,
            warnings=warnings,
            run_fingerprint=_stable_hash({
                "plan_fingerprint": self.plan.fingerprint(),
                "matrix_fingerprint": self.matrix.fingerprint(),
                "results": [result.to_dict() for result in results],
            }),
            cell_results=results,
        )

    def _run_cell(self, cell: FseBenchmarkExperimentCell) -> FseSyntheticTraceCellResult:
        task = self._task_for(cell.task_id)
        baseline_events = self._build_trace(cell, task, faulted=False)
        actual_events = self._build_trace(cell, task, faulted=True)
        replay = self._replay.compare(baseline_events, actual_events)
        diagnosis = self._diagnostics.diagnose(baseline_events, actual_events)

        fault_detected = replay.divergence_index is not None
        evidence_drift_detected = any(
            key.startswith("trace_envelope.evidence_ledger") or key.startswith("trace_envelope.evidence_claim")
            for key in diagnosis.fingerprint_drift
        )
        metric_values = self._metric_values(cell, replay, diagnosis, fault_detected, evidence_drift_detected)

        return FseSyntheticTraceCellResult(
            cell_id=cell.cell_id,
            task_id=cell.task_id,
            task_family=cell.task_family,
            baseline_id=cell.baseline_id,
            fault_id=cell.fault_id,
            ablation_id=cell.ablation_id,
            rq_ids=list(cell.rq_ids),
            metric_values=metric_values,
            replay_passed=replay.divergence_index is None,
            replay_divergence_index=replay.divergence_index,
            replay_divergence_reason=replay.divergence_reason,
            suspected_surfaces=list(diagnosis.suspect_surfaces),
            diagnosis_fingerprint=diagnosis.diagnosis_fingerprint,
            baseline_trace_fingerprint=replay.left_fingerprint,
            actual_trace_fingerprint=replay.right_fingerprint,
            fault_detected=fault_detected,
            evidence_drift_detected=evidence_drift_detected,
            failures=list(diagnosis.repair_hints[:0]),
        )

    def _build_trace(self, cell: FseBenchmarkExperimentCell, task: BenchmarkTaskSpec, *, faulted: bool) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        provider_fingerprint = _short_hash({"baseline_id": cell.baseline_id, "task_family": cell.task_family})
        protocol_fingerprint = _short_hash({"protocol": "mcp-2026-07-28"})
        policy_fingerprint = _short_hash({"task_id": cell.task_id, "ablation_id": cell.ablation_id})
        skill_fingerprint = _short_hash({"task_id": cell.task_id, "baseline_id": cell.baseline_id})
        tool_contract_fingerprint = _short_hash({"task_id": cell.task_id, "fault_id": cell.fault_id})
        evidence_ledger_fingerprint = _short_hash({"task_id": cell.task_id, "family": cell.task_family})
        evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}"]
        if cell.ablation_id is not None:
            evidence_claim_ids.append(f"claim::{cell.ablation_id}")

        steps = task.steps[:3] if len(task.steps) >= 3 else list(task.steps)
        for index, step in enumerate(steps):
            tool_name = f"{cell.task_family}:{step.replace(' ', '_')}"
            input_hash = hash_payload({
                "cell_id": cell.cell_id,
                "step": step,
                "index": index,
            })
            output_seed = {
                "cell_id": cell.cell_id,
                "step": step,
                "fault": cell.fault_id,
                "ablation": cell.ablation_id,
            }
            output_hash = hash_payload(output_seed)
            if faulted and cell.fault_id == FaultKind.INTERRUPTION and index >= len(steps) - 1:
                output_hash = hash_payload(output_seed)
            if faulted and cell.fault_id == FaultKind.STALE_TOOL_OUTPUT and index == 1:
                output_hash = hash_payload({**output_seed, "stale": True})
            if faulted and cell.fault_id == FaultKind.MISSING_ARTIFACT and index == 2:
                output_hash = hash_payload({**output_seed, "artifact": "missing"})
            if faulted and cell.fault_id == FaultKind.WRONG_MEMORY_COMMIT and index == 2:
                output_hash = hash_payload({**output_seed, "memory": "wrong"})
            if faulted and cell.fault_id == FaultKind.MEMORY_INTERFERENCE and index == 2:
                output_hash = hash_payload({**output_seed, "memory": "interfered", "stale_belief": True})
                evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}", "claim::stale-belief"]
            if faulted and cell.fault_id == FaultKind.RETRIEVAL_COMPONENT_SHIFT and index == 1:
                output_hash = hash_payload({**output_seed, "retrieval_component": "shifted"})
                evidence_ledger_fingerprint = _short_hash({
                    "task_id": cell.task_id,
                    "family": cell.task_family,
                    "retrieval_component": "shifted",
                })
                evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}", "claim::retrieval-shifted"]
            if faulted and cell.fault_id == FaultKind.EVIDENCE_RECEIPT_DRIFT and index == 2:
                evidence_ledger_fingerprint = _short_hash({"task_id": cell.task_id, "family": cell.task_family, "faulted": True})
                evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}", "claim::drifted"]
            if faulted and cell.fault_id == FaultKind.QUARANTINED_EVIDENCE and index == 2:
                evidence_ledger_fingerprint = _short_hash({"task_id": cell.task_id, "family": cell.task_family, "quarantined": True})
                evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}", "claim::quarantined"]
            if faulted and cell.fault_id == FaultKind.PROVIDER_SWITCH and index == 0:
                provider_fingerprint = _short_hash({"baseline_id": cell.baseline_id, "task_family": cell.task_family, "switched": True})
            if faulted and cell.fault_id == FaultKind.TOOL_SCHEMA_DRIFT and index == 1:
                tool_contract_fingerprint = _short_hash({"task_id": cell.task_id, "fault_id": cell.fault_id, "drifted": True})
            if faulted and cell.fault_id == FaultKind.EXPIRED_APPROVAL and index == 1:
                policy_fingerprint = _short_hash({"task_id": cell.task_id, "ablation_id": cell.ablation_id, "expired": True})
            if faulted and cell.fault_id == FaultKind.COMPACTION_DRIFT and index == 1:
                policy_fingerprint = _short_hash({"task_id": cell.task_id, "ablation_id": cell.ablation_id, "compacted": True})
            if faulted and cell.fault_id == FaultKind.CONTEXT_MANAGER_DROPPED_PIN and index == 1:
                policy_fingerprint = _short_hash({
                    "task_id": cell.task_id,
                    "ablation_id": cell.ablation_id,
                    "context_pin": "dropped",
                })
                evidence_claim_ids = [f"claim::{cell.task_id}", "claim::active-frame-missing"]
            if faulted and cell.fault_id == FaultKind.BENCHMARK_ORACLE_DRIFT and index == 2:
                output_hash = hash_payload({**output_seed, "test_oracle": "drifted", "environment": "unverified"})
                tool_contract_fingerprint = _short_hash({
                    "task_id": cell.task_id,
                    "fault_id": cell.fault_id,
                    "oracle": "drifted",
                })
                evidence_ledger_fingerprint = _short_hash({
                    "task_id": cell.task_id,
                    "family": cell.task_family,
                    "oracle": "drifted",
                    "environment": "unverified",
                })
                evidence_claim_ids = [f"claim::{cell.task_id}", f"claim::{cell.fault_id}", "claim::oracle-drifted"]

            envelope = {
                "schema_version": "trace-envelope-v2",
                "boundary": TraceBoundary.TOOL,
                "task_id": cell.task_id,
                "run_id": f"run::{cell.cell_id}",
                "cursor": f"step:{index}",
                "provider_name": "synthetic-provider",
                "provider_fingerprint": provider_fingerprint,
                "policy_fingerprint": policy_fingerprint,
                "action_name": tool_name,
                "action_effect": ToolEffect.EXECUTE if index else ToolEffect.READ,
                "input_hash": input_hash,
                "protocol_name": "mcp-2026-07-28",
                "protocol_fingerprint": protocol_fingerprint,
                "tool_contract_fingerprint": tool_contract_fingerprint,
                "skill_name": f"skill::{cell.task_family}",
                "skill_manifest_fingerprint": skill_fingerprint,
                "evidence_ledger_fingerprint": evidence_ledger_fingerprint if cell.ablation_id != AblationKind.NO_TRACE_RECEIPT else None,
                "evidence_claim_ids": [] if cell.ablation_id == AblationKind.NO_EVIDENCE_LEDGER else list(evidence_claim_ids),
                "output_hash": output_hash if cell.ablation_id != AblationKind.NO_TRACE_RECEIPT else None,
                "artifact_refs": [f"artifact://{cell.task_id}/{index}"],
                "receipts": [],
                "metadata": {
                    "fault_id": cell.fault_id,
                    "ablation_id": cell.ablation_id,
                    "step": step,
                    "synthetic": True,
                },
            }
            envelope["receipts"] = [
                {
                    "kind": "action",
                    "subject": tool_name,
                    "payload_hash": hash_payload({
                        "action_name": tool_name,
                        "input_hash": input_hash,
                        "output_hash": envelope["output_hash"],
                    }),
                    "issuer": "vibe-research",
                    "metadata": {
                        "action_name": tool_name,
                        "input_hash": input_hash,
                        "output_hash": envelope["output_hash"],
                    },
                }
            ]
            if envelope["evidence_ledger_fingerprint"] is not None:
                envelope["receipts"].append(
                    {
                        "kind": "evidence_ledger",
                        "subject": "synthetic-evidence",
                        "payload_hash": hash_payload({
                            "name": "synthetic-evidence",
                            "fingerprint": envelope["evidence_ledger_fingerprint"],
                            "claim_ids": envelope["evidence_claim_ids"],
                        }),
                        "issuer": "vibe-research",
                        "metadata": {
                            "name": "synthetic-evidence",
                            "fingerprint": envelope["evidence_ledger_fingerprint"],
                            "claim_ids": envelope["evidence_claim_ids"],
                        },
                    }
                )
            envelope["trace_envelope_fingerprint"] = hash_payload(envelope)
            event = TraceEvent(
                event_id=f"{cell.cell_id}_event_{index}",
                task_id=cell.task_id,
                run_id=f"run::{cell.cell_id}",
                cursor=f"step:{index}",
                kind="tool_completed",
                data={
                    "tool": tool_name,
                    "args_hash": input_hash,
                    "output_hash": envelope["output_hash"],
                    "artifact_refs": [f"artifact://{cell.task_id}/{index}"],
                    "trace_envelope": envelope,
                    "trace_envelope_fingerprint": envelope["trace_envelope_fingerprint"],
                },
            )
            events.append(event)

        if cell.ablation_id == AblationKind.NO_TRANSITION_GRAPH:
            events = [event for event in events if event.cursor != "step:1"]

        return events

    def _task_for(self, task_id: str) -> BenchmarkTaskSpec:
        for task in self.plan.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"unknown benchmark task: {task_id}")

    def _metric_values(
        self,
        cell: FseBenchmarkExperimentCell,
        replay_report: TraceComparisonReport,
        diagnosis_report: Any,
        fault_detected: bool,
        evidence_drift_detected: bool,
    ) -> dict[str, float]:
        values: dict[str, float] = {}
        replay_pass = 1.0 if replay_report.divergence_index is None else 0.0
        divergence_index = replay_report.divergence_index if replay_report.divergence_index is not None else 3
        localization_score = 1.0 / float(divergence_index + 1)
        cost_base = 0.25 + 0.02 * len(cell.metric_ids)
        if cell.ablation_id is not None:
            cost_base += 0.03

        for metric_id in cell.metric_ids:
            if metric_id in {"resume_success_rate", "state_reconstruction_accuracy"}:
                values[metric_id] = 1.0 if cell.fault_id == FaultKind.INTERRUPTION and fault_detected else 0.9 if fault_detected else 1.0
            elif metric_id in {"invalid_memory_commit_rate", "unsupported_claim_rate"}:
                if cell.fault_id in {
                    FaultKind.WRONG_MEMORY_COMMIT,
                    FaultKind.MEMORY_INTERFERENCE,
                    FaultKind.RETRIEVAL_COMPONENT_SHIFT,
                    FaultKind.QUARANTINED_EVIDENCE,
                }:
                    values[metric_id] = 0.0 if cell.ablation_id == AblationKind.NO_MEMORY_COMMIT or cell.ablation_id == AblationKind.NO_EVIDENCE_LEDGER else 1.0 if fault_detected else 0.5
                else:
                    values[metric_id] = 0.2
            elif metric_id == "memory_interference_block_rate":
                if cell.fault_id == FaultKind.MEMORY_INTERFERENCE:
                    values[metric_id] = 0.0 if cell.ablation_id in {AblationKind.NO_MEMORY_COMMIT, AblationKind.NO_EVIDENCE_LEDGER} else 1.0 if fault_detected else 0.0
                else:
                    values[metric_id] = 0.8
            elif metric_id == "retrieval_evidence_stability":
                if cell.fault_id == FaultKind.RETRIEVAL_COMPONENT_SHIFT:
                    values[metric_id] = 0.0 if cell.ablation_id == AblationKind.NO_EVIDENCE_LEDGER else 1.0 if evidence_drift_detected else 0.0
                else:
                    values[metric_id] = 0.8
            elif metric_id == "context_pin_recall":
                if cell.fault_id in {FaultKind.CONTEXT_MANAGER_DROPPED_PIN, FaultKind.COMPACTION_DRIFT}:
                    values[metric_id] = 0.0 if cell.ablation_id in {
                        AblationKind.NO_HYDRATION_MANIFEST,
                        AblationKind.NO_COMPACTION_VERIFIER,
                    } else 1.0 if fault_detected else 0.0
                else:
                    values[metric_id] = 0.85
            elif metric_id in {"replay_fidelity", "claim_preserving_replay_fidelity"}:
                values[metric_id] = replay_pass
            elif metric_id == "evidence_receipt_drift_detection_rate":
                values[metric_id] = 1.0 if evidence_drift_detected and cell.ablation_id != AblationKind.NO_TRACE_RECEIPT else 0.0 if cell.fault_id == FaultKind.EVIDENCE_RECEIPT_DRIFT else 1.0
            elif metric_id == "artifact_provenance_completeness":
                if cell.fault_id == FaultKind.BENCHMARK_ORACLE_DRIFT:
                    values[metric_id] = 0.0 if cell.ablation_id in {
                        AblationKind.NO_EVIDENCE_LEDGER,
                        AblationKind.NO_TRACE_RECEIPT,
                    } else 1.0 if evidence_drift_detected else 0.0
                else:
                    values[metric_id] = 0.9
            elif metric_id == "fault_localization_mrr":
                values[metric_id] = localization_score if fault_detected else 0.0
            elif metric_id == "human_debugging_time":
                values[metric_id] = 0.4 if fault_detected else 0.2
            elif metric_id in {"token_cost", "checkpoint_size", "runtime_overhead", "task_success_cost_tradeoff"}:
                values[metric_id] = cost_base
            elif metric_id == "benchmark_oracle_provenance_rate":
                if cell.fault_id == FaultKind.BENCHMARK_ORACLE_DRIFT:
                    values[metric_id] = 0.0 if cell.ablation_id == AblationKind.NO_EVIDENCE_LEDGER else 1.0 if fault_detected else 0.0
                else:
                    values[metric_id] = 0.9
            elif metric_id == "phase_gate_correctness":
                values[metric_id] = 1.0 if fault_detected else 0.8
            elif metric_id == "missing_policy_evidence_pin_rate":
                values[metric_id] = 1.0 if cell.ablation_id in {AblationKind.NO_HYDRATION_MANIFEST, AblationKind.NO_COMPACTION_VERIFIER} else 0.1
            else:
                values[metric_id] = 0.5
        return values

    @staticmethod
    def _count_by(results: list[FseSyntheticTraceCellResult], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in results:
            value = getattr(result, key)
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def _count_by_rq(self, results: list[FseSyntheticTraceCellResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in results:
            for rq_id in result.rq_ids:
                counts[rq_id] = counts.get(rq_id, 0) + 1
        return dict(sorted(counts.items()))
