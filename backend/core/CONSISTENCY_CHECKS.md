# Monthly Evidence Consistency Checks

`backend/core/consistency_checks.py` provides deterministic, non-blocking checks over
monthly aggregate evidence. The checks are simple consistency heuristics on **monthly
aggregates**, not fraud detection. They cannot detect circular transfers or round-tripping;
that requires per-transaction data such as account-aggregator data. All thresholds are
product assumptions, not values learned from data.

## Flags

| Flag | Severity | Trigger |
| --- | --- | --- |
| `EVIDENCE_GAP` | MEDIUM | Calendar month(s) missing between the first and last evidence month. |
| `EVIDENCE_MALFORMED` | INFO | A `YYYY-MM` value was malformed and ignored. |
| `LATEST_MONTH_SPIKE` | MEDIUM | Latest inflow exceeds `SPIKE_RATIO` times the earlier median, with at least `MIN_MONTHS_FOR_SPIKE` months. |
| `CONSTANT_INFLOW` | INFO | At least `MIN_MONTHS_FOR_CONSTANT` positive months share an identical inflow. |
| `SENDER_DROP` | INFO | Latest unique-sender count is at most `SENDER_DROP_RATIO` times the earlier median, with at least `MIN_MONTHS_FOR_SENDERS` months of sender data. |

Malformed values, `None`, non-finite values, and negative values are ignored. Empty input
returns no flags. The checks never divide by zero and never return `HIGH` severity.
