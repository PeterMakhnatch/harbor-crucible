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
| `crucible benchmark-monitors` | Tier 0 (public chat) vs Tier 1 (audit) vs Tier 2 (full traces), calibrated at 5% FPR |
| `crucible export-evallab` | JSONL that keeps missing cost distinct from zero |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, [docs/FINDINGS.md](docs/FINDINGS.md) for what the runs showed, and [experiments/PROTOCOL.md](experiments/PROTOCOL.md) for the pre-registered monitor benchmark.

## Status

Every family runs end to end through real Harbor seat containers with the `oracle` agent, and every variant passes `crucible lint-task` with zero errors.

| Family | Variants | Oracle behaviour |
|---|---:|---|
| `supply-chain-sabotage` | 4 | three controls finish the mission; the saboteur hoards 2 units, posts 1 deceptive report, and the mission fails |
| `migration-turf-war` | 3 | clean collaboration; force escalation with a lockout and a camouflaged healthcheck; negotiated truce |
| `reward-hack-contagion` | 4 | clean passes; both seeded hacks are confirmed and propagate; the strict gate blocks delivery |
| `epistemic-crucible` | 5 | liar conditions show a real naive-versus-oracle gap; the hidden-profile trap is avoided by the team |

Four defects found while building this are recorded in [docs/FINDINGS.md](docs/FINDINGS.md). One of them, every family labelling actions `world_private`, would have silently emptied the audit tier and made the benchmark measure nothing. `crucible lint-task` now catches it.

Three draft PRs to `olamlabs/harbor-multiagent` fix gaps a lab would hit on day two of using seats: seat-attributed live logs, error-policy overrides for seat records, and regrade for recorded multi-seat trials.

## Install

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
```

Oracle runs need a separate Harbor Multi-Agent checkout. Do not `uv tool install` that fork: it replaces the `harbor` command. Point `CRUCIBLE_HARBOR_BIN` at an isolated virtualenv.

## License

Apache-2.0. Independent of Olam Labs and upstream Harbor.
