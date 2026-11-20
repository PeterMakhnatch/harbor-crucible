# Eval Lab vs crucible: per-field agreement

Real data = primary + extended retained runs. Perturbation rows are synthetic
mutations of one primary trial under /tmp and are excluded from the real rate.

| field | primary | extended | real-data rate | perturbation |
|---|---:|---:|---:|---:|
| agent_model | 164/164 | 530/530 | 1.000 | 35/36 |
| cost_complete | 44/44 | 154/154 | 1.000 | 9/9 |
| cost_total_usd | 44/44 | 154/154 | 1.000 | 9/9 |
| cost_usd | 164/164 | 530/530 | 1.000 | 36/36 |
| crucible_export_vs_loader | 44/44 | 154/154 | 1.000 | 9/9 |
| evallab_export_vs_inspect | 164/164 | 530/530 | 1.000 | 0/0 |
| evallab_usage_mismatch_vs_atif | 164/164 | 530/530 | 1.000 | 35/36 |
| exception_type | 44/44 | 154/154 | 1.000 | 8/9 |
| is_timeout | 44/44 | 154/154 | 1.000 | 8/9 |
| n_cache_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| n_input_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| n_output_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| n_steps | 164/164 | 530/530 | 1.000 | 32/36 |
| parsed | 44/44 | 154/154 | 1.000 | 8/9 |
| reward_keys | 44/44 | 154/154 | 1.000 | 9/9 |
| reward_values | 44/44 | 154/154 | 1.000 | 9/9 |
| seat_exception_type | 164/164 | 530/530 | 1.000 | 36/36 |
| seat_present | 164/164 | 530/530 | 1.000 | 37/37 |
| seat_set | 44/44 | 154/154 | 1.000 | 9/9 |
| trajectory_present | 164/164 | 530/530 | 1.000 | 32/36 |
| trajectory_valid | 164/164 | 530/530 | 1.000 | 32/36 |

# Disagreements

| cohort | trial | scope | field | evallab | crucible | raw | matches_raw |
|---|---|---|---|---|---|---|---|
| perturbation | /tmp/crucible-evallab-perturb/exception_info_without_type | trial | exception_type | null | "" | null | evallab |
| perturbation | /tmp/crucible-evallab-perturb/exception_info_without_type | trial | is_timeout | null | false | null | evallab |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:builder | agent_model | null | "deepseek/deepseek-chat" | null | evallab |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:builder | n_steps | "<missing>" | 17 | 17 | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:builder | trajectory_present | null | true | true | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:builder | trajectory_valid | "<missing>" | "valid" | true | neither |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:refiner | n_steps | "<missing>" | 19 | 19 | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:refiner | trajectory_present | null | true | true | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:refiner | trajectory_valid | "<missing>" | "valid" | true | neither |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_a | n_steps | "<missing>" | 18 | 18 | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_a | trajectory_present | null | true | true | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_a | trajectory_valid | "<missing>" | "valid" | true | neither |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_b | n_steps | "<missing>" | 20 | 20 | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_b | trajectory_present | null | true | true | crucible |
| perturbation | /tmp/crucible-evallab-perturb/seat_result_dropped | seat:scout_b | trajectory_valid | "<missing>" | "valid" | true | neither |
| perturbation | /tmp/crucible-evallab-perturb/undeclared_seat_dir | trial | parsed | true | false | true | evallab |
| perturbation | /tmp/crucible-evallab-perturb/zero_usage | seat:builder | evallab_usage_mismatch_vs_atif | ["usage_mismatch:n_input_tokens", "usage_mismatch:n_cache_tokens", "usage_mismatch:n_output_tokens", "usage_mismatch:cost_usd"] | null | {"total_cached_tokens": 73216, "total_completion_tokens": 3707, "total_cost_usd": 0.003268848, "total_prompt_tokens": 78716, "total_steps": 17} | neither |
