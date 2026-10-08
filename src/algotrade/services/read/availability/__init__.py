"""Why a fact is not available, and who may know (ADR 0056): the public vocabulary
(``Unavailable``: a kind, the features it hides and the Guide term that explains the kind;
``cause.py``) and the admin-only chain behind it (``Cause``: source -> step -> table -> features,
expanded from stored facts by ``explain.py``). A trader sees the kind and the feature names;
the chain is served only to admins, by the server, never filtered in the browser."""
