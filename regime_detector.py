import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple


class RegimeDetector:
    DIRECTION_BULL = 'Bull'
    DIRECTION_BEAR = 'Bear'
    DIRECTION_SIDEWAYS = 'Sideways'
    VOLATILITY_QUIET = 'Quiet'
    VOLATILITY_VOLATILE = 'Volatile'

    REGIME_LABELS = [
        'Bull Volatile', 'Bull Quiet',
        'Bear Volatile', 'Bear Quiet',
        'Sideways Volatile', 'Sideways Quiet'
    ]

    def __init__(self, ema_fast: int = 20, ema_mid: int = 50, ema_slow: int = 200,
                 adx_period: int = 14, adx_threshold: int = 20,
                 atr_period: int = 14, atr_percentile: int = 50,
                 bb_period: int = 20, bb_std: float = 2.0):
        self.ema_fast = ema_fast
        self.ema_mid = ema_mid
        self.ema_slow = ema_slow
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period
        self.atr_percentile = atr_percentile
        self.bb_period = bb_period
        self.bb_std = bb_std

    def detect(self, df: pd.DataFrame) -> Optional[Dict]:
        if df is None or len(df) < 50:
            return None

        df = df.copy()
        self._add_indicators(df)
        latest = df.iloc[-1]
        lookback = df.iloc[-20:]

        direction, dir_votes, dir_total = self._detect_direction(df, latest, lookback)
        volatility, vol_votes, vol_total = self._detect_volatility(df, latest)

        direction_conf = round(dir_votes / dir_total * 100) if dir_total > 0 else 0
        volatility_conf = round(vol_votes / vol_total * 100) if vol_total > 0 else 0
        overall_conf = round((direction_conf * 0.6 + volatility_conf * 0.4))

        regime = f"{direction} {volatility}"
        color = self._get_regime_color(regime)
        emoji = self._get_regime_emoji(regime)
        description = self._get_regime_description(regime)

        indicators = {
            'EMA20': latest.get('EMA20'),
            'EMA50': latest.get('EMA50'),
            'EMA200': latest.get('EMA200') if 'EMA200' in latest and not pd.isna(latest.get('EMA200')) else None,
            'ADX': round(latest.get('ADX', 0), 1),
            'ATR': round(latest.get('ATR', 0), 5),
            'ATR_Percentile': round(latest.get('ATR_Percentile', 0), 1),
            'BB_Width': round(latest.get('BB_Width', 0), 5),
            'BB_Width_Percentile': round(latest.get('BB_Width_Percentile', 0), 1),
            'MACD': round(latest.get('MACD', 0), 5),
            'MACD_Signal': round(latest.get('MACD_Signal', 0), 5),
            'RSI': round(latest.get('RSI', 0), 1),
            'Price': round(latest.get('Close', 0), 5),
        }

        votes = {
            'direction': {'Bull': 0, 'Bear': 0, 'Sideways': 0},
            'volatility': {'Quiet': 0, 'Volatile': 0},
        }
        self._record_direction_votes(df, latest, lookback, votes)
        self._record_volatility_votes(df, latest, votes)

        return {
            'regime': regime,
            'direction': direction,
            'volatility': volatility,
            'confidence': overall_conf,
            'direction_confidence': direction_conf,
            'volatility_confidence': volatility_conf,
            'color': color,
            'emoji': emoji,
            'description': description,
            'indicators': indicators,
            'votes': votes,
            'timestamp': str(df.index[-1]),
        }

    def detect_multi_timeframe(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        return {
            tf: self.detect(df)
            for tf, df in data.items()
            if df is not None
        }

    def _add_indicators(self, df: pd.DataFrame):
        closes = df['Close'].values.astype(float)
        highs = df['High'].values.astype(float)
        lows = df['Low'].values.astype(float)

        df['EMA20'] = self._ema(closes, 20)
        df['EMA50'] = self._ema(closes, 50)
        df['EMA200'] = self._ema(closes, 200)

        df['ATR'] = self._atr(highs, lows, closes, self.atr_period)
        df['ATR_Percentile'] = self._rolling_percentile(df['ATR'].values)

        df['BB_Upper'], df['BB_Middle'], df['BB_Lower'] = self._bollinger_bands(closes, self.bb_period, self.bb_std)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
        df['BB_Width_Percentile'] = self._rolling_percentile(df['BB_Width'].values)

        df['ADX'] = self._adx(highs, lows, closes, self.adx_period)

        macd_line, signal_line = self._macd(closes)
        df['MACD'] = macd_line
        df['MACD_Signal'] = signal_line

        df['RSI'] = self._rsi(closes, 14)

        df['EMA20_Slope'] = df['EMA20'].diff(3) / df['EMA20'].shift(3) * 100
        df['EMA50_Slope'] = df['EMA50'].diff(3) / df['EMA50'].shift(3) * 100

    def _detect_direction(self, df: pd.DataFrame, latest: pd.Series,
                          lookback: pd.DataFrame) -> Tuple[str, int, int]:
        votes = 0
        total = 5

        price = latest['Close']

        vote1 = price > latest['EMA20']
        votes += 1 if vote1 else 0

        vote2 = latest['EMA20'] > latest['EMA50'] if not pd.isna(latest.get('EMA50')) else False
        votes += 1 if vote2 else 0

        vote3 = latest['EMA20_Slope'] > 0 if not pd.isna(latest.get('EMA20_Slope')) else False
        votes += 1 if vote3 else 0

        vote4 = latest.get('ADX', 0) > self.adx_threshold and latest['MACD'] > latest['MACD_Signal']
        votes += 1 if vote4 else 0

        bb_touches = self._check_bb_touches(lookback)
        vote5 = not bb_touches
        votes += 1 if vote5 else 0

        bear_votes = total - votes

        if votes >= 4:
            return self.DIRECTION_BULL, votes, total
        elif bear_votes >= 4:
            return self.DIRECTION_BEAR, bear_votes, total
        elif votes <= 2 and bear_votes <= 2:
            return self.DIRECTION_SIDEWAYS, max(votes, bear_votes), total
        elif votes >= bear_votes:
            return self.DIRECTION_BULL, votes, total
        else:
            return self.DIRECTION_BEAR, bear_votes, total

    def _detect_volatility(self, df: pd.DataFrame, latest: pd.Series) -> Tuple[str, int, int]:
        votes = 0
        total = 2

        atr_pct = latest.get('ATR_Percentile', 0)
        if not pd.isna(atr_pct):
            votes += 1 if atr_pct >= self.atr_percentile else 0
        else:
            total -= 1

        bbw_pct = latest.get('BB_Width_Percentile', 0)
        if not pd.isna(bbw_pct):
            votes += 1 if bbw_pct >= self.atr_percentile else 0
        else:
            total -= 1

        if total == 0:
            return self.VOLATILITY_QUIET, 0, 1

        if votes >= total / 2:
            return self.VOLATILITY_VOLATILE, votes, total
        else:
            return self.VOLATILITY_QUIET, total - votes, total

    def _record_direction_votes(self, df: pd.DataFrame, latest: pd.Series,
                                 lookback: pd.DataFrame, votes: dict):
        price = latest['Close']

        if price > latest['EMA20']:
            votes['direction']['Bull'] += 1
        else:
            votes['direction']['Bear'] += 1

        if latest['EMA20'] > latest.get('EMA50', 0) if not pd.isna(latest.get('EMA50', np.nan)) else False:
            votes['direction']['Bull'] += 1
        else:
            votes['direction']['Bear'] += 1

        slope = latest.get('EMA20_Slope', 0)
        if not pd.isna(slope) and slope > 0:
            votes['direction']['Bull'] += 1
        elif not pd.isna(slope):
            votes['direction']['Bear'] += 1

        adx = latest.get('ADX', 0)
        if not pd.isna(adx) and adx <= self.adx_threshold:
            votes['direction']['Sideways'] += 1
        elif latest['MACD'] > latest['MACD_Signal']:
            votes['direction']['Bull'] += 1
        else:
            votes['direction']['Bear'] += 1

        bb_touches = self._check_bb_touches(lookback)
        if bb_touches:
            votes['direction']['Sideways'] += 1
        elif price > latest['BB_Middle']:
            votes['direction']['Bull'] += 1
        else:
            votes['direction']['Bear'] += 1

    def _record_volatility_votes(self, df: pd.DataFrame, latest: pd.Series, votes: dict):
        atr_pct = latest.get('ATR_Percentile', 0)
        if not pd.isna(atr_pct):
            if atr_pct >= self.atr_percentile:
                votes['volatility']['Volatile'] += 1
            else:
                votes['volatility']['Quiet'] += 1

        bbw_pct = latest.get('BB_Width_Percentile', 0)
        if not pd.isna(bbw_pct):
            if bbw_pct >= self.atr_percentile:
                votes['volatility']['Volatile'] += 1
            else:
                votes['volatility']['Quiet'] += 1

    def _check_bb_touches(self, lookback: pd.DataFrame, threshold: float = 0.3) -> bool:
        if len(lookback) < 5:
            return False
        upper_touches = (lookback['High'] >= lookback['BB_Upper'] * 0.98).sum()
        lower_touches = (lookback['Low'] <= lookback['BB_Lower'] * 1.02).sum()
        total = upper_touches + lower_touches
        return total / len(lookback) >= threshold

    @staticmethod
    def _ema(values: np.ndarray, period: int) -> np.ndarray:
        if len(values) < period:
            return np.full(len(values), np.nan)
        alpha = 2 / (period + 1)
        result = np.full(len(values), np.nan)
        result[period - 1] = np.mean(values[:period])
        for i in range(period, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
        return result

    @staticmethod
    def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
             period: int) -> np.ndarray:
        if len(highs) < 2:
            return np.full(len(highs), np.nan)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        tr = np.concatenate([[np.nan], tr])
        result = np.full(len(highs), np.nan)
        if len(tr) < period + 1:
            return result
        result[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, len(tr)):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
        return result

    @staticmethod
    def _bollinger_bands(values: np.ndarray, period: int, std: float
                         ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        middle = np.full(len(values), np.nan)
        upper = np.full(len(values), np.nan)
        lower = np.full(len(values), np.nan)
        if len(values) < period:
            return upper, middle, lower
        for i in range(period - 1, len(values)):
            window = values[i - period + 1:i + 1]
            m = np.mean(window)
            s = np.std(window, ddof=1)
            middle[i] = m
            upper[i] = m + std * s
            lower[i] = m - std * s
        return upper, middle, lower

    @staticmethod
    def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
             period: int) -> np.ndarray:
        if len(highs) < period + 1:
            return np.full(len(highs), np.nan)
        up = np.diff(highs)
        down = -np.diff(lows)
        plus_dm = np.where((up > down) & (up > 0), up, 0)
        minus_dm = np.where((down > up) & (down > 0), down, 0)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        atr_val = np.full(len(plus_dm), np.nan)
        plus_di = np.full(len(plus_dm), np.nan)
        minus_di = np.full(len(plus_dm), np.nan)
        if len(tr) < period:
            return np.full(len(highs), np.nan)
        atr_val[period - 1] = np.mean(tr[:period])
        for i in range(period, len(tr)):
            atr_val[i] = (atr_val[i - 1] * (period - 1) + tr[i]) / period
        for i in range(period - 1, len(tr)):
            if atr_val[i] > 0:
                plus_di[i] = 100 * np.mean(plus_dm[i - period + 1:i + 1]) / atr_val[i]
                minus_di[i] = 100 * np.mean(minus_dm[i - period + 1:i + 1]) / atr_val[i]
        dx = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
        adx = np.full(len(plus_di), np.nan)
        for i in range(period * 2 - 1, len(dx)):
            adx[i] = np.mean(dx[i - period + 1:i + 1])
        result = np.full(len(highs), np.nan)
        result[-len(adx):] = adx
        return result

    @staticmethod
    def _macd(values: np.ndarray, fast: int = 12, slow: int = 26,
              signal: int = 9) -> Tuple[np.ndarray, np.ndarray]:
        ema_fast = RegimeDetector._ema(values, fast)
        ema_slow = RegimeDetector._ema(values, slow)
        macd_line = ema_fast - ema_slow
        signal_line = RegimeDetector._ema(macd_line, signal)
        return macd_line, signal_line

    @staticmethod
    def _rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
        if len(values) < period + 1:
            return np.full(len(values), np.nan)
        deltas = np.diff(values)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.full(len(values), np.nan)
        avg_loss = np.full(len(values), np.nan)
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        for i in range(period + 1, len(values)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def _rolling_percentile(values: np.ndarray) -> np.ndarray:
        result = np.full(len(values), np.nan)
        valid = np.where(~np.isnan(values))[0]
        if len(valid) < 20:
            return result
        for i in valid:
            window = values[valid[0]:i + 1]
            window_clean = window[~np.isnan(window)]
            if len(window_clean) > 1:
                result[i] = (window_clean[-1] < window_clean).sum() / len(window_clean) * 100
        return result

    @staticmethod
    def _get_regime_color(regime: str) -> str:
        colors = {
            'Bull Volatile': '#ff6b35', 'Bull Quiet': '#00b894',
            'Bear Volatile': '#d63031', 'Bear Quiet': '#636e72',
            'Sideways Volatile': '#fdcb6e', 'Sideways Quiet': '#74b9ff',
        }
        return colors.get(regime, '#dfe6e9')

    @staticmethod
    def _get_regime_emoji(regime: str) -> str:
        emojis = {
            'Bull Volatile': '🔥', 'Bull Quiet': '🌿',
            'Bear Volatile': '⚡', 'Bear Quiet': '❄️',
            'Sideways Volatile': '🌀', 'Sideways Quiet': '🌊',
        }
        return emojis.get(regime, '❓')

    @staticmethod
    def _get_regime_description(regime: str) -> str:
        descriptions = {
            'Bull Volatile': 'Strong bullish momentum with high volatility. Trend-following ideal. Widen stops.',
            'Bull Quiet': 'Steady bullish climb with low volatility. Favorable for trend trades. Tight stops work.',
            'Bear Volatile': 'Aggressive selling pressure with high volatility. Short entries, but wide stops needed.',
            'Bear Quiet': 'Controlled bearish decline. Steady short trades with tight risk management.',
            'Sideways Volatile': 'Choppy whipsaw with wide swings. High risk of false breakouts. Reduce size or wait.',
            'Sideways Quiet': 'Low-activity consolidation. Mean-reversion works. Expect breakout soon.',
        }
        return descriptions.get(regime, 'Unknown regime.')
