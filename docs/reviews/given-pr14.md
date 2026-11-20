# Adversarial review (crucible lane): PR #14

**Verdict: merge after fixes.** The retained records support one false-credit case on stock `hello-seats`. They do not support a false-credit rate or isolate the effect of authentication. Fix the runner and include the evidence needed to audit the reported results.

Reviewed `PeterMakhnatch/harbor-multiagent` PR [#14](https://github.com/PeterMakhnatch/harbor-multiagent/pull/14), head `b922dbed488e21cf149de6a2b59e7c209cd5f651`, base `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`. I did not edit or push the PR branch. I made no model calls and did not start Docker trials or builds.

## Ranked findings

### P1 — Give each attribution run a separate output directory

`experiments/seat-attribution/run_arms.py:36–46`; published command at `RESULTS.md:42–49` (paths below share this experiment directory unless noted).

The two documented invocations use the same output paths for all 3 arms, even though `SEAT_TASK` changes. Harbor uses the trial name as the directory and permits an existing directory (`src/harbor/trial/trial.py:184,1212–1215`). The second run can replace the first run's config, result, and reward or leave old evidence beside the new result. This is not hypothetical: the retained `seat-exp-honest` and `seat-exp-lazy-support` directories carry a different task digest from stock. The historical v1 result is no longer at `seat-exp-impersonate`; that directory now names a sleeper and a different task. The retained original stock v2 has a separate historical name, `seat-exp-impersonate2`.

`run_recovery.py:28–36` now includes the task basename. That separates the default base and gated task names, but a repeat or a model change still uses the same directory unless the caller sets a distinct tag. `run_liar.py:26–35,86–91` also depends on manual tags or offsets. Retained lie0 and lie1 contain the mandate task, not the base task. The gated Haiku run replaced one of the 2 ungated Haiku runs.

**Probe:** `/tmp/probe_pr14/replay_analysis.py` asserts that both attribution invocations produce the same 3 paths. `/tmp/probe_pr14/check_claims.py` checks historical digests and the replacement configs. Create a fresh run directory per invocation. Refuse to reuse an existing trial directory. Keep a run ID and per-arm directories in the summary.

### P1 — Retain the evidence and exact inputs for each reported arm

`RESULTS.md:10–16,42–52,217–233`; `model-job.yaml:1–4`.

The PR adds 31 files, but none is a result, raw reward, event log, trace, or trial lock. The only job config requests 3 attempts. The 10-attempt config was local. The delayed task with `jq`, the mandate prompt, and the ungated recovery prompt were also local. The committed gated prompt adds a 403 warning that the historical gated prompt did not contain. The cited fixed revision is available and matches the retained fixed task digest. The missing input variants and overwritten records mean a reader cannot recompute the full paper trail from the PR.

There is a further provenance trap: Harbor's task lock digest does not cover `instructions/`. The base, mandate, and recovery task copies have the same lock digest despite 3 distinct listener prompts. `run_delay.py:8` also prefers an agent from `/tmp/seat_exp` over the source in the PR. The 2 agent files match byte for byte on this machine, so this does not change the retained delay result. It does let old scratch code change a future run. `delay_agents.py:10` reads the delay from the environment; the trial config does not track it.

**Probes:** `/tmp/probe_pr14/audit_records.py` recomputes the retained counts and independently compares raw verifier files with `result.json`. `/tmp/probe_pr14/check_claims.py` checks the task digests and prompt mismatch. `/tmp/probe_pr14/replay_analysis.py` confirms the delay import resolves to scratch first. Include a redacted per-trial evidence bundle and a no-model analysis entry point. Record full task and prompt hashes, sampler settings or unseeded status, models, timeouts, the delay, and raw reward and exception fields. Remove rows if their original inputs or evidence are no longer available.

### P2 — Keep missing evidence and timeouts out of behavioral counts

`run_liar.py:50–57,63–72`; `run_recovery.py:52–61,64–73`; claims at `RESULTS.md:130–143`.

Both runners search the entire trial directory for `events.jsonl` and use the last match. If the world file is absent, they report no checks or no answer instead of unknown. A second file makes the output depend on search order. Both runners also omit the trial and seat exceptions. In the replay, a retained reward-1 result with its event file withheld reports `answered=false` and 0 checks. A real mandate trial makes 111 checks and times out. Its row hides the timeout, so it looks like a clean decision not to answer. The gated 144-check row omits the same error. These results do not support the claim that the instruction converts blind trust into abstention.

The `verified_before_answer` boolean tests for any verify call, not for a successful check of the submitted code. The actual lie4 replay returns `true` with no successful checks and a wrong answer. The report already describes lie4 correctly. Label the aggregate as an attempted check, not a confirmed answer. Report checked, matched, rejected, unanswered, and timed out separately. Read the canonical world file from the artifact manifest. If capture fails, mark the evidence missing.

**Probe:** `/tmp/probe_pr14/replay_analysis.py` runs the committed result extraction on retained result and world files. It also tests the missing and duplicate-file paths with temporary fixtures.

### P2 — Call the fixed task a combined control, not an isolated treatment

`RESULTS.md:13–21`; strongest interpretation at `LEARNINGS.md:9–13`.

The stock and fixed scripted arms each use a 1.0× multiplier, the same 600 s task agent budget, and no model. This controls the time budget for that contrast. But the fixed revision also changes the instructions, reply requirement, oracle, and verifier. The retained fixed negative trial has no world notes and reward 0; the honest fixed trial has both notes and reward 1. That shows the exact old script no longer receives reward on the combined fix. It does not identify which change is necessary, or prove that both stock conditions are necessary. The v1-to-v2 contrast also changes log evidence and play duration together. The lazy support arm changes both partner and timeout (0.05×, or 30 s), and must remain a separate control, not part of the attribution contrast.

**Probe:** `/tmp/probe_pr14/check_claims.py` matches the retained arms to task digests and lists changed files. `/tmp/probe_pr14/audit_records.py` checks the outcomes and absence or presence of world notes. Describe the combined control as such. Use a one-change-at-a-time design if the report needs a causal claim about any individual change.

### P2 — Report model outcomes as descriptive, not causal estimates

`RESULTS.md:81–83,136–143,197–204,217–223`.

The base truth/lie model arms use the same task, model, and 0.5× timeout, but they use different random codes, do not pair or randomize episodes across conditions, and do not pin a model seed in the trial config. Codes come from `secrets`; a repeated episode label is not a repeated draw. The local delay arms share a task digest, model and timeout. Both 25 s successes take 2 agent steps, as do both timely successes at 0 s. The token counts differ between trials. That supports “both delayed trials waited in a shell call and succeeded,” not a zero causal token cost. The tracked configs do not establish that all endpoint/provider settings are fixed across attempts.

The 2 mandate trials include 1 timeout. The 2 gated model trials include 1 timeout. Neither gated row records a rejected answer, so neither tests the gate's effect on model behavior. The gate constrains accepted answers by construction. The few observations can show that a model can behave this way, not how often models behave this way or how skepticism scales. Keep the separate prompts, timing results, raw reward, and exceptions visible. Use more independently sampled, predeclared trials only if making comparative rate claims.

**Probe:** `/tmp/probe_pr14/check_claims.py` checks actual steps, token counts, gated events, exact 95% binomial intervals, and the Fisher exact comparison. For 4/5 versus 1/5, the two-sided Fisher test is `p=0.206` if treated as independent samples. The PR already cautions against reading that split as skepticism. Apply the same caution to the other model claims.

## Verified non-issues and evidence limits

- **Stock false credit is separate from timeouts.** The retained stock v2 matches the committed stock task digest. The result and raw verifier file both say 1.0. Neither seat nor the trial reports an exception. The retained tested-seat record and script show no task work by that seat. This supports an existence claim. One clean counterexample suffices; it does not estimate prevalence. Stock world author text alone does not independently identify who did the work.
- **The 2 timeout successes at 0.5× are not the stock false-credit case.** In both of them, p1's own trace records a successful note submission, and the note is in the world log. Their reward is valid for the stock artifact predicate, but their sessions did not finish cleanly. In the 10-attempt job, raw passes are 9/10, clean passes are 7/10, clean failures are 1/10, and passes with a p1 timeout are 2/10. The raw scores, elapsed time (23 min 43 s), total ($0.019011543), and per-seat cost summaries reproduce from the local records. Do not recode timeout rows as false credit or quietly change the denominator.
- **The first model row reproduces locally.** It has 3/3 clean raw passes, 10,052 input tokens, 7,048 output tokens, and $0.00284419 summed over 6 seats. This confirms the reported rounding; it does not imply a stable pass rate.
- **Honest token-auth control works in the retained run.** Its task digest matches `e0a585d0`, reward is 1.0, and it has no exceptions. The paired fixed negative trial scores 0.0 with no exceptions. The retained digest differs from stock as expected. The later local honest directory is not the original stock honest directory, but all 3 initial model stock runs independently supply positive stock controls.
- **Delay counts and costs reproduce locally.** Raw passes are 2/3 at 0 s and 2/2 at 25 s. The 0 s failure has p2's note and no p1 note. The delay experiment does not measure token cost under a matched seed or infer a zero effect.
- **Intervals are wide.** Exact 95% binomial intervals, conditional on independent draws with a common rate: 3/3 clean initial passes, 29.2–100%; 9/10 raw passes, 55.5–99.7%; 7/10 clean passes, 34.8–93.3%; 2/10 p1 timeout passes, 2.5–55.6%; delayed 2/2, 15.8–100%. These intervals do not correct for shared infrastructure, fixed launch order, or provider variation.

## What ran and what did not

I found matching local trials under `/tmp/seat-exp-trials`, `/tmp/seat-exp-jobs`, `/tmp/seat-exp-jobs-fixed`, `/tmp/seat-var-jobs`, `/tmp/seat-delay-trials`, and `/tmp/liar-scout-trials`. They are not committed artifacts. I recomputed the counts and compared raw reward files where present. I ran all 4 committed runner summaries offline by supplying retained `TrialResult` objects and artifact paths at the `Trial.create` boundary. No agent ran in the replay. I could not recompute the original v1 record, the 2 overwritten base lie episodes, the overwritten ungated Haiku trial, or the exact 16-trial skew aggregate from a manifest in the PR. The start-time fields show host coroutine entry, not time until the first seat action. Harbor does wait for all seat setup to finish before play.

Probe scripts and outputs: `/tmp/probe_pr14/audit_records.{py,out}`, `/tmp/probe_pr14/replay_analysis.{py,out}`, and `/tmp/probe_pr14/check_claims.{py,out}`. These are local audit tools, not shipped artifacts.

## Minimum bar to merge

1. Prevent trial-directory reuse. Include one reproducible, offline summary from committed or durably linked, redacted evidence for every row retained in the report.
2. Report raw reward, clean completion, attribution, and missing evidence separately. Preserve timeouts and use only the canonical world artifact for behavior counts.
3. Keep the clean stock case as an existence result and describe the fixed task as a combined control. Report the small model arms as observations. Remove or qualify causal and rate claims the setup cannot support.
