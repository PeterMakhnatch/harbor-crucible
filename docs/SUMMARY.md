# Summary: what this is, what it measured, what is open

One page for orientation. Details in `FINDINGS.md`, `ARCHITECTURE.md`, `UPSTREAM-DEFECTS.md`, `RUNLOG.md`.

## What exists

- **`harbor-crucible`**, a suite built on `olamlabs/harbor-multiagent`: four native seat task families (17 variants), an audit-contract linter, a cross-seat causal timeline, a tiered monitor benchmark with bootstrap intervals, and an Eval Lab export.
- **Four draft PRs** on Peter's fork of the upstream repo: seat-attributed live logs (#12), seat error-policy overrides and order-invariant lock identity (#10), native seat regrade (#11), per-seat job statistics (#21). Two of them fix defects a lab hits on day two; the regrade round-trip is verified on a recorded trial with zero agent re-execution.
- **CI** that gates lint, formatting, tests, the audit contract of every variant, and a report smoke test.
- **Spend: about $1.00** of the $20 infrastructure cap. A four-seat episode costs about one cent.

## What it measured

106 real-model seat trials, 98 complete and integrity-labelled. Per family, because scales differ:

| Family | Pos / ctrl | AUROC, public chat | AUROC, + audit | Detection | Attribution |
|---|---:|---:|---|---:|---:|
| `supply-chain-sabotage` | 24 / 26 | 0.667 | **0.970 [0.913, 1.000]** | 87.5% | **95.8%** |
| `epistemic-crucible` | 12 / 18 | 0.917 | 0.917 [0.792, 1.000] | 83.3% | 83.3% |
| `reward-hack-contagion` | 12 / 6 | 0.500 | 0.500 | 0% | 0% |

**The headline: authenticated audit evidence takes sabotage attribution from 8.3% to 95.8%.** In the liar family the same audit evidence changes nothing, because chat already carries the signal. The reward-hack cell is unmeasurable because the world detects mechanisms in workspace state that never reached a commit, so its label and its evidence are different events.

Behaviour, three trials per condition unless noted:

| Finding | Result |
|---|---|
| Sabotage under a secret adversary | the adversarial seat committed sabotage in 23 of 24 completed trials |
| Cross-role reward-hack contagion | a planner seeds a test bypass, the coder implements it, the reviewer approves: 1 of 3 |
| Strict quarantine gate | blocked every delivery attempt |
| Turf war under incompatible goals | escalated in 1 of 3 blind conflicts, stood down or truced otherwise |
| Gullibility dose response | liar named 0/6 at no-liar, 3/6 at half, 5/6 at full; decision always correct (18/18) |
| Hidden profile, sharing mandated | team equals the solo ceiling, 3/3; the family tests nothing |
| Hidden profile, no sharing mandate | team drops to 1/3 while the solo ceiling stays 3/3, and the reference solution solves it |

## What failed, and is recorded as failing

- **Monitor v2** (claim-versus-audit text rules): AUROC 0.604 against 0.646 for v1. Four rules fire on honest behaviour that merely contains a matching word. Kept as the pre-registered negative result.
- **Pooled monitor analysis**: invalid, because the scales differ across families. Replaced by per-family reporting.
- **The "audit evidence lifts detection" claim**: it came from four timed-out trials and reverses on complete runs.
- **The reward-hack family's Tier-1 detection from model trials**: Wave 1's audit log held file names, not code. Fixed in the world; only the oracle corpus has been re-measured.
- **Gemini as a second model**: the key returns HTTP 402 (prepayment credits depleted). Model-specificity is unanswered.

## What is open

1. **Per-file content in the reward-hack log.** The world detects a mechanism in files the audit log never records, so the family cannot support a monitor claim. Record bounded per-file content for committed work.
2. **A second model family.** Qwen through OpenRouter works but costs $0.17 per trial, which the second-model cap forbids.
3. **Reward-hack model trials with the fixed evidence.** The world now records submitted code as audited action; no model trial has been scored since.
4. **Threshold stability of any LLM judge at this sample size.** With 14 controls its detection rate ranges from 7% to 60% under resampling, so only AUROC is usable.
