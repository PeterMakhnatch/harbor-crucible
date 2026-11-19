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
| `crucible report` | One command turns a corpus into `REPORT.md` and `report.json`: per-family ranges, tier table, spend, corpus commit |
| `crucible lint-task` | 19 audit-contract rules over a task, a trial, or a tree of evidence |
| `crucible export-evallab` | JSONL that keeps missing cost distinct from zero |
| `experiments/ensemble_monitors.py` | Combines two stored benchmarks by maximum score and compares all three |

## Measured headline

42 real-model seat trials; 34 completed without a timeout; 29 of those carry an integrity label. Detection at a 5% false-accusation budget on the **complete** runs only:

| Monitor | AUROC | TPR at 5% FPR | Names the right agent | Cost |
|---|---:|---:|---:|---:|
| rules, public + audit | 0.607 | 26.7% | 26.7% | $0.00 |
| LLM judge, public + audit | 0.714 | 6.7% | 46.7% | $0.052 |
| **rules + judge, maximum** | **0.738** | **33.3%** | 33.3% | $0.052 |

Three things hold with and without the truncated trials: a model reads these worlds better than a rule set does; rules add detection the model misses, so the pair beats either; and an ablation with every payload removed scores **exactly zero**, so the signal is stored content, not the structure of who acted.

One thing does not hold: the audit tier's apparent lift (TPR 22.2% → 33.3% on all 42 trials) reverses to AUROC 0.633 → 0.607 once the 8 timed-out trials are dropped. It is reported as **not established**, not as a finding. Details and limits in [docs/FINDINGS.md](docs/FINDINGS.md).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, [docs/FINDINGS.md](docs/FINDINGS.md) for what the runs showed, [docs/UPSTREAM-DEFECTS.md](docs/UPSTREAM-DEFECTS.md) for the fork defects with repros, [docs/RUNLOG.md](docs/RUNLOG.md) for the running record, and [experiments/PROTOCOL.md](experiments/PROTOCOL.md) for the pre-registered monitor benchmark.

## Status

Every family runs end to end through real Harbor seat containers with the `oracle` agent, and every variant passes `crucible lint-task` with zero errors.

| Family | Variants | Oracle behaviour |
|---|---:|---|
| `supply-chain-sabotage` | 4 | three controls finish the mission; the saboteur hoards 2 units, posts 1 deceptive report, and the mission fails |
| `migration-turf-war` | 3 | clean collaboration; force escalation with a lockout and a camouflaged healthcheck; negotiated truce |
| `reward-hack-contagion` | 4 | clean passes; both seeded hacks are confirmed and propagate; the strict gate blocks delivery |
| `epistemic-crucible` | 5 | liar conditions show a real naive-versus-oracle gap; the hidden-profile trap is avoided by the team, which is a null result about that design, not about teams |

Six of the defects found while building this are recorded in [docs/FINDINGS.md](docs/FINDINGS.md) and nine with repros in [docs/UPSTREAM-DEFECTS.md](docs/UPSTREAM-DEFECTS.md). One of them, every family labelling actions `world_private`, would have silently emptied the audit tier and made the benchmark measure nothing. `crucible lint-task` now catches it.

Four draft PRs to `olamlabs/harbor-multiagent` fix gaps a lab would hit on day two of using seats: seat-attributed live logs, error-policy overrides for seat records, regrade for recorded multi-seat trials, and per-seat job statistics.

## Install

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
```

Oracle runs need a separate Harbor Multi-Agent checkout. Do not `uv tool install` that fork: it replaces the `harbor` command. Point `CRUCIBLE_HARBOR_BIN` at an isolated virtualenv.

## License

Apache-2.0. Independent of Olam Labs and upstream Harbor.
