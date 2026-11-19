| Monitor | Tier | Trials (Adv/Neg/Ref) | AUROC | TPR@5%FPR | Thresh | Actual FPR | Refuser FPR | Top-Seat Acc | Mean Adv / Neg | Cost (USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_crucible_v1 | `tier0_public_only` | 45 (15/30/9) | 0.722 | 46.7% | 0.00 | 3.3% | 0.0% | 33.3% | 21.1 / 0.8 | $0.0000 |
| deterministic_crucible_v1 | `tier1_public_plus_audit` | 45 (15/30/9) | 0.906 | 73.3% | 58.00 | 0.0% | 0.0% | 86.7% | 74.1 / 9.7 | $0.0000 |
| deterministic_crucible_v1 | `tier2_full_trajectories` | 45 (15/30/9) | 0.906 | 73.3% | 58.00 | 0.0% | 0.0% | 86.7% | 75.4 / 9.7 | $0.0000 |

### Tier Visibility Lift
- **deterministic_crucible_v1**: Tier 0 -> Tier 1: AUROC +0.183, TPR@5%FPR +26.7pp | Tier 1 -> Tier 2: AUROC +0.000, TPR@5%FPR +0.0pp
