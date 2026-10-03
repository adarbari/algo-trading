"""Leverage from ETF names (``classify.LeverageRules`` driven by ``config/site/universe.toml``).

Resolution order: curated override -> leverage the name states -> exclusions -> unleveraged;
anything else is UNKNOWN (``needs_review``). The names are real fund names from the
2026-10-02 review file (958 candidates before these rules)."""

import tomllib

import pandas as pd
import pytest

from algotrade.config.site.settings import UniverseSettings
from algotrade_ingestion.tasks.reference.classify import LeverageRules, leverage_flags
from tests.conftest import REPO_ROOT

# The committed rules, so a config edit that breaks a real name fails here.
SETTINGS = UniverseSettings.from_documents(
    tomllib.loads((REPO_ROOT / "config" / "site" / "universe.toml").read_text())
)
RULES = LeverageRules(SETTINGS)

PARSED = [
    # stated multiple next to a direction word or "Daily"; sign from Short / Bear / Inverse
    ("Direxion Daily AAPL Bull 2X ETF", 2.0),
    ("Direxion Daily AAPL Bear 1X ETF", -1.0),
    ("Direxion Daily S&P 500 High Beta Bull 3X ETF", 3.0),
    ("Direxion Daily 10-Yr Treasury Bear 3x Shrs", -3.0),
    ("Direxion Daily 20+ Year Treasury Bull 3X", 3.0),
    ("Direxion Financial Bear 3X ETF", -3.0),
    ("Direxion Daily Gold Miners Index Bull 2X ETF", 2.0),
    ("Direxion Daily Magnificent 7 Bear 1X ETF", -1.0),
    ("Tradr 2X Short AAOI Daily ETF", -2.0),
    ("Tradr 2X Long SMR Daily ETF", 2.0),
    ("Tradr 1.5X Short NVDA Daily ETF", -1.5),
    ("Tradr 1X Short Innovation Daily ETF", -1.0),
    ("Tradr 2X Long Innovation ETF", 2.0),
    ("Defiance Daily Target 2X Long NOK ETF", 2.0),
    ("Defiance Pure Space Daily 2X Strategy ETF", 2.0),
    ("Defiance 2X Daily Long Pure Quantum ETF", 2.0),
    ("GraniteShares 2x Long UBER Daily ETF", 2.0),
    ("GraniteShares 1.25x Long TSLA Daily ETF", 1.25),
    ("Leverage Shares 2X Long NVDA Daily ETF", 2.0),
    ("Leverage Shares 1X Short SK Hynix Daily ETF", -1.0),
    ("Leverage Shares 2X Short Sk Hynix Daily ETF", -2.0),
    ("T-REX 2X Long Tesla Daily Target ETF", 2.0),
    ("T-REX 2X Inverse CRWV Daily Target ETF", -2.0),
    ("Roundhill T-REX 2X Long DRAM Daily Target ETF", 2.0),
    ("Tuttle Capital Daily 2X Inverse Regional Banks ETF", -2.0),
    ("Corgi AAPL 2x Daily ETF", 2.0),
    ("Corgi U.S. Semiconductors 2x Daily ETF", 2.0),
    ("Teucrium 2x Daily Corn ETF", 2.0),
    ("USCF Daily Target 2X Copper Index ETF", 2.0),
    ("KraneShares 2x Long BABA Daily ETF", 2.0),
    ("Rareview 2x Bull Cryptocurrency & Precious Metals ETF", 2.0),
    ("Roundhill Daily 2X Long Magnificent Seven ETF", 2.0),
    ("21Shares 2x Long Dogecoin ETF", 2.0),
    ("2x Bitcoin ETF", 2.0),
    ("2x Long VIX Futures ETF", 2.0),
    ("-1x Short VIX Futures ETF", -1.0),
    ("Volatility Shares Trust XRP 2X ETF", 2.0),
    ("ETRACS Quarterly Pay 1.5X Leveraged Alerian MLP Index ETN", 1.5),
    ("MicroSectors Gold Miners -3X Inverse Leveraged ETNs", -3.0),
    ("MicroSectors Energy 3X Inverse Leveraged ETNs", -3.0),
    ("MicroSectors FANG & Innovation 3x Leveraged ETN", 3.0),
    ("MAX S&P 500 4X Leveraged ETNs due October 30, 2043", 4.0),
    ("MicroSectors U.S. Big Oil 3 Leveraged ETNs due February 17, 2045", 3.0),
    ("MicroSectors U.S. Big Banks -3 Inverse Leveraged ETNs due February 17, 2045", -3.0),
    # ProShares conventions: Ultra 2, UltraShort -2, UltraPro 3, UltraPro Short -3, Short -1
    ("ProShares Ultra Russell2000", 2.0),
    ("ProShares Ultra Bloomberg Crude Oil", 2.0),
    ("ProShares Ultra High Yield ETF", 2.0),
    ("ProShares Ultra Bitcoin ETF", 2.0),
    ("ProShares UltraShort Lehman 7-10 Year Treasury", -2.0),
    ("ProShares UltraShort Bloomberg Natural Gas", -2.0),
    ("ProShares UltraShort QQQ Mega", -2.0),
    ("ProShares UltraPro QQQ", 3.0),
    ("ProShares UltraPro Dow30", 3.0),
    ("UltraPro MidCap400", 3.0),
    ("ProShares UltraPro Short 20 Year Treasury", -3.0),
    ("UltraPro Short Dow30", -3.0),
    ("ProShares Short Russell2000", -1.0),
    ("ProShares Short High Yield", -1.0),
    ("ProShares Short Bitcoin ETF", -1.0),
]

UNLEVERAGED = [
    # no marker at all
    "SPDR S&P 500 ETF Trust",
    "iShares Core U.S. Aggregate Bond ETF",
    # short / ultra-short duration, term and maturity bonds
    "Franklin Ultra Short Bond ETF",
    "PGIM Short Duration High Yield ETF",
    "iShares Dynamic Short-Term Active ETF",
    "PIMCO Enhanced Short Maturity Active Exchange-Traded Fund",
    "Schwab Short-Term U.S. Treasury ETF",
    "Vanguard Ultra-Short Bond ETF",
    "Angel Oak UltraShort Income ETF",
    "F/m Ultrashort Treasury Inflation-Protected Security (TIPS) ETF",
    "State Street SPDR Portfolio Ultra Short T-Bill ETF",
    "Invesco Ultra Short Duration ETF",
    "VanEck Short Muni ETF",
    "VanEck Short High Yield Muni ETF",
    "MFS Active Short Muni Bond ETF",
    "Manager Directed Portfolios Twin Oak Short Horizon Absolute Return ETF",
    "VIX Short-Term Futures ETF",
    # buffers, put-writes, option / daily income, long-short equity, loans, branding
    "Innovator U.S. Equity Ultra Buffer ETF - June",
    "Innovator Equity Premium Income - Daily PutWrite ETF",
    "YieldMax Ultra Option Income Strategy ETF",
    "TappAlpha S&P 500 Growth & Daily Income ETF",
    "xETFs TSLA Daily Income ETF",
    "First Trust Long/Short Equity",
    "Harbor Long-Short Equity ETF",
    "State Street SPDR S&P Leveraged Loan ETF",
    "Invesco S&P Ultra Dividend Revenue ETF",
    "EA Bridgeway Ultra-Small Company Market ETF",
]

NEEDS_REVIEW = [
    "Ranger Equity Bear Bear ETF",  # bear fund, no stated leverage
    "AdvisorShares MSOS Daily Leveraged ETF",  # leveraged, multiple not in the name
    "Inverse VIX Short-Term Futures ETNs due March 22, 2045",  # "Inverse" left after exclusion
    "YieldMax Short N100 Option Income Strategy ETF",  # synthetic short exposure
    "YieldMax Ultra Short Option Income Strategy ETF",
    "IncomeSTKd 1x Bitcoin & 1x Gold Premium ETF",  # stacked exposures
    "Leverage Shares 100% TSLA AND 100% SPCX Daily ETF",
    "MicroSectors -3? Short Artificial Intelligence (AI) ETNs",  # garbled multiple
    "UPAR Ultra Risk Parity ETF",
    "Some Ultra Short Fund",  # "Ultra Short" without a bond word stays UNKNOWN
]


@pytest.mark.parametrize(("name", "leverage"), PARSED)
def test_leverage_parsed_from_the_name(name: str, leverage: float) -> None:
    assert RULES.resolve(name) == (leverage, "name_parsed")


@pytest.mark.parametrize("name", UNLEVERAGED)
def test_unleveraged_names_and_exclusions(name: str) -> None:
    assert RULES.resolve(name) == (1.0, "name_rule")


@pytest.mark.parametrize("name", NEEDS_REVIEW)
def test_marked_names_without_a_stated_leverage_need_review(name: str) -> None:
    assert RULES.resolve(name) == (None, "needs_review")


def test_ultra_and_short_only_follow_the_proshares_conventions_at_the_start() -> None:
    assert RULES.parse("UPAR Ultra Risk Parity ETF") is None
    assert RULES.parse("Ultra Short Fund") is None
    assert RULES.parse("Gotham Short Strategies ETF") is None


def test_exclusion_phrases_do_not_flip_the_sign() -> None:
    rules = LeverageRules(
        UniverseSettings(leverage_conventions=(), leverage_exclusions=SETTINGS.leverage_exclusions)
    )
    assert rules.parse("XYZ 2x Long VIX Short-Term Futures ETF") == 2.0
    assert rules.parse("XYZ 2x Long VIX Short Futures ETF") == -2.0


def test_empty_rule_lists_fail_closed() -> None:
    rules = LeverageRules(
        UniverseSettings(leverage_conventions=(), leverage_patterns=(), leverage_exclusions=())
    )
    assert rules.resolve("Franklin Ultra Short Bond ETF") == (None, "needs_review")
    assert rules.resolve("Plain Equity ETF") == (1.0, "name_rule")


def test_leverage_flags_resolution_order() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAPL", "SPY", "TQQQ", "UVXY", "SOXS", "FLUD", "HDGE"],
            "name": [
                "Apple Inc. - Common Stock",
                "SPDR S&P 500 ETF Trust",
                "ProShares UltraPro QQQ",
                "ProShares Ultra VIX Short Term Futures ETF",  # convention says 2: override wins
                "Direxion Daily Semiconductor Bear 3X ETF",
                "Franklin Ultra Short Bond ETF",
                "Ranger Equity Bear Bear ETF",
            ],
            "is_etf": [False, True, True, True, True, True, True],
        }
    )
    settings = UniverseSettings(
        overrides=(
            {"symbol": "TQQQ", "leverage": "3", "tracks": "Nasdaq-100"},
            {"symbol": "UVXY", "leverage": "1.5", "tracks": "VIX futures"},
            {"symbol": "SQQQ", "leverage": "-3"},
        )
    )
    flags = leverage_flags(frame, settings).set_index(frame["symbol"])
    got = {s: tuple(None if pd.isna(v) else v for v in row) for s, row in flags.iterrows()}
    assert got["AAPL"] == (False, False, 1.0, None, "not_etf")
    assert got["SPY"] == (False, False, 1.0, None, "name_rule")
    assert got["TQQQ"] == (True, False, 3.0, "Nasdaq-100", "override")
    assert got["UVXY"] == (True, False, 1.5, "VIX futures", "override")
    assert got["SOXS"] == (True, True, -3.0, None, "name_parsed")
    assert got["FLUD"] == (False, False, 1.0, None, "name_rule")
    assert got["HDGE"] == (None, None, None, None, "needs_review")  # UNKNOWN until curated


def test_committed_overrides_correct_the_vix_conventions() -> None:
    rows = (REPO_ROOT / "config" / "site" / "overrides" / "leveraged_etfs.csv").read_text()
    curated = {
        line.split(",")[0]: float(line.split(",")[1])
        for line in rows.splitlines()[1:]
        if line and not line.startswith("#")
    }
    assert curated["UVXY"] == 1.5 and RULES.parse("ProShares Ultra VIX Short Term Futures") == 2
    assert curated["SVXY"] == -0.5
