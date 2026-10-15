"""Result-set labels (owner decision 2026-10-15). Three sets are kept side by side:

- PRE_REGISTERED: Gate 3 strategies as first specified (no charge guard).
- REVISED_GUARD_DEFECT: revised strategy whose guard carried the highest month-start peak
  forward (superseded; kept in *_guard_defect tables and docs/results/guard_defect/).
- REVISED: revised strategy with the guard corrected to start each month at the previous
  month's billed demand. This is the revised result.

The frozen strategy settings (config/revised_strategy.yaml) are the same for both revised
sets; only the guard's month start differs.
"""

PRE_REGISTERED = "pre-registered"
REVISED_GUARD_DEFECT = "revised strategy, post-hoc (guard defect)"
REVISED = "revised strategy, post-hoc (corrected guard)"
