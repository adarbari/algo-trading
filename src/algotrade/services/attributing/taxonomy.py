"""The cause taxonomy of a big move (ADR 0050 decision 5) and the 8-K item codes that name it.

The classes are closed: a filing attributes a move with high confidence and no model; the model
classes (headlines, EV4b) and the analyst review (the dossier) use the same set. An item that says
nothing about a cause (9.01 exhibits, 2.03 and 2.04 obligations, 7.01 alone is guidance) maps to no
class: no row is better than a guessed one."""

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
