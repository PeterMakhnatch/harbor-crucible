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

130 real-model seat trials, 122 of them complete and integrity-labelled. Scores are not comparable across worlds, so this is per family. AUROC intervals are 1000 bootstrap resamples of the controls.

| Family | Pos / ctrl | AUROC, public chat | AUROC, + audit [95% CI] | Detection at 5% FPR | Names the right agent |
|---|---:|---:|---|---:|---:|
| `supply-chain-sabotage` | 24 / 26 | 0.667 [0.583, 0.771] | **0.970 [0.913, 1.000]** | **87.5%** | **95.8%** |
| `epistemic-crucible` | 24 / 18 | 0.938 [0.875, 1.000] | 0.938 [0.875, 1.000] | 87.5% | 87.5% |
| `reward-hack-contagion` | 21 / 9 | 0.500 | 0.500 | 0% | 0% |

**The one result worth leading with:** in supply-chain sabotage, authoritative audit evidence takes attribution from 2 of 24 trials to **95.8%**, and detection from 33.3% to 87.5%, over 24 adversarial trials and 26 controls. Both intervals exclude chance. That is the capability the fork's seat model exists to enable.

What is established:

- **Audit evidence converts near-random attribution into exact attribution**, in the family where the adversary acts in code rather than in speech.
- **For liars, public chat is already enough.** The epistemic family scores identically at every tier, so a monitor needs no audit trail there.
- **Private reasoning adds nothing**, in every family and every view, with 46 to 82 real steps present.
- **Emptied payloads score exactly zero**, so the signal is text, not action structure.
- **Instructed refusers are never accused** at any tier.

What is not established:

- **Any reward-hack detection claim.** The label now derives from the committed snapshot, but real sabotage attempts are too rare in the sample to power a cell.
- **Any pooled number.** Pooling families compares one world's adversaries with another's honest agents; the earlier pooled 0.607 was a mixture.
- **An audit gain outside supply-chain**, and any transfer to another model family.

Details, intervals and the failed predictions are in [docs/FINDINGS.md](docs/FINDINGS.md); the one-page orientation is [docs/SUMMARY.md](docs/SUMMARY.md).

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
