"""Explicit spend ledger with hard budget cap enforcement for Crucible experiments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_BUDGET_CAP_USD = 20.0
DEFAULT_LEDGER_PATH = Path("experiments/spend_ledger.jsonl")


class SpendEntry(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str  # "trial_run" | "llm_monitor" | "infra"
    provider: str
    model: str
    trial_or_job: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    estimated: bool = False
    notes: str = ""


class BudgetExceededError(RuntimeError):
    """Raised when a planned or recorded run would exceed the approved dollar cap."""


# Approximate list prices per 1M tokens (USD), checked Nov 2026 — always log actual usage when reported.
MODEL_RATES_PER_M: dict[str, tuple[float, float]] = {
    "deepseek/deepseek-chat": (0.28, 0.42),
    "deepseek/deepseek-reasoner": (0.55, 2.19),
    "gemini/gemini-2.5-flash": (0.15, 0.60),
    "gemini/gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini/gemini-2.0-flash": (0.10, 0.40),
    "openrouter/deepseek/deepseek-chat-v3-0324": (0.30, 0.88),
    "openrouter/google/gemini-2.5-flash": (0.15, 0.60),
    "openrouter/anthropic/claude-haiku-4.5": (1.00, 5.00),
    "openrouter/anthropic/claude-sonnet-4.5": (3.00, 15.00),
}


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    in_rate, out_rate = MODEL_RATES_PER_M.get(model, (0.50, 1.50))
    return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate


class SpendLedger:
    def __init__(
        self,
        path: Path = DEFAULT_LEDGER_PATH,
        cap_usd: float = DEFAULT_BUDGET_CAP_USD,
    ) -> None:
        self.path = path
        self.cap_usd = cap_usd

    def entries(self) -> list[SpendEntry]:
        if not self.path.exists():
            return []
        rows: list[SpendEntry] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(SpendEntry.model_validate_json(line))
        return rows

    def total_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries()), 6)

    def remaining_usd(self) -> float:
        return round(max(0.0, self.cap_usd - self.total_usd()), 6)

    def check_headroom(self, planned_usd: float = 0.0) -> None:
        projected = self.total_usd() + planned_usd
        if projected > self.cap_usd:
            raise BudgetExceededError(
                f"Projected spend ${projected:.4f} exceeds cap ${self.cap_usd:.2f} "
                f"(already spent ${self.total_usd():.4f})."
            )

    def record(self, entry: SpendEntry) -> float:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")
        return self.total_usd()

    def summary(self) -> dict[str, Any]:
        items = self.entries()
        by_category: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for e in items:
            by_category[e.category] = round(by_category.get(e.category, 0.0) + e.cost_usd, 6)
            by_model[e.model] = round(by_model.get(e.model, 0.0) + e.cost_usd, 6)
        total = round(sum(e.cost_usd for e in items), 6)
        return {
            "cap_usd": self.cap_usd,
            "total_usd": total,
            "remaining_usd": round(max(0.0, self.cap_usd - total), 6),
            "n_entries": len(items),
            "by_category": by_category,
            "by_model": by_model,
        }
