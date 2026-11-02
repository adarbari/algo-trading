"""The option calculators (plan docs/ui/evening-desk-plan.md V11): read-only previews of figures
a trader types in (a contract they sold, shares they hold, a contract and count), priced from
exactly the request's session chain through ``services/read/options/session_inputs.py``. Never
stored or logged; the API serves them as body-only POSTs. Derived figures only: a vendor bid,
ask, last or size never leaves this folder (``pool.py`` is where the quote stops). Payoff maths
is ``quant/options/payoff.py``; a broker's margin rule (Reg-T) is here, not in ``quant/``."""
