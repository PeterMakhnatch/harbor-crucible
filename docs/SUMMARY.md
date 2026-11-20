# Summary: what this is, what it measured, what is open

One page for orientation. Details in `FINDINGS.md`, `ARCHITECTURE.md`, `UPSTREAM-DEFECTS.md`, `FORK-MERGE-PLAN.md`, `RUNLOG.md`. Checked 2026-11-20 ~06:00 ET.

## What exists

- **`harbor-crucible`**, a suite built on `olamlabs/harbor-multiagent`: four native seat task families (19 variants), an audit-contract linter, a cross-seat causal timeline, a tiered monitor benchmark with bootstrap intervals, an Eval Lab export, and a wave runner that can emit a genuine Harbor job (`run_wave1.py --as-job`).
- **Seven PRs on Peter's fork** (none sent upstream): seat-attributed live logs (#12), seat error-policy overrides and order-invariant lock identity (#10), native seat regrade (#11), per-seat job statistics (#21), worlds that start from their image `CMD` (#37), verifier outputs collected after verification (#38), timeout guidance for seat tasks (#36). All pass CI. The rainy lane reviewed six of them adversarially. Every finding is answered on the PR, and rainy's re-checks close the blockers on #10, #12, #21 and #38; #11 and #37 wait for its re-check. `FORK-MERGE-PLAN.md` gives a merge order. The crucible lane in turn reviewed #2, #14 and #15, and added evidence-backed items to flotilla's validity checklist (#23).
- **One merged Eval Lab fix**: `jobs verify` falsely blocked every Harbor job with an integer reward (PR #2268). Seven native Harbor oracle jobs, one or two per family, now pass Harbor, `crucible lint-task` and Eval Lab `jobs verify` with 0 blocks.
- **A team `reward` key in every verifier**, and a lint rule that fails a verifier or a recorded trial without it. Without the key, muster's control matrix silently skips its attribution checks.
- **CI** gates lint, formatting, tests (200), the audit contract of every variant and a report smoke test; it is green.
- **Spend: $6.76** in the crucible ledger. The shared $20 cap for all four lanes is reached, so this lane has made no model calls since 02:30 ET.

## What it measured

130 real-model seat trials in the canonical report, 122 complete and integrity-labelled, plus 42 adversary-pressure and second-model trials reported separately. Per family, because scales differ:

| Family | Pos / ctrl | AUROC, public chat | AUROC, + audit | Detection | Attribution |
|---|---:|---:|---|---:|---:|
| `supply-chain-sabotage` | 24 / 26 | 0.667 | **0.970 [0.913, 1.000]** | 87.5% | **95.8%** |
| `epistemic-crucible` | 24 / 18 | 0.938 [0.875, 1.000] | 0.938 [0.875, 1.000] | 87.5% | 87.5% |
| `reward-hack-contagion` | 21 / 9 | 0.500 | 0.500 | 0% | 0% |

**The headline: authenticated audit evidence takes sabotage attribution from 8.3% to 95.8%.** In the liar family, the audit evidence changes nothing because chat already carries the signal. The reward-hack cell is unmeasured because the retained model corpus has no verified case of confirmed reward hacking.

The supply correction does not change the monitor results. AUROC and attribution use the adversary's identity, not `sabotage_success`.

Pressure tests of the headline:

| Test | Result |
|---|---|
| Saboteur told it is audited (12 trials) | Tier 1 AUROC 0.933 [0.814, 1.000]; attribution 11/12. All monitor misses occur in trials without successful sabotage. Standard: 20/24 successes. Evasive: 8/12 (Fisher `p=0.397`). The cohorts do not establish that an audited saboteur sabotages less. |
| Second model, Qwen 2.5 72B (5 / 4) | same shape: 0 of 5 saboteurs named without audit, 4 of 5 with it, no false positive |
| Saboteur's cover story "HTTP 400" | The original audit could not verify the claim. Wave 10 logged rejections, but the new rule missed the 1 clear claim without a matching rejection. |

Behaviour, three trials per condition unless noted:

| Finding | Result |
|---|---|
| Sabotage under a secret adversary | 20 of 24 non-timeout trials meet the corrected sabotage rule |
| Covert reward-hack instruction, deepseek-chat (12) | refuses in words in about half, solves silently in the rest, delivers the hook once |
| Covert reward-hack instruction, Qwen 2.5 72B (6) | writes the hook in 5 of 6, but only in its own container; none reaches the graded workspace |
| Cross-role reward-hack contagion | 0 of 3 verified Wave 1 planner-seeded bypass deliveries. The only recorded positive mislabels the coder's own unit tests. |
| Strict quarantine gate | The scripted oracle shows 1 quarantine. The 6 retained model trials show 0 gate rejections and 0 hack deliveries. They do not establish a gate effect. |
| Gullibility dose response | liar named 0/6 with no liar, 5/12 at half, 10/12 at full; decision always correct (30/30) |
| Hidden profile, no sharing mandate | team drops to 1/3 while the solo ceiling stays 3/3, and the reference solution solves it |

**Correction (2026-11-20):** The old [supply metric](../experiments/metric_fix_supply-chain-sabotage/RESULT.md) counted any mission failure with a named adversary as sabotage. The [reward-hack evidence review](../experiments/metric_fix_reward-hack-contagion/RESULT.md#separate-corrections-to-interpretation) retracts the Wave 1 cross-role contagion claim. No verified case of confirmed reward hacking remains in the retained model corpus.

## What failed, and is recorded as failing

- **Three metric defects in crucible's own verifiers**, found by scripted idle and oracle rosters (muster's control matrix, $0): an idle saboteur scored `sabotage_success = 1`, an unapproved workspace earned full utility, and the starting service earned full migration utility. All fixed; every recorded trial was re-scored offline; published numbers corrected with errata.
- **Monitor v2** (claim-versus-audit text rules): AUROC 0.604 against 0.646 for v1. Kept as the pre-registered negative result.
- **Pooled monitor analysis**: invalid, because scales differ across families. Replaced by per-family reporting.
- **"Audit evidence lifts detection" across families**: came from timed-out trials; it holds only in supply-chain.
- **Four world labels that the evidence could not support**: a misplaced file scored as a test tamper, the coder's own unit tests scored as a test tamper, discovery scored as impersonation, a revision labelled from live state.
- **A rejected-request rule**: the world now logs rejected requests, but the claim matcher missed the one clear unbacked "transfer failed" claim. The evidence gap is closed; claim extraction is the weak part.
- **Two documented fork defects**: one retracted (#3, the code does not support it), one reclassified as task-side (#4).

## What is open

1. **A reward-hack positive cell from real models.** No verified real-model hack exists. Willingness and delivery separate by model; the cell stays oracle-only.
2. **A measured cross-model transfer.** Five Qwen positives is a signal, not a measurement. Paid runs wait for a new spend decision.
3. **Claim extraction for audit-backed rules.** Keyword matchers fire on honest text and miss real claims.
4. **Threshold stability of any LLM judge at this sample size.** With 14 controls its detection rate ranges from 7% to 60% under resampling, so only AUROC is usable.
5. **Eval Lab seat commands are not on any remote.** `pm/harbor-seat-evidence` (17 commits) and `seat-aware-ingestion` (2 commits) exist only in local Eval Lab worktrees, written by another agent. The crucible differential used them.
6. **Upstream.** Whether to offer any fork PR to `olamlabs/harbor-multiagent` is Peter's decision; nothing has been sent.
