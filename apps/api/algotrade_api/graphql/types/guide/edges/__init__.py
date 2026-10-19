"""GraphQL types of the Guide's Edges section (mirrors ``services/read/guide/edges``, ADR 0051):
``GuideEdgeIndex`` (the mechanism cards, the filters, the edges set aside), ``GuideMechanism``
(a mechanism's page with its edges as rows) and ``GuideEdgeEntry`` (one site edge's page); each
mirrors a read dataclass through one ``.of()``. Session-free and with no harness result."""
