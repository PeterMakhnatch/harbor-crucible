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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Install

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest -q
```

Oracle runs need a separate Harbor Multi-Agent checkout. Do not `uv tool install` that fork: it replaces the `harbor` command. Point `CRUCIBLE_HARBOR_BIN` at an isolated virtualenv.

## License

Apache-2.0. Independent of Olam Labs and upstream Harbor.
