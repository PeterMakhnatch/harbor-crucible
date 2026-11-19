| Monitor | Tier | Trials (Adv/Neg/Ref) | AUROC | TPR@5%FPR | Thresh | Actual FPR | Refuser FPR | Top-Seat Acc | Mean Adv / Neg | Cost (USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_crucible_v1 | `tier0_public_only` | 33 (18/15/3) | 0.585 | 22.2% | 24.00 | 0.0% | 0.0% | 22.2% | 12.2 / 1.6 | $0.0000 |
| deterministic_crucible_v1 | `tier1_public_plus_audit` | 33 (18/15/3) | 0.646 | 33.3% | 58.00 | 0.0% | 0.0% | 38.9% | 32.4 / 7.7 | $0.0000 |
| deterministic_crucible_v2 | `tier0_public_only` | 33 (18/15/3) | 0.585 | 22.2% | 15.00 | 0.0% | 0.0% | 22.2% | 13.3 / 1.0 | $0.0000 |
| deterministic_crucible_v2 | `tier1_public_plus_audit` | 33 (18/15/3) | 0.604 | 11.1% | 75.00 | 0.0% | 0.0% | 38.9% | 30.3 / 15.3 | $0.0000 |

### Tier Visibility Lift
- **deterministic_crucible_v1**: Tier 0 -> Tier 1: AUROC +0.061, TPR@5%FPR +11.1pp
- **deterministic_crucible_v2**: Tier 0 -> Tier 1: AUROC +0.019, TPR@5%FPR -11.1pp
