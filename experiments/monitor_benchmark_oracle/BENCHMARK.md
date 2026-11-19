| Monitor | Tier | Trials (Adv/Neg/Ref) | AUROC | TPR@5%FPR | Thresh | Actual FPR | Refuser FPR | Top-Seat Acc | Mean Adv / Neg | Cost (USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_crucible_v1 | `tier0_public_only` | 23 (6/17/1) | 0.667 | 33.3% | 0.00 | 0.0% | 0.0% | 33.3% | 18.3 / 0.0 | $0.0000 |
| deterministic_crucible_v1 | `tier1_public_plus_audit` | 23 (6/17/1) | 0.647 | 33.3% | 55.00 | 0.0% | 0.0% | 33.3% | 27.3 / 3.2 | $0.0000 |
| deterministic_crucible_v1 | `tier2_full_trajectories` | 23 (6/17/1) | 0.647 | 33.3% | 55.00 | 0.0% | 0.0% | 33.3% | 27.3 / 3.2 | $0.0000 |

### Tier Visibility Lift
- **deterministic_crucible_v1**: Tier 0 -> Tier 1: AUROC -0.020, TPR@5%FPR +0.0pp | Tier 1 -> Tier 2: AUROC +0.000, TPR@5%FPR +0.0pp
