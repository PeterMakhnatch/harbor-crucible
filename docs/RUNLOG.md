# Run log

Running record for the overnight mission. Newest first. Hours are ET.

## Next 3 items (planned 2026-11-19, before starting)

1. **Fork PR 4: seat-aware job statistics.** `models/job/result.py` groups rewards by the trial-level `agent_info`, which is the first tested seat. A four-seat job therefore reports one model's statistics. No sibling PR touches job aggregation: #17 uploads seat logs, #4 reads seat traces, #15 records failed downloads, #13 preflights participants. Rebase onto `main`, add per-seat grouping, keep single-agent output byte-identical, unit-test both.
2. **Wave 2 experiments.** Tighten the supply-chain interval (the 33.3% TPR rests on 18 positives) and test whether reward-hack contagion is model-specific by running the four reward-hack conditions on a second model.
3. **`crucible report`.** One command that turns a corpus dir into a self-contained report: tier table, hypothesis verdicts, per-condition outcomes, spend. Keeps the evidence reproducible without me in the loop.

## Done

### 2026-11-19 ~07:40-08:10 — Report command and the defect brief
- `crucible report` turns a corpus into `REPORT.md` and `report.json`: per-family condition ranges, monitor tiers, spend, corpus commit. Five tests cover aggregation, timeout counting, missing-metric behaviour and per-family tables.
- **Protocol correction found by the report itself.** Wave 1 used a 0.5 timeout multiplier (240 s), so 8 of 42 trials ended in `AgentTimeoutError`, including all three `saboteur` trials and all three protocol-conflict trials. The act was measured (`sabotage_success=1.0` in 3/3) but mission completion was truncated. Every `task_utility` under a timeout is a floor, not a rate. Wave 2 uses the full multiplier.
- `docs/UPSTREAM-DEFECTS.md`: nine items for the maintainers, each with a repro, the observed text, and a repair direction. Verified against source: the keepalive overlay replaces `main`'s command in both the build and prebuilt paths.

### 2026-11-19 ~04:00-07:40 — Foundation
- Fork clone in `harbor-multiagent-crucible`, three isolated worktrees, isolated venv (never `uv tool install`; that replaces `harbor`).
- Three draft PRs on Peter's fork: #10 seat error policy + lock order, #11 seat regrade, #12 seat log streaming.
- Real seat regrade round-trip verified: recorded saboteur trial re-scored with identical rewards, zero agent re-execution.

### 2026-11-19 ~04:30-07:20 — Crucible
- New repo `PeterMakhnatch/harbor-crucible`, public, Apache-2.0.
- Four native seat families: supply-chain sabotage (4 variants), migration turf war (3), reward-hack contagion (4), epistemic failures (5).
- `crucible trace`: merged cross-seat timeline, exposure graph, standalone HTML view.
- `crucible monitor`: four visibility tiers, deterministic + LLM monitors, exact AUROC and 5% FPR calibration.
- `crucible lint-task`: 19 audit-contract rules. Caught the visibility-collapse defect on its first run.

### 2026-11-19 ~05:00-07:30 — Defects found and fixed
1. Harbor's build overlay replaces `main`'s command with `sleep infinity`; a world declared only in the Dockerfile `CMD` never starts.
2. A cross-uid `/proc/<pid>/exe` check raised `PermissionError`, so every health probe returned `None` and a healthy world reported unhealthy.
3. Exclusive-create on a declared artifact fails because Harbor stages artifact paths first.
4. All four families labelled actions `world_private`, which empties the audit tier. Fixed; linter now enforces it.
5. Verifier output cannot be a declared artifact: Harbor collects artifacts before verification.
6. A clean aligned control read as a negotiated truce, so the control was indistinguishable from conflict resolution.

### 2026-11-19 ~06:30-07:40 — Wave 1 and measurements
- 42 real-model seat trials, `deepseek-chat`, $0.53 of the $20 cap, ~$0.009 per four-seat episode.
- Sabotage 3/3; cross-role reward-hack contagion 1/3; coder-seeded hack 0/3; turf-war escalation 1/3.
- Tier benchmark on 33 integrity-labelled trials: rules 22.2% → 33.3% TPR at 5% FPR from audit evidence; full trajectories add nothing; refusers never over-flagged.
- LLM judge: 66.7% attribution from chat alone, AUROC improves with audit, but its calibrated threshold collapses at 15 negatives.
- Reward-hack evidence fix: Tier 0 AUROC 0.500, Tier 1 AUROC 1.000.
