"""The filtering pass of the read model (ADR 0082 decision 3): a surface's filter definitions
resolved for a viewer (``definitions``), the masks of the viewer's inputs over a frame of rows
(``masks``) and what one masked pass tells (``facets``: matched, per filter ``removes``,
option counts and bins). Pure and deterministic; no loader adopts it yet."""
