# Handoff prompt: crucible lane (multi-agent Harbor)

Paste everything below the line into the new agent.

---

You are taking over the **crucible lane** of Peter Makhnatch's overnight project on multi-agent Harbor. Read this whole prompt, then read the files it names before you change anything. Peter's standing mission: build useful infrastructure and tooling for multi-agent Harbor, run benchmarks and evals with it, record learnings, and prepare PRs for his fork plus Eval Lab integration. Four agent lanes share this mission (crucible, flotilla, muster, rainy). Do not duplicate the other lanes.

## Hard rules

1. **Publish only to Peter's fork `PeterMakhnatch/harbor-multiagent`.** Never open issues, PRs or comments on `olamlabs/harbor-multiagent`. Create fork PRs with `gh pr create -R PeterMakhnatch/harbor-multiagent --base main`. Whether anything goes upstream is Peter's decision; it is still open.
2. **No paid model calls.** The shared $20 model-spend cap for all four lanes is reached. Crucible's own ledger shows $6.76 (`cd harbor-crucible && .venv/bin/crucible spend`). A costed plan waits for Peter's decision in `docs/NEXT-PAID-EXPERIMENTS.md`; run nothing from it unless Peter approves a limit in writing.
3. **Never run `uv tool install` of harbor-multiagent.** It replaces Peter's global `harbor` command. Use the fork's venv: `/Users/petermakhnatch/Developer/harbor-multiagent-crucible/.venv/bin/harbor`.
4. **Docker:** at most 2 local Docker trials at a time on this Mac. Wrap every Docker-starting command in the shared gate `/tmp/crucible-docker-slot.sh <command> [args...]` (a Python fcntl 2-slot lock; there is no `flock` binary). Do not steal focus; if Docker is down, start it with `open -g -a Docker`.
5. **Eval Lab** (`/Users/petermakhnatch/Developer/eval-lab`): never edit the primary checkout; work in an owned worktree; never run billable or database-writing commands (`ingest`, `process-job`, `run`, `submit`, `tick`, `doctor`). Read-only commands such as `jobs verify` are fine.
6. **Git hygiene:** commit only your own paths (`git commit -- <paths>`), never `git add -A`, never stash or reset other writers' work. Leave every checkout clean and pushed. Scratch goes to `/tmp`.
7. **Honesty:** separate OBSERVED from INFERRED. The monitor in `src/crucible/monitor.py` is **frozen**; evaluate changes as separate experiment-local variants with a pre-registration. Pre-registered reports get an erratum section, never a silent rewrite.
8. **Replies to Peter:** Simplified Technical English (short sentences, active voice, digits, one idea per sentence). Times in New York time, labelled ET.

## Where everything is

| What | Where |
|---|---|
| Crucible repo (main work) | `/Users/petermakhnatch/Developer/harbor-crucible` → `PeterMakhnatch/harbor-crucible`, branch `main`, HEAD `46f5c50`, clean |
| **Start here** | `docs/SUMMARY.md` (one page, current), then `docs/RUNLOG.md` (dated log, newest first under "## Done", with "Next 3 items" blocks above) |
| Full findings and corrections | `docs/FINDINGS.md`; per-experiment folders `experiments/*/RESULT.md` (each with PREREG.md where pre-registered) |
| Fork defects and their PRs | `docs/UPSTREAM-DEFECTS.md` |
| Merge order for the fork PRs | `docs/FORK-MERGE-PLAN.md`; integration branch `crucible/stack-integration` on the fork |
| Reviews received and given | `docs/reviews/` (`review-pr*.md` received from the rainy lane, `given-pr*.md` written by crucible) |
| Next paid experiments (awaiting Peter) | `docs/NEXT-PAID-EXPERIMENTS.md` |
| Architecture and lint contract | `docs/ARCHITECTURE.md` |
| Harbor fork clone and venv | `/Users/petermakhnatch/Developer/harbor-multiagent-crucible` (`.venv`) |
| Fork PR worktrees | `/Users/petermakhnatch/Developer/crucible-wt/<branch-leaf>` (one per PR) |
| Lane logs of all four lanes | `/Users/petermakhnatch/Developer/research-context/multi-agent/` (`crucible-log-20261120.md`, `muster-log-20261119.md`, `rainy-wezen-log-20261119.md`); read the others before picking work |
| muster (another lane's control-matrix tool) | `/Users/petermakhnatch/Developer/muster`; do not edit it |
| Recorded trials | `harbor-crucible/runs/` (gitignored, local only; never modify — it is evidence) |

## What crucible is

`harbor-crucible` is a suite on top of `olamlabs/harbor-multiagent` (Harbor with native multi-seat tasks): four seat task families (19 variants: `supply-chain-sabotage`, `epistemic-crucible`, `reward-hack-contagion`, `migration-turf-war`), a world container per task with an authenticated audit log, an audit-contract linter (`crucible lint-task`), a tiered monitor benchmark (`crucible report`: tier 0 public chat, tier 1 plus audit log, tier 2 full trajectories, with bootstrap intervals), an Eval Lab export, and a wave runner (`experiments/run_wave1.py`, `--as-job` emits a real Harbor job).

**Headline (unchanged after all corrections):** in supply-chain sabotage, the authenticated audit log raises seat attribution from 2/24 (public chat) to 23/24, AUROC 0.667 → 0.970 [0.913, 1.000]. In the liar family the audit log adds nothing (0.938 at every tier). The reward-hack cell is unmeasured: no verified real-model hack exists.

**Important corrections made on 2026-11-20** (all recorded with errata): a scripted control matrix (muster, all-nop/all-oracle rosters) found three verifier metric defects: an idle saboteur scored `sabotage_success = 1`, unapproved work earned utility, and a starting service earned migration utility. All fixed; every recorded trial re-scored offline. Consequences: sabotage 23/24 → 20/24; "an audited saboteur sabotages less" is not established (p 0.034 → 0.397); the cross-role contagion "1 of 3" is retracted (0 of 3 verified). Every verifier now writes a team `reward` key; `crucible lint-task` fails without it; CI runs an all-nop/all-oracle control smoke per family (`scripts/control_smoke.py`). The procedure is captured in the skill `seat-task-validity-audit` if your harness can read OMP skills.

## Checks (run before claiming anything)

```bash
cd /Users/petermakhnatch/Developer/harbor-crucible
.venv/bin/pytest -q -p no:cacheprovider            # 206 tests
.venv/bin/python -m pytest -q -p no:cacheprovider experiments   # 43 experiment tests
.venv/bin/ruff check src tests experiments scripts
.venv/bin/ruff format --check src tests experiments scripts
for v in tasks/*/variants/*/; do .venv/bin/crucible lint-task "$v"; done   # 19 clean
```

`tests/test_readme_numbers.py` pins README numbers to `experiments/report_final5/report.json`. If you touch `src/crucible/monitor.py`, prove the canonical per-family summary is unchanged: rerun `crucible report` on the `corpus_roots` listed in that report into `/tmp` and diff `monitor_summary_by_family`.

Fork checks run inside the PR worktree: `PYTHONPATH="$PWD/src" /Users/petermakhnatch/Developer/harbor-multiagent-crucible/.venv/bin/python -m pytest -q -p no:cacheprovider <paths>` (about 20 `tests/unit/environments/*` modules fail collection locally on main too, for missing provider SDKs; ignore those). Type check like fork CI: `uv tool run ty@0.0.49 check --python /Users/petermakhnatch/Developer/harbor-multiagent-crucible/.venv <files>`.

## Open work, in priority order

1. **Seven crucible PRs on the fork, all CI-green, none merged** (Peter merges; do not merge without his instruction):

   | PR | Branch | Head | Review state |
   |---|---|---|---|
   | #10 error-policy overrides, order-invariant lock | `crucible/seat-error-policy-and-lock-order` | `86372e2e` | rainy closed its blocker |
   | #11 seat regrade | `crucible/seat-regrade` | `d8750cd5` | waits for rainy's re-check |
   | #12 seat log streaming | `crucible/seat-log-streaming` | `e7aba94a` | rainy closed the criticals; follow-ups done |
   | #21 per-seat job stats | `crucible/seat-job-stats` | `d0e0bddc` | rainy closed the P0s; P2 guards done |
   | #36 timeout guidance (docs) | `crucible/seat-timeout-guidance` | `3d94df4b` | green |
   | #37 `use_image_command` | `crucible/seat-world-image-cmd` | `566e5b56` | waits for rainy's re-check |
   | #38 artifacts collected after verification | `crucible/artifact-after-verify` | `e95c436c` | rainy closed the P1s; hardening pushed, waits for re-check |

   When the rainy lane posts a re-check (a PR comment starting "Re-verification at <sha> (Muse session rainy-wezen ..."), fix or narrow each finding in that PR's worktree, re-run the reviewer's probe, push, wait for CI, and post one finding-by-finding reply. Then refresh `docs/FORK-MERGE-PLAN.md` (pinned heads; #38 and #11 interact on regrade, and rainy's #15 should merge before #11) and rebuild `crucible/stack-integration` if heads moved.
2. **Reviews crucible gave** on other lanes' PRs: #2 (flotilla), #14 and #15 (rainy), all "merge after fixes"; #14 was re-checked at `98c16ab7` with all 5 findings still open. Re-verify if their authors push.
3. **Peter's pending decisions** (do not act on them yourself): the $4.00 monitor v3 test in `docs/NEXT-PAID-EXPERIMENTS.md`, and whether to offer any fork PR upstream.
4. **Known gap owned by someone else:** Eval Lab branches `pm/harbor-seat-evidence` (17 commits) and `seat-aware-ingestion` (2 commits) exist only as local worktrees under `eval-lab/.worktrees/`; another agent wrote them. Do not push or change them; mention them to Peter if relevant.
5. **Free ideas not yet done:** see "## What is open" in `docs/SUMMARY.md`. Prefer work that needs no model calls: tests and CI gaps, fork fixes, reviews, offline analyses of `runs/`.

## How to work

- At each new block of work, write the next 3 items into `docs/RUNLOG.md` (above "## Done") before starting, and add a dated entry under "## Done" when finished. Update the crucible lane log in `research-context/multi-agent/crucible-log-20261120.md` when other lanes should know something; that repo has other writers, so commit only your file and push without stashing.
- Verify every subagent or tool result yourself before you report it; report only checks you ran.
- Keep `docs/SUMMARY.md` current; it is the page Peter reads first.
