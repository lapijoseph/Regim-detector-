import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple

MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    pass

import yfinance as yf


class DataConnector:
    YFINANCE_SUFFIX_MAP = {
        'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'USDJPY=X',
        'AUDUSD': 'AUDUSD=X', 'USDCAD': 'USDCAD=X', 'USDCHF': 'USDCHF=X',
        'NZDUSD': 'NZDUSD=X', 'EURGBP': 'EURGBP=X', 'EURJPY': 'EURJPY=X',
        'GBPJPY': 'GBPJPY=X', 'AUDJPY': 'AUDJPY=X', 'CHFJPY': 'CHFJPY=X',
        'EURNZD': 'EURNZD=X', 'EURCAD': 'EURCAD=X', 'EURAUD': 'EURAUD=X',
        'GBPAUD': 'GBPAUD=X', 'GBPCAD': 'GBPCAD=X', 'GBPNZD': 'GBPNZD=X',
        'AUDCAD': 'AUDCAD=X', 'AUDNZD': 'AUDNZD=X', 'CADJPY': 'CADJPY=X',
        'NZDJPY': 'NZDJPY=X', 'XAUUSD': 'GC=F', 'XAGUSD': 'SI=F',
        'BTCUSD': 'BTC-USD', 'ETHUSD': 'ETH-USD', 'SP500': '^GSPC',
        'US30': '^DJI', 'NAS100': '^IXIC', 'DAX': '^GDAXI',
    }

    TIMEFRAME_MAP = {
        'M1': '1m', 'M5': '5m', 'M15': '15m', 'M30': '30m',
        'H1': '1h', 'H4': '4h', 'D1': '1d', 'W1': '1wk',
    }

    MT5_TIMEFRAME_MAP = {}

    def __init__(self, mt5_login: Optional[str] = None, mt5_password: Optional[str] = None,
                 mt5_server: Optional[str] = None):
        self.mt5_login = mt5_login
        self.mt5_password = mt5_password
        self.mt5_server = mt5_server
        self.mt5_initialized = False

        if MT5_AVAILABLE:
            self._init_mt5_timeframes()

    def _init_mt5_timeframes(self):
        import MetaTrader5 as mt5
        self.MT5_TIMEFRAME_MAP = {
            'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1,
        }

    def _init_mt5(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        if self.mt5_initialized:
            return True
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return False
        if self.mt5_login and self.mt5_password:
            authorized = mt5.login(
                login=int(self.mt5_login),
                password=self.mt5_password,
                server=self.mt5_server
            )
            if not authorized:
                return False
        self.mt5_initialized = True
        return True

    def fetch(self, symbol: str, timeframe: str = 'H1',
              bars: int = 100, source: str = 'auto') -> Optional[pd.DataFrame]:
        if source == 'auto':
            if MT5_AVAILABLE and self._init_mt5():
                df = self._fetch_mt5(symbol, timeframe, bars)
                if df is not None and len(df) > 20:
                    return df
            return self._fetch_yfinance(symbol, timeframe, bars)
        elif source == 'mt5':
            if not MT5_AVAILABLE or not self._init_mt5():
                return None
            return self._fetch_mt5(symbol, timeframe, bars)
        else:
            return self._fetch_yfinance(symbol, timeframe, bars)

    def _fetch_mt5(self, symbol: str, timeframe: str, bars: int) -> Optional[pd.DataFrame]:
        import MetaTrader5 as mt5
        tf = self.MT5_TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            return None
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={
            'time': 'Date', 'open': 'Open', 'high': 'High',
            'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'
        })
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df.set_index('Date', inplace=True)
        return df

    def _fetch_yfinance(self, symbol: str, timeframe: str, bars: int) -> Optional[pd.DataFrame]:
        yf_symbol = self.YFINANCE_SUFFIX_MAP.get(symbol, symbol)
        interval = self.TIMEFRAME_MAP.get(timeframe, '1h')

        period_map = {'1m': '7d', '5m': '1mo', '15m': '1mo', '30m': '2mo',
                      '1h': '3mo', '4h': '6mo', '1d': '2y', '1wk': '5y'}
        period = period_map.get(interval, '3mo')

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return None
            if len(df) > bars:
                df = df.tail(bars)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            return df
        except Exception:
            return None

    def fetch_multi_timeframe(self, symbol: str, timeframes: list,
                              bars: int = 100, source: str = 'auto') -> dict:
        return {
            tf: self.fetch(symbol, tf, bars, source)
            for tf in timeframes
        }
