# The dossier file (schema 1)

One TOML file per name, `var/dossiers/<ticker>/<YYYY-MM-DD>.toml` (git-ignored; the owner reviews the
diff against the previous file). Validated whole by `services/attributing/dossier.py`; one problem
stores nothing and the error lists them all.

```toml
schema = 1
ticker = "MU"                  # resolved through the import session's reference snapshot
reviewed_on = 2026-11-02       # the owner's review date; never after the import session

[[factor]]                     # at least one; every factor of the name, retired ones included
id = "hbm-pricing"             # slug: lower case, digits, - and _
kind = "commodity"             # peer | macro | regulation | commodity | litigation | product_cycle | financing | flows
status = "active"              # active (default) | retired: a retired factor is marked, never deleted
description = "One paragraph: why it moves the name, how to read it."

  [[factor.occurrence]]        # a dated occurrence: a past instance the factor explains, or the next date
  date = 2026-10-24
  label = "SK Hynix Q3 results"

  [[factor.watch]]             # undated: an expected window, ending on or after the import session
  expected_from = 2026-12-01
  expected_to = 2026-12-20
  label = "Korean export data"

[[attribution]]                # a reviewed cause of a big move (optional)
date = 2026-10-26              # the reaction session (a trading day, not after reviewed_on)
cause = "read_across"          # the closed taxonomy: services/attributing/taxonomy.py CAUSES
text = "SK Hynix guided HBM supply up."
confidence = 0.7               # 0..1
evidence = "SK Hynix Q3 call, 2026-10-24"   # required: what you read
evidence_ref = "https://..."   # optional link
```

**A dossier is the whole truth of its name.** An import stores every factor and occurrence listed;
a reader takes, per name, the rows of the latest import run among those with `known_from` (the
import session) on or before its session, so a date dropped from a later dossier disappears with it.
Reviewed attributions are `source = analyst_review` rows of `events/attribution` and beat a filing
or model row of the same move. A session before the import never sees any of it (ADR 0050
decision 3).
