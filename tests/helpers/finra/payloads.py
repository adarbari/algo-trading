"""Hand-built FINRA Query API payloads (JSON lists), in the field names the API answers with."""

import json


def short_interest(settlement: str = "2026-09-30") -> bytes:
    """Three symbols of one settlement date: a stock, an ETF and an OTC name with gaps."""

    def row(symbol: str, market: str, current: int, previous: int, adv: int, dtc: float) -> dict:
        return {
            "accountingYearMonthNumber": int(settlement.replace("-", "")),
            "symbolCode": symbol,
            "issueName": f"{symbol} issue",
            "issuerServicesGroupExchangeCode": market[:1],
            "marketClassCode": market,
            "currentShortPositionQuantity": current,
            "previousShortPositionQuantity": previous,
            "stockSplitFlag": None,
            "averageDailyVolumeQuantity": adv,
            "daysToCoverQuantity": dtc,
            "revisionFlag": None,
            "changePercent": round(100 * (current - previous) / previous, 2) if previous else None,
            "changePreviousNumber": current - previous,
            "settlementDate": settlement,
        }

    rows = [
        row("AAA", "NYSE", 5_240_309, 5_078_629, 2_950_874, 1.78),
        row("BBB", "NASDAQ", 100, 200, 0, 0.0),
        row("OTCX", "OTC", 7, 7, 3, 2.33),
    ]
    rows[2]["revisionFlag"] = "R"
    return json.dumps(rows).encode()


def short_volume(day: str = "2026-10-16") -> bytes:
    """AAA on two facilities (summed), BBB on one, and a blank symbol (dropped)."""

    def row(symbol: str, facility: str, short: int, exempt: int, total: int) -> dict:
        return {
            "tradeReportDate": day,
            "securitiesInformationProcessorSymbolIdentifier": symbol,
            "shortParQuantity": short,
            "shortExemptParQuantity": exempt,
            "totalParQuantity": total,
            "marketCode": "Q",
            "reportingFacilityCode": facility,
        }

    rows = [
        row("AAA", "NQTRF", 400, 5, 1000),
        row("AAA", "NYTRF", 100, 0, 500),
        row("BBB", "ADF", 10, 0, 40),
        row("", "ADF", 1, 0, 1),
    ]
    return json.dumps(rows).encode()
