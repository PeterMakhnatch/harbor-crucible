# Summary: what this is, what it measured, what is open

One page for orientation. Details in `FINDINGS.md`, `ARCHITECTURE.md`, `UPSTREAM-DEFECTS.md`, `RUNLOG.md`. Checked 2026-11-20 ~01:00 ET.

## What exists

- **`harbor-crucible`**, a suite built on `olamlabs/harbor-multiagent`: four native seat task families (19 variants), an audit-contract linter, a cross-seat causal timeline, a tiered monitor benchmark with bootstrap intervals, an Eval Lab export, and a wave runner that can emit a genuine Harbor job (`run_wave1.py --as-job`).
- **Seven PRs on Peter's fork** (none sent upstream): seat-attributed live logs (#12), seat error-policy overrides and order-invariant lock identity (#10), native seat regrade (#11), per-seat job statistics (#21), worlds that start from their image `CMD` (#37), verifier outputs collected after verification (#38), timeout guidance for seat tasks (#36). All pass CI. Five had adversarial reviews from the rainy lane; each finding is answered on the PR and the reviewer's probes pass on the new heads. The crucible lane in turn reviewed #2, #14 and #15.
- **One merged Eval Lab fix**: `jobs verify` falsely blocked every Harbor job with an integer reward (PR #2268).
- **CI** gates lint, formatting, tests, the audit contract of every variant and a report smoke test; it is green.
- **Spend: $6.76** of the $20 infrastructure cap.

## What it measured

130 real-model seat trials in the canonical report, 122 complete and integrity-labelled, plus 42 adversary-pressure and second-model trials reported separately. Per family, because scales differ:

| Family | Pos / ctrl | AUROC, public chat | AUROC, + audit | Detection | Attribution |
|---|---:|---:|---|---:|---:|
| `supply-chain-sabotage` | 24 / 26 | 0.667 | **0.970 [0.913, 1.000]** | 87.5% | **95.8%** |
| `epistemic-crucible` | 24 / 18 | 0.938 [0.875, 1.000] | 0.938 [0.875, 1.000] | 87.5% | 87.5% |
| `reward-hack-contagion` | 21 / 9 | 0.500 | 0.500 | 0% | 0% |

**The headline: authenticated audit evidence takes sabotage attribution from 8.3% to 95.8%.** In the liar family the same audit evidence changes nothing, because chat already carries the signal. The reward-hack cell is unmeasured because real models rarely deliver a hack (below).

Pressure tests of the headline:

| Test | Result |
|---|---|
| Saboteur told it is audited (12 trials) | audit-tier AUROC 0.933 [0.814, 1.000], attribution 11/12: the monitor holds. Sabotage itself falls from 23/24 to 8/12 (p=0.034). Every miss was a failed sabotage. |
| Second model, Qwen 2.5 72B (5 / 4) | same shape: 0 of 5 saboteurs named without audit, 4 of 5 with it, no false positive |
| Saboteur's cover story "HTTP 400" | could not be disproved: the world did not log rejected requests. Fix and re-run in progress. |

Behaviour, three trials per condition unless noted:

| Finding | Result |
|---|---|
| Sabotage under a secret adversary | committed in 23 of 24 completed trials |
| Covert reward-hack instruction, deepseek-chat (12) | refuses in words in about half, solves silently in the rest, delivers the hook once |
| Covert reward-hack instruction, Qwen 2.5 72B (6) | writes the hook in 5 of 6, but only in its own container; none reaches the graded workspace |
| Cross-role reward-hack contagion | a planner seeds a test bypass, the coder implements it, the reviewer approves: 1 of 3 |
| Strict quarantine gate | blocked every delivery attempt |
| Gullibility dose response | liar named 0/6 with no liar, 5/12 at half, 10/12 at full; decision always correct (30/30) |
| Hidden profile, no sharing mandate | team drops to 1/3 while the solo ceiling stays 3/3, and the reference solution solves it |

## What failed, and is recorded as failing

- **Monitor v2** (claim-versus-audit text rules): AUROC 0.604 against 0.646 for v1. Kept as the pre-registered negative result.
- **Pooled monitor analysis**: invalid, because scales differ across families. Replaced by per-family reporting.
- **"Audit evidence lifts detection" across families**: came from timed-out trials; it holds only in supply-chain.
- **Three world labels that the evidence could not support**: a misplaced file scored as a test tamper, discovery scored as impersonation, a revision labelled from live state. All fixed with tests.
- **Two documented fork defects**: one retracted (#3, the code does not support it), one reclassified as task-side (#4).

## What is open

1. **A reward-hack positive cell from real models.** Willingness and delivery separate by model; a model that both complies and routes the hook through the world API is needed, or the cell stays oracle-only.
2. **A measured cross-model transfer.** Five Qwen positives is a signal, not a measurement.
3. **Rejected-request logging** in the supply world, and whether it closes the evasive saboteur's last escape.
4. **Threshold stability of any LLM judge at this sample size.** With 14 controls its detection rate ranges from 7% to 60% under resampling, so only AUROC is usable.
