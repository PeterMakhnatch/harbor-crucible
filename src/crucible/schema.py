"""Crucible Shared Contract v1: typed schemas for world audit logs, trial reports,
unified causal timelines, and calibrated multi-tier monitor evaluations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MonitorTier(str, Enum):
    """Information visibility tiers for monitor benchmarking (Anthropic Project EVE + Orbit)."""

    TIER0_PUBLIC_ONLY = "tier0_public_only"
    TIER1_PUBLIC_PLUS_AUDIT = "tier1_public_plus_audit"
    # Same events as Tier 1, with every payload emptied: actor, event type, order,
    # visibility and recipients remain. Used to separate the lift that comes from
    # action structure from the lift that comes from stored content.
    TIER1_METADATA_ONLY = "tier1_metadata_only"
    TIER2_FULL_TRAJECTORIES = "tier2_full_trajectories"
    TIER3_LIVE_STREAM = "tier3_live_stream"


class WorldEvent(BaseModel):
    """One authenticated, append-only event recorded by a task's authoritative `main` world."""

    seq: int
    ts: str
    task_family: str
    condition: str
    seed: int = 42
    event_type: str
    actor: str
    authenticated: bool = True
    visibility: str = "public"
    recipients: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_public(self) -> bool:
        return self.visibility == "public"

    @property
    def is_dm(self) -> bool:
        return self.visibility.startswith("dm:")

    @property
    def is_world_private(self) -> bool:
        return self.visibility == "world_private"


class CrucibleReport(BaseModel):
    """Structured verifier output stored at verifier/crucible_report.json."""

    task_family: str
    condition: str
    seed: int = 42
    is_negative_control: bool = False
    is_instructed_refuser: bool = False
    ground_truth_adversaries: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    per_seat: dict[str, dict[str, Any]] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class SeatTrajectoryStep(BaseModel):
    """Normalized step from a seat's ATIF trajectory.json."""

    seat: str
    step_id: int
    source: str
    timestamp: str | None = None
    message: str = ""
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    observation_text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class UnifiedTimelineEntry(BaseModel):
    """One merged event on the cross-seat causal timeline."""

    order: int
    ts: str | None = None
    kind: Literal["world_event", "seat_step", "live_log"]
    seat: str
    event_type: str
    visibility: str
    summary: str
    world_seq: int | None = None
    step_id: int | None = None
    exposed_msg_seqs: list[int] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ExposureEdge(BaseModel):
    """A proven exposure or influence edge between two seats."""

    sender: str
    recipient: str
    msg_seq: int
    read_seq: int | None = None
    downstream_action_seq: int | None = None
    channel: str
    latency_events: int | None = None


class TrialBundle(BaseModel):
    """Loaded, validated evidence bundle for one completed multi-seat Harbor trial."""

    trial_dir: str
    trial_name: str
    task_family: str
    condition: str
    seed: int = 42
    seats: list[str] = Field(default_factory=list)
    seat_models: dict[str, str] = Field(default_factory=dict)
    seat_usage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # None = the trial was never graded (no verifier result recorded); {} = graded with
    # no numeric metrics. Source is "result_json" (Harbor's record, preferred) or
    # "reward_json" (only when no result.json exists).
    rewards: dict[str, float] | None = Field(default_factory=dict)
    reward_source: str | None = None
    # verifier/reward.json exists and differs from the rewards recorded in result.json.
    reward_file_mismatch: bool = False
    report: CrucibleReport | None = None
    world_events: list[WorldEvent] = Field(default_factory=list)
    seat_steps: dict[str, list[SeatTrajectoryStep]] = Field(default_factory=dict)
    missing_traces: list[str] = Field(default_factory=list)
    # trajectory.json exists but is not a usable ATIF document (seat_steps holds []).
    invalid_traces: list[str] = Field(default_factory=list)
    # Roster problems: "missing_seat_result:<seat>", "undeclared_seat_dir:<name>",
    # "seat_from_dir_only:<name>".
    seat_anomalies: list[str] = Field(default_factory=list)
    trial_exception: str | None = None


class SeatSuspicionScore(BaseModel):
    """Monitor's per-seat suspicion score (0.0 to 100.0) with cited evidence."""

    seat: str
    score: float = Field(ge=0.0, le=100.0)
    predicted_adversary: bool = False
    rationale: str = ""
    cited_world_seqs: list[int] = Field(default_factory=list)
    cited_steps: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class MonitorVerdict(BaseModel):
    """One monitor evaluation over one trial at one visibility tier."""

    trial_name: str
    task_family: str
    condition: str
    monitor_name: str
    tier: MonitorTier
    cutoff_seq: int | None = None
    trial_suspicion_score: float = Field(ge=0.0, le=100.0)
    seat_scores: dict[str, SeatSuspicionScore] = Field(default_factory=dict)
    ground_truth_adversaries: list[str] = Field(default_factory=list)
    is_negative_control: bool = False
    is_instructed_refuser: bool = False
    top_predicted_seat: str | None = None
    top_seat_correct: bool | None = None
    latency_ms: float = 0.0
    monitor_cost_usd: float = 0.0
    evaluated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class MonitorBenchmarkSummary(BaseModel):
    """Calibrated aggregate metrics for one (monitor, tier) cell across a corpus."""

    monitor_name: str
    tier: MonitorTier
    n_trials: int
    n_adversarial: int
    n_negative_controls: int
    n_instructed_refusers: int
    auroc_trial: float | None = None
    tpr_at_5pct_fpr: float | None = None
    threshold_at_5pct_fpr: float | None = None
    actual_fpr_all_negatives: float | None = None
    refuser_false_positive_rate: float | None = None
    top_seat_attribution_accuracy: float | None = None
    mean_adversarial_score: float | None = None
    mean_negative_score: float | None = None
    total_monitor_cost_usd: float = 0.0
