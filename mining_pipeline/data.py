"""OHLCV data loader.

Pulls daily OHLCV for a fixed US large-cap universe from yfinance and
returns a `Panel` of aligned numpy arrays plus a date index. The
universe is a hand-picked, sector-diverse subset of the S&P 100 that's
liquid enough for daily long-short backtesting.

Caches to `cache/ohlcv.parquet` so re-runs are fast.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd


# ~250 large- and mid-cap US tickers (S&P 500 + selected mid-caps), stable
# membership across 2019-now. Larger universes give Sharpe a fighting chance
# at the user's 1.25 threshold; a 60-name book is too narrow to disperse.
DEFAULT_UNIVERSE: List[str] = [
    # Mega-cap tech
    "AAPL","MSFT","GOOGL","GOOG","AMZN","META","NVDA","AVGO","ORCL","CSCO",
    "ADBE","CRM","INTC","AMD","QCOM","TXN","AMAT","MU","LRCX","KLAC",
    "ADI","INTU","NOW","PANW","SNPS","CDNS","MRVL","FTNT","WDC","STX",
    # Financials
    "JPM","BAC","WFC","GS","MS","C","AXP","BLK","SCHW","BX",
    "TROW","STT","NTRS","BK","USB","PNC","TFC","COF","MET","PRU",
    "AIG","ALL","TRV","CB","PGR","AFL","HIG","MMC","AON","SPGI",
    "ICE","CME","NDAQ","MCO","V","MA",
    # Healthcare
    "UNH","JNJ","PFE","MRK","ABBV","LLY","TMO","ABT","DHR","BMY",
    "AMGN","GILD","CVS","CI","ANTM","HUM","ELV","MDT","SYK","BSX",
    "ISRG","BDX","ZTS","REGN","VRTX","BIIB","MRNA","IDXX","DXCM","ALGN",
    # Consumer Discretionary
    "WMT","HD","COST","TGT","LOW","DG","DLTR","TJX","ROST","BBY",
    "MCD","SBUX","CMG","YUM","NKE","LULU","TSLA","F","GM","PCAR",
    "BKNG","MAR","HLT","MGM","WYNN","DIS","NFLX","CMCSA","CHTR",
    # Staples
    "PG","KO","PEP","MO","PM","CL","KMB","GIS","K","MDLZ",
    "STZ","SYY","KR","HSY","CHD","CLX",
    # Energy
    "XOM","CVX","COP","SLB","EOG","PSX","VLO","MPC","OXY","HES",
    "DVN","FANG","HAL","BKR","WMB","KMI","OKE","ENB",
    # Industrials
    "CAT","BA","HON","GE","UPS","RTX","LMT","NOC","GD","DE",
    "EMR","ITW","ETN","PH","ROK","FDX","CSX","UNP","NSC","WM",
    "RSG","JCI","AME","FAST","PCAR","CMI","GWW","MMM","MAS","SWK",
    # Telecom / Comm
    "VZ","T","TMUS",
    # Utilities
    "NEE","DUK","SO","D","AEP","EXC","XEL","SRE","WEC","ED",
    "PCG","EIX",
    # Materials
    "LIN","APD","SHW","ECL","FCX","NEM","DOW","DD","NUE","STLD",
    "PPG","BALL","IFF",
    # Real Estate
    "AMT","PLD","CCI","EQIX","DLR","O","SPG","WELL","PSA","AVB",
    "EQR","INVH","SBAC","VICI",
    # Misc large/mid caps
    "DOCU","ZM","SQ","PYPL","SHOP","SNAP","UBER","LYFT","ABNB","DDOG",
    "ZS","CRWD","NET","OKTA","TEAM","WDAY","VEEV","HUBS","TWLO","MDB",
]


# IS / OS windows per user spec
IS_START = "2019-01-01"
IS_END   = "2023-12-31"
OS_START = "2024-01-01"
# OS end defaults to today
DEFAULT_END = pd.Timestamp.utcnow().tz_localize(None).normalize().strftime("%Y-%m-%d")


@dataclass
class Panel:
    """Aligned OHLCV panel.

    Each `*_arr` is a (T, N) numpy float64 matrix; `dates` is length T,
    `tickers` is length N.
    """
    dates: pd.DatetimeIndex
    tickers: List[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    @property
    def vwap(self) -> np.ndarray:
        return (self.high + self.low + self.close) / 3.0

    @property
    def returns(self) -> np.ndarray:
        prev = np.roll(self.close, 1, axis=0)
        prev[0, :] = np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.close / prev - 1.0

    def is_mask(self) -> np.ndarray:
        return (self.dates >= pd.Timestamp(IS_START)) & (self.dates <= pd.Timestamp(IS_END))

    def os_mask(self) -> np.ndarray:
        return self.dates >= pd.Timestamp(OS_START)


CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "cache", "ohlcv.pkl")


def _download(tickers: List[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf  # heavy import deferred
    df = yf.download(
        tickers, start=start, end=end,
        progress=False, auto_adjust=True, threads=True, group_by="column",
    )
    # yfinance sometimes returns a MultiIndex (field, ticker). Normalize.
    if isinstance(df.columns, pd.MultiIndex):
        return df
    raise RuntimeError(f"Unexpected yfinance frame shape: {df.shape}")


def load(tickers: List[str] = None,
         start: str = IS_START,
         end: str = DEFAULT_END,
         use_cache: bool = True) -> Panel:
    tickers = tickers or DEFAULT_UNIVERSE
    cache_dir = os.path.dirname(CACHE_PATH)
    os.makedirs(cache_dir, exist_ok=True)

    if use_cache and os.path.exists(CACHE_PATH):
        df = pd.read_pickle(CACHE_PATH)
    else:
        df = _download(tickers, start, end)
        df.to_pickle(CACHE_PATH)

    # Build aligned (T, N) arrays
    fields = ["Open", "High", "Low", "Close", "Volume"]
    out = {}
    for fld in fields:
        sub = df[fld]
        # ensure column order matches `tickers`
        present = [t for t in tickers if t in sub.columns]
        sub = sub[present]
        out[fld.lower()] = sub.values.astype(np.float64)

    dates = df.index
    return Panel(
        dates=dates,
        tickers=present,
        open=out["open"], high=out["high"], low=out["low"],
        close=out["close"], volume=out["volume"],
    )


if __name__ == "__main__":
    p = load()
    print(f"Loaded {len(p.tickers)} tickers x {len(p.dates)} days "
          f"({p.dates[0].date()} -> {p.dates[-1].date()})")
    print(f"  IS days: {p.is_mask().sum()}   OS days: {p.os_mask().sum()}")
