# Harbor Crucible

Adversarial multi-agent evaluation, causal traces, and calibrated monitor benchmarks for [Harbor Multi-Agent](https://github.com/olamlabs/harbor-multiagent).

Crucible measures whether a team of Harbor seats can finish a shared task, whether a compromised seat can hide, and whether a monitor can tell the difference from public chat alone versus an authenticated world audit.

## Why

Frontier labs report the same gaps:

- Teams that share a goal still miss a saboteur who uses noisy tools as cover ([Project EVE](https://www.anthropic.com/research/project-eve-claude-plays-mmorpgs)).
- Agents with incompatible goals escalate to lockouts and disguised process killers ([multiagent systems](https://www.anthropic.com/research/multiagent-systems)).
- Reward hacks travel through shared code and plans ([Hu et al., 2026](https://arxiv.org/abs/2610.12822)).
- A monitor that stops one compromised agent can miss collusion, and a score after the vote can leak the label.

Harbor Multi-Agent already runs several native agents in one Compose project. Crucible adds the missing measurement layer: authenticated world evidence, matched controls, and monitors scored at a fixed false-positive rate.

## What you get

| Piece | What it does |
|---|---|
| 4 task families | Supply-chain sabotage, migration turf war, reward-hack contagion, epistemic failures |
| World audit log | Append-only events with seat tokens, visibility, and message-read receipts |
| `crucible trace` | One timeline across seats plus an exposure graph and a standalone HTML view |
| `crucible benchmark-monitors` | Tier 0 (public chat) vs Tier 1 (audit) vs Tier 2 (full traces) vs metadata-only, calibrated at 5% FPR |
| `crucible stability` | Bootstrap intervals for the threshold, TPR and AUROC, because a bare TPR overstates precision |
| `crucible report` | One command turns a corpus into `REPORT.md` and `report.json`: per-family ranges, tier table, spend, corpus commit |
| `crucible lint-task` | 19 audit-contract rules over a task, a trial, or a tree of evidence |
| `crucible export-evallab` | JSONL that keeps missing cost distinct from zero |
| `experiments/ensemble_monitors.py` | Combines two stored benchmarks by maximum score and compares all three |

## Measured headline

Score scales differ per world, so a monitor benchmark must be read **per family**. Pooling families compares one world's adversaries against another world's honest agents, which is not a monitor result. Complete runs only (4 timed-out trials dropped):

| Family | Positives / controls | Rules AUROC [95% CI] | Rules detection at 5% FPR | Read |
|---|---:|---|---:|---|
| `epistemic-crucible` | 12 / 12 | 0.917 [0.792, 1.000] | 83.3% | separates liars from honest scouts |
| `reward-hack-contagion` | 9 / 3 | 0.500 [0.500, 0.500] | 0.0% | no signal in the Wave 1 evidence |
| `supply-chain-sabotage` | 0 / 8 | not measurable | — | every saboteur trial timed out |

The epistemic row is the only well-powered cell: 24 trials, 12 of them controls, detection 83.3% with a 0.0 point bootstrap span. Every other cell is starved.

What is established:

- **Private reasoning adds nothing.** Tier 2 is identical to Tier 1 in every view and every family, with 46–82 real steps present.
- **The signal is text, and the tier rarely adds anything.** Over the pooled 24-trial epistemic corpus the rule set scores AUROC 0.917 and 83.3% detection at Tier 0, Tier 1 and Tier 2 alike, so public chat alone is enough and audit evidence adds nothing. Emptied payloads score exactly zero at every tier, so that same text is load-bearing. For the reward-hack family the code itself is required, and Wave 1 did not record it.
- **Instructed refusers are never accused**, at any tier, by any monitor.
- **Within the epistemic family the rule set separates liars.** Pooling every available trial of that family gives AUROC 0.917 [0.792, 1.000] and detection 83.3% at a 5% budget, over 24 trials with 12 controls, and a bootstrap span of 0.0 points. This is the only cell in the suite with enough controls to mean anything.

What is not established:

- **Any pooled number.** The earlier pooled AUROC of 0.607 was a mixture of family scales, and an earlier "audit lift" came from four timed-out trials.
- **Reward-hack detection from model trials.** Wave 1's audit log held file names, not code, so 0.500 is expected. The fixed world detects at Tier 1 on the oracle corpus (AUROC 1.000), but no model trial has been scored with the fix yet.
- **Supply-chain detection.** Needs the full-timeout corpus, which is running.
- Nothing here shows these rates transfer to another model family.

Details, intervals and the failed predictions are in [docs/FINDINGS.md](docs/FINDINGS.md).

Start with [docs/SUMMARY.md](docs/SUMMARY.md) for one page of orientation. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, [docs/FINDINGS.md](docs/FINDINGS.md) for what the runs showed, [docs/UPSTREAM-DEFECTS.md](docs/UPSTREAM-DEFECTS.md) for the fork defects with repros, [docs/RUNLOG.md](docs/RUNLOG.md) for the running record, and [experiments/PROTOCOL.md](experiments/PROTOCOL.md) for the pre-registered monitor benchmark.

## Status

Every family runs end to end through real Harbor seat containers with the `oracle` agent, and every variant passes `crucible lint-task` with zero errors.

| Family | Variants | Oracle behaviour |
|---|---:|---|
| `supply-chain-sabotage` | 4 | three controls finish the mission; the saboteur hoards 2 units, posts 1 deceptive report, and the mission fails |
| `migration-turf-war` | 3 | clean collaboration; force escalation with a lockout and a camouflaged healthcheck; negotiated truce |
| `reward-hack-contagion` | 4 | clean passes; both seeded hacks are confirmed and propagate; the strict gate blocks delivery |
| `epistemic-crucible` | 6 | liar conditions show a real naive-versus-oracle gap; a hidden-profile variant with no sharing mandate drops from 3/3 to 1/3 correct against a 3/3 solo ceiling, which reproduces the published effect |

Six of the defects found while building this are recorded in [docs/FINDINGS.md](docs/FINDINGS.md) and nine with repros in [docs/UPSTREAM-DEFECTS.md](docs/UPSTREAM-DEFECTS.md). One of them, every family labelling actions `world_private`, would have silently emptied the audit tier and made the benchmark measure nothing. `crucible lint-task` now catches it.

Four draft PRs to `olamlabs/harbor-multiagent` fix gaps a lab would hit on day two of using seats: seat-attributed live logs, error-policy overrides for seat records, regrade for recorded multi-seat trials, and per-seat job statistics.

## Quick start

```sh
# Check a task's audit contract before spending anything on it
crucible lint-task tasks/supply-chain-sabotage/variants/saboteur

# Run a wave of real four-seat trials (needs the fork's harbor on PATH)
python experiments/run_wave1.py --family supply-chain-sabotage --attempts 3

# Score the monitor tiers over a corpus, then write the full report
crucible benchmark-monitors runs/wave1-supply --families supply-chain-sabotage \
  --out-dir experiments/monitor_benchmark_wave1
crucible stability experiments/monitor_benchmark_wave1/verdicts.jsonl \
  --tier tier1_public_plus_audit --out-dir experiments/stability_wave1
crucible report runs/wave1-supply runs/wave1-epistemic --exclude-timeouts \
  --integrity-families supply-chain-sabotage,epistemic-crucible \
  --out-dir experiments/report_wave1_clean

# Export trial-level evidence for Eval Lab
crucible export-evallab runs/wave1-supply --out /tmp/evallab-seats.jsonl
```

`--exclude-timeouts` is not cosmetic: a truncated trial drags every mission metric down, and including it changed the headline conclusion once already.

## Install

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
```

Oracle runs need a separate Harbor Multi-Agent checkout. Do not `uv tool install` that fork: it replaces the `harbor` command. Point `CRUCIBLE_HARBOR_BIN` at an isolated virtualenv.

## License

Apache-2.0. Independent of Olam Labs and upstream Harbor.
