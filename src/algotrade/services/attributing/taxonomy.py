"""The cause taxonomy of a big move (ADR 0050 decision 5) and the 8-K item codes that name it.

The classes are closed: a filing attributes a move with high confidence and no model; the model
classes (headlines, EV4b) and the analyst review (the dossier) use the same set. An item that says
nothing about a cause (9.01 exhibits, 2.03 and 2.04 obligations) maps to no class: no row is better
than a guessed one. 7.01 (Reg FD: guidance, an investor day) and 8.01 (other events) are named but
carry a lower confidence."""

RESULTS, AGREEMENT, MANAGEMENT, GUIDANCE = "results", "agreement", "management", "guidance"
OTHER_EVENT, ACQUISITION, RESTATEMENT, DELISTING = (
    "other_event",
    "acquisition",
    "restatement",
    "delisting",
)
# classes only the model or the analyst names (no 8-K item says them)
LITIGATION, ANALYST_ACTION, REGULATION, READ_ACROSS = (
    "litigation",
    "analyst_action",
    "regulation",
    "read_across",
)
PRODUCT, SHORT_REPORT, OTHER = "product", "short_report", "other"

CAUSES = (
    RESULTS, AGREEMENT, MANAGEMENT, GUIDANCE, OTHER_EVENT, ACQUISITION, RESTATEMENT, DELISTING,
    LITIGATION, ANALYST_ACTION, REGULATION, READ_ACROSS, PRODUCT, SHORT_REPORT, OTHER,
)  # fmt: skip

# 8-K item -> cause class (the plan's section 4.5)
ITEM_CLASS: dict[str, str] = {
    "2.02": RESULTS,
    "1.01": AGREEMENT,
    "1.02": AGREEMENT,
    "5.02": MANAGEMENT,
    "7.01": GUIDANCE,
    "8.01": OTHER_EVENT,
    "2.01": ACQUISITION,
    "4.02": RESTATEMENT,
    "3.01": DELISTING,
}
# confidence of an attribution from one class of 8-K item: a restatement, a delisting notice, an
# acquisition or a results release names its cause; an agreement or a management change usually
# does; Reg FD (7.01) and "other events" (8.01) are catch-alls a move may not be about
CONFIDENCE: dict[str, float] = {
    RESTATEMENT: 0.9, DELISTING: 0.9, ACQUISITION: 0.9, RESULTS: 0.9,
    AGREEMENT: 0.8, MANAGEMENT: 0.8, GUIDANCE: 0.6, OTHER_EVENT: 0.6,
}  # fmt: skip
# which class names a filing with several: the most specific cause first
PRIORITY = (
    RESTATEMENT,
    DELISTING,
    ACQUISITION,
    RESULTS,
    AGREEMENT,
    MANAGEMENT,
    GUIDANCE,
    OTHER_EVENT,
)
