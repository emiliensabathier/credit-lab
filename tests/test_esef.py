import json

import pandas as pd
import pytest

from clab.data import esef
from clab.data.loader import CompanyData
from clab.errors import CreditLabError
from clab.universe import UNIVERSE
from tests.fixtures import frozen

FY = {year: pd.Timestamp(f"{year}-12-31") for year in range(2019, 2026)}


def _fact(concept: str, period: str, value, **extra) -> dict:
    dims = {
        "concept": f"ifrs-full:{concept}", "entity": "lei:X", "period": period,
        "unit": "iso4217:EUR",
    }
    return {"value": str(value), "dimensions": {**dims, **extra}}


def _payload(*facts: dict) -> dict:
    return {"facts": {f"f{i}": fact for i, fact in enumerate(facts)}}


def test_instant_periods_are_shifted_back_to_the_fiscal_year_end() -> None:
    facts = esef.parse(_payload(_fact("Assets", "2022-01-01T00:00:00", 100)))

    assert facts == {FY[2021]: {"ifrs-full:Assets": 100.0}}


def test_durations_close_on_the_day_before_their_end_stamp() -> None:
    period = "2021-01-01T00:00:00/2022-01-01T00:00:00"
    facts = esef.parse(_payload(_fact("ProfitLossAttributableToOwnersOfParent", period, -7)))

    assert facts == {FY[2021]: {"ifrs-full:ProfitLossAttributableToOwnersOfParent": -7.0}}


def test_dimensional_non_numeric_and_unread_facts_are_skipped() -> None:
    stamp = "2022-01-01T00:00:00"
    facts = esef.parse(
        _payload(
            _fact("Assets", stamp, 100),
            _fact("Assets", stamp, 40, **{"ifrs-full:SegmentsAxis": "seg:Retail"}),
            _fact("Assets", stamp, None),
            _fact("Revenue", stamp, 5),
        )
    )

    assert facts == {FY[2021]: {"ifrs-full:Assets": 100.0}}


def test_a_candidate_sums_plus_terms_and_needs_every_minus_term() -> None:
    candidate = esef.Candidate("x", ("A", "B"), ("C",))
    p = esef.IFRS

    assert candidate.value({p + "A": 5.0, p + "C": 1.0}) == 4.0
    assert candidate.value({p + "A": 5.0, p + "B": 2.0, p + "C": 1.0}) == 6.0
    assert candidate.value({p + "A": 5.0}) is None
    assert candidate.value({p + "C": 1.0}) is None


def test_a_years_own_report_wins_over_the_next_reports_comparative() -> None:
    a = "ifrs-full:Assets"
    filings = {
        FY[2021]: {FY[2021]: {a: 100.0}, FY[2020]: {a: 90.0}},
        FY[2022]: {FY[2022]: {a: 120.0}, FY[2021]: {a: 103.0, "ifrs-full:Equity": 1.0}},
    }

    merged = esef.merge(filings)

    assert merged[FY[2021]] == {a: 100.0, "ifrs-full:Equity": 1.0}
    assert merged[FY[2020]] == {a: 90.0}
    assert merged[FY[2022]] == {a: 120.0}


def test_restatements_count_comparatives_that_moved_beyond_the_threshold() -> None:
    a, e = "ifrs-full:Assets", "ifrs-full:Equity"
    filings = {
        FY[2021]: {FY[2021]: {a: 100.0, e: 50.0}},
        FY[2022]: {FY[2022]: {a: 1.0}, FY[2021]: {a: 101.0, e: 60.0}},
    }

    assert esef.restatements(filings) == (1, 2)


def _company_data(balance: dict, income: dict | None = None) -> CompanyData:
    def frame(rows: dict) -> pd.DataFrame:
        return pd.DataFrame(rows).T.reindex(columns=[FY[2024], FY[2023], FY[2022]])

    return CompanyData(
        UNIVERSE[0],
        frame(balance),
        frame(income or {"Net Income": {FY[2022]: 1.0}}),
        frame({"Operating Cash Flow": {FY[2022]: 1.0}}),
        pd.Series(dtype=float),
    )


def _facts(**years: dict) -> esef.Facts:
    return {FY[int(y[2:])]: {esef.IFRS + k: v for k, v in f.items()} for y, f in years.items()}


def test_a_matching_line_is_extended_to_the_years_yahoo_lacks_only() -> None:
    data = _company_data({"Total Assets": {FY[2022]: 100.0, FY[2023]: 110.0, FY[2024]: 120.0}})
    facts = _facts(
        fy2020={"Assets": 80.0}, fy2021={"Assets": 90.0},
        fy2022={"Assets": 101.0}, fy2023={"Assets": 110.0},
    )

    result = esef.extend(data, facts)

    row = result.data.balance_sheet.loc["Total Assets"]
    assert row[FY[2020]] == 80.0 and row[FY[2021]] == 90.0
    assert row[FY[2022]] == 100.0  # Yahoo's figure is kept, not ESEF's 101
    assert result.chosen["Total Assets"] == "Assets"
    assert result.added_years["Total Assets"] == [FY[2020], FY[2021]]
    assert list(result.data.balance_sheet.columns) == sorted(row.index, reverse=True)


def test_a_line_no_candidate_reproduces_is_left_alone() -> None:
    data = _company_data({"Total Assets": {FY[2022]: 100.0, FY[2023]: 110.0}})
    facts = _facts(fy2021={"Assets": 90.0}, fy2022={"Assets": 150.0})

    result = esef.extend(data, facts)

    assert result.chosen["Total Assets"] is None
    assert FY[2021] not in result.data.balance_sheet.dropna(axis=1, how="all").columns
    assert "Total Assets" not in result.added_years


def test_the_first_candidate_that_matches_is_used() -> None:
    line = "Total Liabilities Net Minority Interest"
    data = _company_data({line: {FY[2022]: 60.0}})
    # "Liabilities" is tagged but means something else; the identity reproduces Yahoo.
    facts = _facts(
        fy2021={"Liabilities": 10.0, "EquityAndLiabilities": 95.0, "Equity": 40.0},
        fy2022={"Liabilities": 12.0, "EquityAndLiabilities": 100.0, "Equity": 40.0},
    )

    result = esef.extend(data, facts)

    assert result.chosen[line] == "EquityAndLiabilities - Equity"
    assert result.data.balance_sheet.loc[line, FY[2021]] == 55.0


def test_a_line_with_no_shared_year_is_not_validated() -> None:
    data = _company_data({"Total Assets": {FY[2022]: 100.0}})
    facts = _facts(fy2021={"Assets": 90.0})

    assert esef.extend(data, facts).chosen["Total Assets"] is None


def test_extend_does_not_mutate_its_input() -> None:
    data = _company_data({"Total Assets": {FY[2022]: 100.0}})
    before = data.balance_sheet.copy()

    esef.extend(data, _facts(fy2021={"Assets": 90.0}, fy2022={"Assets": 100.0}))

    pd.testing.assert_frame_equal(data.balance_sheet, before)


def _index(*urls: str) -> bytes:
    return json.dumps({"data": [{"attributes": {"json_url": u}} for u in urls]}).encode()


def test_load_filings_keys_each_filing_by_its_latest_year_and_caches(tmp_path) -> None:
    calls = []
    responses = {
        "/api/entities/LEI/filings": _index("/a.json", "/b.json", None),
        "/a.json": json.dumps(_payload(
            _fact("Assets", "2022-01-01T00:00:00", 100), _fact("Assets", "2021-01-01T00:00:00", 90)
        )).encode(),
        "/b.json": json.dumps(_payload(_fact("Assets", "2023-01-01T00:00:00", 120))).encode(),
    }

    def fetcher(path: str) -> bytes:
        calls.append(path)
        return responses[path]

    first = esef.load_filings("LEI", fetcher, tmp_path)
    again = esef.load_filings("LEI", fetcher, tmp_path)

    assert sorted(first) == [FY[2021], FY[2022]]
    assert first[FY[2021]][FY[2020]] == {"ifrs-full:Assets": 90.0}
    assert again == first
    assert len(calls) == 3


def test_load_filings_rejects_an_unknown_entity(tmp_path) -> None:
    with pytest.raises(CreditLabError, match="LEI"):
        esef.load_filings("NOPE", lambda path: b'{"errors": []}', tmp_path)


def test_dates_that_do_not_close_a_fiscal_year_are_not_spliced() -> None:
    data = _company_data({"Total Assets": {FY[2022]: 100.0}})
    facts = {
        **_facts(fy2021={"Assets": 90.0}, fy2022={"Assets": 100.0}),
        pd.Timestamp("2021-01-01"): {"ifrs-full:Assets": 85.0},
    }

    result = esef.extend(data, facts)

    assert result.added_years["Total Assets"] == [FY[2021]]
    assert pd.Timestamp("2021-01-01") not in result.data.balance_sheet.columns


def test_filings_survive_a_round_trip_through_the_fixture_format() -> None:
    a = "ifrs-full:Assets"
    filings = {FY[2022]: {FY[2022]: {a: 120.0}, FY[2021]: {a: 103.0}}}

    assert esef.undump(esef.dump(filings)) == filings


def test_the_frozen_filings_extend_ohlson_back_to_fy2020_for_emeis() -> None:
    data = frozen.load()["loaded"]["EMEIS.PA"]
    filings = esef.undump((frozen.FIXTURES / "esef" / "EMEIS_PA.json").read_text(encoding="utf-8"))

    result = esef.extend(data, esef.merge(filings))

    ohlson_lines = (
        "Total Assets", "Total Liabilities Net Minority Interest", "Working Capital",
        "Current Assets", "Current Liabilities", "Net Income", "Operating Cash Flow",
    )
    for line in ohlson_lines:
        assert FY[2020] in result.added_years[line], line
    # Neither Yahoo's EBIT nor its share count is reproduced by any IFRS concept.
    assert result.chosen["EBIT"] is None
    assert result.chosen["Ordinary Shares Number"] is None
