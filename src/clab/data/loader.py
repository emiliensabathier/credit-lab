"""Data acquisition, and the only place in this package that reaches the network.

Every entry point takes a `fetcher` argument defaulting to the live implementation,
so the whole test suite runs offline against injected doubles. Statements and prices
are cached on disk for a week; pass refresh=True to force a pull.
"""

from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from clab.errors import CurrencyMismatchError, MissingLineError
from clab.universe import Company

CACHE_DIR = Path(__file__).resolve().parents[3] / "cache"
CACHE_MAX_AGE_DAYS = 7

FRED_SERIES: dict[str, str] = {
    "EUR": "IR3TIB01DEM156N",
    "SEK": "IR3TIB01SEM156N",
    "CHF": "IR3TIB01CHM156N",
}
FRED_DEFLATOR = "GDPDEF"
FX_TICKERS: dict[str, str] = {"EUR": "EURUSD=X", "SEK": "SEKUSD=X", "CHF": "CHFUSD=X"}


@dataclass(frozen=True)
class CompanyData:
    company: Company
    balance_sheet: pd.DataFrame
    income: pd.DataFrame
    cashflow: pd.DataFrame
    prices: pd.Series


def line(frame: pd.DataFrame, name: str, ticker: str) -> pd.Series:
    """Return one accounting line, or refuse by name.

    A missing line is not a zero and not a NaN to be filled later: it is a number
    this package cannot produce honestly.
    """
    if name not in frame.index:
        raise MissingLineError(f"{ticker}: statement line {name!r} is not reported")
    return frame.loc[name]


def _yahoo_fetcher(ticker: str) -> dict:
    import yfinance as yf

    handle = yf.Ticker(ticker)
    info = handle.get_info()
    return {
        "balance_sheet": handle.balance_sheet,
        "income": handle.income_stmt,
        "cashflow": handle.cashflow,
        "prices": handle.history(period="max")["Close"],
        "currency": info.get("currency"),
        "financial_currency": info.get("financialCurrency"),
    }


def _cached(ticker: str, fetcher, refresh: bool) -> dict:
    """One week of on-disk memory, so a repeated live run does not re-hammer the source.

    The cache is a convenience, never a guarantee: reproducibility comes from the frozen
    fixture, which is what the test suite replays.
    """
    import pickle

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{ticker.replace('.', '_').replace('-', '_')}.pkl"
    if not refresh and path.exists():
        age = pd.Timestamp.today() - pd.Timestamp(path.stat().st_mtime, unit="s")
        if age < pd.Timedelta(days=CACHE_MAX_AGE_DAYS):
            return pickle.loads(path.read_bytes())
    raw = fetcher(ticker)
    path.write_bytes(pickle.dumps(raw))
    return raw


def load_company(company: Company, fetcher=_yahoo_fetcher, refresh: bool = False) -> CompanyData:
    raw = (
        _cached(company.ticker, fetcher, refresh)
        if fetcher is _yahoo_fetcher
        else fetcher(company.ticker)
    )
    trading, reporting = raw["currency"], raw["financial_currency"]
    if trading != reporting:
        raise CurrencyMismatchError(
            f"{company.ticker}: trades in {trading} but reports in {reporting}; "
            "comparing a per-share figure across two currencies is a silent error"
        )
    prices = raw["prices"]
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return CompanyData(
        company=company,
        balance_sheet=raw["balance_sheet"],
        income=raw["income"],
        cashflow=raw["cashflow"],
        prices=prices.sort_index(),
    )


def _fred_fetcher(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read().decode()
    frame = pd.read_csv(io.StringIO(payload), parse_dates=[0], index_col=0)
    return pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()


def _daily(series: pd.Series) -> pd.Series:
    index = pd.date_range(series.index.min(), pd.Timestamp.today().normalize(), freq="D")
    return series.reindex(index).ffill()


def load_rates(fetcher=_fred_fetcher) -> pd.DataFrame:
    """Three-month interbank rates per currency, as decimals, forward-filled daily.

    FRED publishes these monthly; a risk-free rate held flat between prints is a
    far smaller approximation than any of the modelling assumptions above it.
    """
    columns = {
        code: _daily(fetcher(series_id)) / 100.0 for code, series_id in FRED_SERIES.items()
    }
    return pd.DataFrame(columns)


def load_deflator(fetcher=_fred_fetcher) -> pd.Series:
    return _daily(fetcher(FRED_DEFLATOR))


def _yahoo_fx_fetcher(ticker: str) -> pd.Series:
    import yfinance as yf

    prices = yf.Ticker(ticker).history(period="max")["Close"]
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return prices.sort_index()


def load_fx(fetcher=_yahoo_fx_fetcher) -> pd.DataFrame:
    return pd.DataFrame({code: _daily(fetcher(ticker)) for code, ticker in FX_TICKERS.items()})
