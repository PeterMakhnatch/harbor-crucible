# Re-verification — PR #21 `crucible/seat-job-stats` at `312069dc`

**Verdict: F1, F2, F3 remain fully open. Do not merge on the basis of this head.**
The only change since the reviewed head `b7e99d1` is one commit,
`312069dc` "fix(seats): read seat exceptions from exception_info only"
(+10/-16 in one file). It removes the dead `recorded_exceptions` branch
(one sub-part of F6) and changes nothing else. Every prior probe produces
byte-identical output on the new head.

Method: `gh pr view 21` confirms head `312069dc58ff…`, state OPEN.
No local checkout sits at that head (`harbor-multiagent` and
`harbor-multiagent-crucible` are at base `6aeb609e`, clean), so the head
was fetched read-only as a tarball to `/tmp/pr21src2`. The prior probes in
[probe_pr21.py](/tmp/probe_pr21.py) were re-run verbatim against the new
source ([probe_pr21_new.py](/tmp/probe_pr21_new.py), only the `sys.path`
line changed) and against the old snapshot `/tmp/pr21src`;
`diff` of the two outputs is empty ("OUTPUTS IDENTICAL"). The source
diff old→new is exactly the two dead-branch removals
(`_increment_seat_stats`, `_remove_seat_stats`). The PR's own tests still
pass: 7 passed in `tests/unit/models/test_job_stats_seats.py`.

## Per-finding verdicts

### F1 [P0] Retry `_remove_seat_stats` deletes live seat data — OPEN (unfixed)
Code unchanged: `n_trials` still gated on `reward_valid`
([result.py:228](/tmp/pr21src2/src/harbor/models/job/result.py:228)) and the
pop condition is still `n_trials == 0 and n_errors == 0`
([result.py:380](/tmp/pr21src2/src/harbor/models/job/result.py:380)).
Probe 6 re-run, observed: `6 before remove: job tokens= 200 seat tokens= 200
seat n_trials= 0` → `6 after remove(t2): job tokens= 100 seat_stats= []
sum seats= 0`. A reward-invalid trial's removal still discards the other
live trial's spend from `seat_stats` while job totals keep it.

### F2 [P0] Bare seat-name key collides across trials — OPEN (unfixed)
Code unchanged: `seat_stats` keyed by seat string alone
([result.py:66](/tmp/pr21src2/src/harbor/models/job/result.py:66),
[result.py:217](/tmp/pr21src2/src/harbor/models/job/result.py:217));
`under_test` still first-write-wins via `setdefault`,
`agent_name`/`model_name` still last-write-wins
([result.py:224](/tmp/pr21src2/src/harbor/models/job/result.py:224)).
Probe 2 re-run, observed: `2 collision: keys= ['main'] model= claude-B
under_test= True n_trials= 2 tokens= 200` across `gpt-A`/under-test/`dsA`
and `claude-B`/supporting/`dsB`. A model that never ran under test still
gets the under-test row.

### F3 [P0] `usage_complete` wrong both ways and sticky — OPEN (unfixed)
Code unchanged: only `cost_usd` decides completeness
([result.py:247](/tmp/pr21src2/src/harbor/models/job/result.py:247));
`_remove_seat_stats` never restores it. Probes re-run, observed:
- `3 cost-only: usage_complete= True n_input= None` (tokens missing, still "complete").
- `10 mixed completeness: seat n_input= 100 usage_complete= True n_trials= 2` (partial token sum presented as complete).
- `3b tokens-only: usage_complete= False n_input= 100` (known tokens masked as `unknown` in the CLI).
- `5 after remove(bad): a.usage_complete= False` (sticky: retracting the setup-failed trial does not heal the seat).

### F4 [P1] Seat sum ≠ job totals in `compute_token_cost_totals` branches — OPEN
Untouched by the fix commit. Probe 4 re-run: `job n_input= 999 sum seats= 200`, unflagged.

### F5 [P1] Supporting and reward-less seats counted in `n_trials` — OPEN
Untouched. Probe 1 re-run: `supporting lee n_trials= 1 reward_stats= {} |
sum seat n_trials= 2 job completed= 1`.

### F6 [P1] `exception_stats` attribution — PARTLY FIXED
Fixed sub-part: the dead `hasattr(seat_result, "recorded_exceptions")`
branch is gone from both increment and remove; seat exceptions now read
`exception_info` only. Probe confirms the branch was dead
(`SeatResult has recorded_exceptions: False`), so behavior is unchanged —
this is a cleanup, not a behavior fix. Open sub-parts, re-observed:
- `7b trial-only exc: job n_errored= 1 sum seat n_errors= 0` (trial-level exceptions still attributed to no seat).
- `7 job n_errored= 1 sum seat n_errors= 2` (two seats, same type, still double-counted vs the job).

### F7 [P1] Reward attribution by exact seat name — OPEN
Untouched (convention, not addressed in code or docs by this commit).

## Summary

| Finding | Severity | Verdict at `312069dc` |
|---|---|---|
| F1 live seat data deleted on retry | P0 | Open |
| F2 bare seat-name key collision | P0 | Open |
| F3 `usage_complete` wrong/sticky | P0 | Open |
| F4 seat sum ≠ job totals | P1 | Open |
| F5 non-rewarded seats in `n_trials` | P1 | Open |
| F6 exception attribution | P1 | Partly (dead branch removed; zero/double counting open) |
| F7 reward-by-seat-name convention | P1 | Open |

Evidence: [probe_pr21_new.py](/tmp/probe_pr21_new.py),
[/tmp/probe_new_out.txt](/tmp/probe_new_out.txt) vs
[/tmp/probe_old_out.txt](/tmp/probe_old_out.txt) (identical),
[/tmp/pr21-312069dc.diff](/tmp/pr21-312069dc.diff), new source in
[/tmp/pr21src2](/tmp/pr21src2). No repository files were edited; no spend.
