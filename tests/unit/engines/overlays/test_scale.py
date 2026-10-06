"""ScaleByLabel (ADR 0049): multipliers per label, pauses, and the fail-closed unknown."""

import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.engines.overlays.overlay import Overlay, OverlayStep
from algotrade.engines.overlays.scale import UNKNOWN, ScaleByLabel

LABEL = "market.regime@v1.label"
MULTIPLIERS = {"CALM": 1.0, "CAUTION": 0.75, "STRESS": 0.5, "CRISIS": 0.25}
WEIGHTS = {"EQ:A": 0.6, "EQ:B": 0.4}


def scale(**kwargs: object) -> ScaleByLabel:
    return ScaleByLabel(LABEL, MULTIPLIERS, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("label", "factor", "reasons"),
    [
        ("CALM", 1.0, ()),
        ("CAUTION", 0.75, ("regime=CAUTION: x0.75",)),
        ("STRESS", 0.5, ("regime=STRESS: x0.5",)),
        ("CRISIS", 0.25, ("regime=CRISIS: x0.25",)),
    ],
)
def test_weights_scale_by_the_label_multiplier(
    label: str, factor: float, reasons: tuple[str, ...]
) -> None:
    step = scale().apply(WEIGHTS, {LABEL: label})
    assert step.weights == pytest.approx({i: w * factor for i, w in WEIGHTS.items()})
    assert step.reasons == reasons


def test_a_paused_label_scales_to_zero_with_its_reason() -> None:
    step = scale(pause_in=frozenset({"STRESS"})).apply(WEIGHTS, {LABEL: "STRESS"})
    assert step.weights == {"EQ:A": 0.0, "EQ:B": 0.0}
    assert step.reasons == ("regime=STRESS: paused",)


@pytest.mark.parametrize("label", [None, "STORM", 3.0])
def test_an_unknown_label_fails_closed(label: object) -> None:
    """Null or an unrecognised value is never read as CALM: the unknown multiplier (0)."""
    step = scale().apply(WEIGHTS, {LABEL: label})  # type: ignore[dict-item]
    assert step.weights == {"EQ:A": 0.0, "EQ:B": 0.0}
    assert step.reasons == (UNKNOWN,)
    half = scale(unknown_multiplier=0.5).apply(WEIGHTS, {LABEL: None})
    assert half.weights == pytest.approx({"EQ:A": 0.3, "EQ:B": 0.2})


def test_a_name_the_run_did_not_load_is_missing_data() -> None:
    with pytest.raises(MissingDataError, match=LABEL):
        scale().apply(WEIGHTS, {"market.other@v1.x": "CALM"})


def test_multipliers_must_be_fractions() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        ScaleByLabel(LABEL, {"CALM": 1.5})
    with pytest.raises(ValueError, match="unknown"):
        ScaleByLabel(LABEL, MULTIPLIERS, unknown_multiplier=-0.1)


def test_it_is_an_overlay_and_leaves_its_input_alone() -> None:
    overlay: Overlay = scale()
    weights = dict(WEIGHTS)
    step = overlay.apply(weights, {LABEL: "STRESS"})
    assert isinstance(step, OverlayStep) and weights == WEIGHTS
    assert overlay.apply(weights, {LABEL: "STRESS"}) == step  # deterministic
