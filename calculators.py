from typing import Optional, Tuple


class PositionSizeCalculator:
    def __init__(self, account_balance: float = 10000.0,
                 risk_percent: float = 1.0,
                 account_currency: str = 'USD'):
        self.account_balance = account_balance
        self.risk_percent = risk_percent
        self.account_currency = account_currency

    def calculate(self, entry_price: float, stop_loss: float,
                  symbol: str = 'EURUSD', leverage: int = 1,
                  contract_size: Optional[int] = None) -> dict:
        contract_size = contract_size or self._get_contract_size(symbol)
        risk_amount = self.account_balance * (self.risk_percent / 100)
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance == 0:
            return {'error': 'Stop loss distance cannot be zero'}

        pip_value = self._get_pip_value(symbol, entry_price, contract_size)
        sl_pips = sl_distance / self._get_pip_size(symbol)
        position_size_units = (risk_amount * contract_size) / (sl_pips * pip_value) if pip_value > 0 else 0
        position_size_lots = position_size_units / contract_size

        position_size_lots = max(min(position_size_lots, 100), 0.01)
        position_size_lots = round(position_size_lots, 2)

        actual_risk_amount = sl_pips * position_size_lots * pip_value if pip_value > 0 else 0
        margin_required = (position_size_lots * contract_size * entry_price) / leverage if leverage > 0 else 0

        unit_label = 'units' if self._is_crypto(symbol) else contract_size

        return {
            'symbol': symbol,
            'position_size_lots': position_size_lots,
            'position_size_units': round(position_size_lots * contract_size),
            'risk_amount': round(risk_amount, 2),
            'actual_risk_amount': round(actual_risk_amount, 2),
            'sl_distance': round(sl_distance, 5),
            'sl_pips': round(sl_pips, 1),
            'margin_required': round(margin_required, 2),
            'risk_percent': self.risk_percent,
            'account_balance': self.account_balance,
        }

    def calculate_risk_per_lot(self, entry_price: float, stop_loss: float,
                                symbol: str = 'EURUSD',
                                contract_size: Optional[int] = None) -> dict:
        contract_size = contract_size or self._get_contract_size(symbol)
        sl_distance = abs(entry_price - stop_loss)
        pip_value = self._get_pip_value(symbol, entry_price, contract_size)
        sl_pips = sl_distance / self._get_pip_size(symbol)
        risk_per_lot = sl_pips * pip_value if pip_value > 0 else 0

        return {
            'risk_per_lot': round(risk_per_lot, 2),
            'sl_pips': round(sl_pips, 1),
            'pip_value': round(pip_value, 5),
        }

    def calculate_all(self, entry: float, stop_loss: float,
                      take_profit: Optional[float] = None,
                      symbol: str = 'EURUSD', leverage: int = 100,
                      contract_size: Optional[int] = None) -> dict:
        contract_size = contract_size or self._get_contract_size(symbol)
        pos = self.calculate(entry, stop_loss, symbol, leverage, contract_size)
        risk_per_lot = self.calculate_risk_per_lot(entry, stop_loss, symbol, contract_size)

        result = {**pos, **risk_per_lot}

        if take_profit is not None:
            tp_distance = abs(take_profit - entry)
            tp_pips = tp_distance / self._get_pip_size(symbol)
            r_multiple = tp_pips / pos['sl_pips'] if pos['sl_pips'] > 0 else 0
            potential_profit = tp_pips * pos['position_size_lots'] * risk_per_lot['pip_value'] if risk_per_lot['pip_value'] > 0 else 0
            reward_risk = tp_pips / pos['sl_pips'] if pos['sl_pips'] > 0 else 0

            result['take_profit'] = take_profit
            result['tp_pips'] = round(tp_pips, 1)
            result['r_multiple'] = round(r_multiple, 2)
            result['potential_profit'] = round(potential_profit, 2)
            result['reward_risk'] = round(reward_risk, 2)

        return result

    def _is_crypto(self, symbol: str) -> bool:
        return symbol in ('BTC-USD', 'ETH-USD', 'BTCUSD', 'ETHUSD')

    def _is_metal(self, symbol: str) -> bool:
        return symbol in ('XAUUSD', 'XAGUSD', 'GC=F', 'SI=F')

    def _get_contract_size(self, symbol: str, default_size: int = 100000) -> int:
        if self._is_crypto(symbol):
            return 1
        if self._is_metal(symbol):
            return 100
        return default_size

    def _get_pip_size(self, symbol: str) -> float:
        if self._is_crypto(symbol):
            return 1.0
        if symbol in ('XAUUSD', 'XAGUSD', 'GC=F', 'SI=F'):
            return 0.01
        if 'JPY' in symbol:
            return 0.01
        return 0.0001

    def _get_pip_value(self, symbol: str, price: float,
                       contract_size: int = 100000) -> float:
        pip_size = self._get_pip_size(symbol)
        if self._is_crypto(symbol):
            return pip_size  # $1 per pip per unit
        if self.account_currency == 'USD':
            if 'JPY' in symbol:
                return pip_size / price * contract_size
            if symbol in ('XAUUSD', 'GC=F'):
                return pip_size * contract_size
            return pip_size * contract_size
        return pip_size * contract_size


class PnLCalculator:
    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        return symbol in ('BTC-USD', 'ETH-USD', 'BTCUSD', 'ETHUSD')

    @staticmethod
    def _is_metal(symbol: str) -> bool:
        return symbol in ('XAUUSD', 'XAGUSD', 'GC=F', 'SI=F')

    @staticmethod
    def _get_contract_size(symbol: str, default: int = 100000) -> int:
        if PnLCalculator._is_crypto(symbol):
            return 1
        if PnLCalculator._is_metal(symbol):
            return 100
        return default

    @staticmethod
    def calculate(entry_price: float, exit_price: float,
                  position_size_lots: float, symbol: str = 'EURUSD',
                  direction: str = 'long', contract_size: Optional[int] = None,
                  commission_per_lot: float = 0.0,
                  spread_pips: float = 0.0) -> dict:
        contract_size = contract_size or PnLCalculator._get_contract_size(symbol)
        pip_size = PnLCalculator._get_pip_size(symbol)
        price_diff = (exit_price - entry_price) if direction == 'long' else (entry_price - exit_price)
        pips = price_diff / pip_size
        pip_value = PnLCalculator._get_pip_value(symbol, entry_price, contract_size)
        gross_pnl = pips * position_size_lots * pip_value if pip_value > 0 else 0
        commission = commission_per_lot * position_size_lots * 2
        spread_cost = spread_pips * position_size_lots * pip_value if pip_value > 0 else 0
        net_pnl = gross_pnl - commission - spread_cost
        notional = entry_price * position_size_lots * contract_size
        roi = (net_pnl / notional) * 100 if notional > 0 else 0

        return {
            'symbol': symbol,
            'gross_pnl': round(gross_pnl, 2),
            'net_pnl': round(net_pnl, 2),
            'pips': round(pips, 1),
            'commission': round(commission, 2),
            'spread_cost': round(spread_cost, 2),
            'roi': round(roi, 4),
            'direction': direction,
        }

    @staticmethod
    def calculate_batch(trades: list) -> dict:
        results = [PnLCalculator.calculate(**t) for t in trades]
        total_gross = sum(r['gross_pnl'] for r in results)
        total_net = sum(r['net_pnl'] for r in results)
        total_commission = sum(r['commission'] for r in results)
        total_spread = sum(r['spread_cost'] for r in results)
        wins = [r for r in results if r['net_pnl'] > 0]
        losses = [r for r in results if r['net_pnl'] <= 0]
        win_rate = len(wins) / len(results) * 100 if results else 0
        avg_win = sum(r['net_pnl'] for r in wins) / len(wins) if wins else 0
        avg_loss = sum(r['net_pnl'] for r in losses) / len(losses) if losses else 0
        profit_factor = abs(sum(r['net_pnl'] for r in wins) / sum(r['net_pnl'] for r in losses)) if losses and sum(r['net_pnl'] for r in losses) != 0 else float('inf')

        return {
            'total_trades': len(results),
            'total_gross_pnl': round(total_gross, 2),
            'total_net_pnl': round(total_net, 2),
            'total_commission': round(total_commission, 2),
            'total_spread_cost': round(total_spread, 2),
            'win_rate': round(win_rate, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'trades': results,
        }

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        return symbol in ('BTC-USD', 'ETH-USD', 'BTCUSD', 'ETHUSD')

    @staticmethod
    def _get_pip_size(symbol: str) -> float:
        if PnLCalculator._is_crypto(symbol):
            return 1.0
        if symbol in ('XAUUSD', 'XAGUSD', 'GC=F', 'SI=F'):
            return 0.01
        if 'JPY' in symbol:
            return 0.01
        return 0.0001

    @staticmethod
    def _get_pip_value(symbol: str, price: float,
                       contract_size: int = 100000) -> float:
        pip_size = PnLCalculator._get_pip_size(symbol)
        if PnLCalculator._is_crypto(symbol):
            return pip_size  # $1 per pip per BTC
        if 'JPY' in symbol:
            return pip_size / price * contract_size
        if symbol in ('XAUUSD', 'GC=F'):
            return pip_size * contract_size
        return pip_size * contract_size
