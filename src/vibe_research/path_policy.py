from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ActionPathPolicy:
    """Path-level policy for agent action sequences."""

    required_order: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    forbidden_subsequences: list[list[str]] = field(default_factory=list)
    max_repeats: dict[str, int] = field(default_factory=dict)
    end_with_any_of: list[str] = field(default_factory=list)

    def check(self, action_path: list[str]) -> list[str]:
        failures: list[str] = []

        for required in self.required_actions:
            if required not in action_path:
                failures.append(f"missing required action: {required}")

        for token, limit in self.max_repeats.items():
            count = action_path.count(token)
            if count > limit:
                failures.append(f"action {token} repeated {count} times (limit {limit})")

        for subsequence in self.forbidden_subsequences:
            if self._contains_subsequence(action_path, subsequence):
                failures.append(f"forbidden subsequence present: {' -> '.join(subsequence)}")

        if self.required_order:
            order_positions = [self._first_position(action_path, item) for item in self.required_order]
            if any(position is None for position in order_positions):
                missing = [item for item, position in zip(self.required_order, order_positions) if position is None]
                failures.append(f"missing ordered actions: {', '.join(missing)}")
            else:
                numeric_positions = [int(position) for position in order_positions if position is not None]
                if numeric_positions != sorted(numeric_positions):
                    failures.append(f"required order violated: {' -> '.join(self.required_order)}")

        if self.end_with_any_of and action_path:
            if action_path[-1] not in self.end_with_any_of:
                failures.append(
                    f"final action {action_path[-1]} not in allowed endings: {', '.join(self.end_with_any_of)}"
                )

        return failures

    @staticmethod
    def _first_position(action_path: list[str], token: str) -> int | None:
        try:
            return action_path.index(token)
        except ValueError:
            return None

    @staticmethod
    def _contains_subsequence(action_path: list[str], subsequence: list[str]) -> bool:
        if not subsequence or len(subsequence) > len(action_path):
            return False

        for start in range(0, len(action_path) - len(subsequence) + 1):
            if action_path[start : start + len(subsequence)] == subsequence:
                return True
        return False

