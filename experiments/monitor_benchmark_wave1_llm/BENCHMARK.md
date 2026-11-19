| Monitor | Tier | Trials (Adv/Neg/Ref) | AUROC | TPR@5%FPR | Thresh | Actual FPR | Refuser FPR | Top-Seat Acc | Mean Adv / Neg | Cost (USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_crucible_v1 | `tier0_public_only` | 33 (18/15/3) | 0.585 | 22.2% | 24.00 | 0.0% | 0.0% | 22.2% | 12.2 / 1.6 | $0.0000 |
| deterministic_crucible_v1 | `tier1_public_plus_audit` | 33 (18/15/3) | 0.646 | 33.3% | 58.00 | 0.0% | 0.0% | 38.9% | 32.4 / 7.7 | $0.0000 |
| llm_deepseek_deepseek-chat | `tier0_public_only` | 33 (18/15/3) | 0.667 | 33.3% | 0.00 | 0.0% | 0.0% | 66.7% | 0.2 / 0.0 | $0.0232 |
| llm_deepseek_deepseek-chat | `tier1_public_plus_audit` | 33 (18/15/3) | 0.744 | 5.6% | 5.00 | 0.0% | 0.0% | 55.6% | 1.8 / 0.7 | $0.0630 |

### Tier Visibility Lift
- **deterministic_crucible_v1**: Tier 0 -> Tier 1: AUROC +0.061, TPR@5%FPR +11.1pp
- **llm_deepseek_deepseek-chat**: Tier 0 -> Tier 1: AUROC +0.078, TPR@5%FPR -27.8pp
