"""``/backtests``: saved backtest runs and one run's detail."""

from fastapi import APIRouter

from algotrade.services.explore import backtests
from algotrade_api.deps import Store
from algotrade_api.schemas.backtests import BacktestDetail, BacktestSummary

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("")
def runs(store: Store) -> list[BacktestSummary]:
    return [BacktestSummary.model_validate(r) for r in backtests.backtest_runs(store)]


@router.get("/{run_id}")
def detail(store: Store, run_id: str) -> BacktestDetail:
    return BacktestDetail.model_validate(backtests.backtest_detail(store, run_id))
