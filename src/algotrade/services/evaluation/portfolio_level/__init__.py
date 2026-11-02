"""The portfolio level's provider (ADR 0088, design 2.15, G15): the facts of a setup's own book of
open trades at a decision session, ``portfolio.<name>`` (``PORTFOLIO_FIELDS``). ``book.py`` is the
one pure computation, ``walk.py`` the in-order walk of decision sessions a setup that reads the
level needs, ``paper.py`` the paper record's book. Reads only the setup's own trades."""
