import argparse
import sys
from datetime import datetime
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

import platform

from mt5_connector import DataConnector
from regime_detector import RegimeDetector
from calculators import PositionSizeCalculator, PnLCalculator


def _supports_emoji() -> bool:
    if platform.system() == 'Windows':
        return False
    return True


class RegimeCLI:
    TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']

    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.detector = RegimeDetector()
        self.connector = DataConnector()

    def run(self, args: argparse.Namespace):
        command = args.command

        if command == 'regime':
            self._cmd_regime(args)
        elif command == 'position':
            self._cmd_position(args)
        elif command == 'pnl':
            self._cmd_pnl(args)
        elif command == 'dashboard':
            self._cmd_dashboard(args)
        elif command == 'analyze':
            self._cmd_analyze(args)
        else:
            print(f"Unknown command: {command}")

    def _cmd_regime(self, args: argparse.Namespace):
        symbol = args.symbol.upper()
        timeframe = args.timeframe.upper() if args.timeframe else 'H1'
        bars = args.bars or 100
        source = args.source or 'auto'

        if timeframe not in self.TIMEFRAMES:
            print(f"Invalid timeframe. Choose from: {', '.join(self.TIMEFRAMES)}")
            return

        df = self.connector.fetch(symbol, timeframe, bars, source)
        if df is None:
            print(f"Could not fetch data for {symbol} ({timeframe})")
            return

        result = self.detector.detect(df)
        if result is None:
            print("Could not detect regime (insufficient data)")
            return

        self._display_regime(symbol, timeframe, result)

    def _display_regime(self, symbol: str, timeframe: str, result: dict):
        if not _supports_emoji():
            result['emoji'] = ''
        if RICH_AVAILABLE:
            self._display_rich(symbol, timeframe, result)
        else:
            self._display_plain(symbol, timeframe, result)

    def _display_rich(self, symbol: str, timeframe: str, result: dict):
        regime = result['regime']
        color = result['color']
        emoji = result['emoji']
        desc = result['description']
        conf = result['confidence']
        ind = result['indicators']

        title = Panel(
            Text(f"{emoji}  {symbol}  |  {timeframe}  |  {regime}", style=f"bold {color}"),
            subtitle=f"Confidence: {conf}%",
            border_style=color,
        )
        self.console.print(title)

        votes = result['votes']
        dir_votes = votes['direction']
        vol_votes = votes['volatility']

        vote_table = Table(title="Vote Breakdown", show_header=True, header_style="bold")
        vote_table.add_column("Metric", style="cyan")
        vote_table.add_column("Votes", justify="center")
        vote_table.add_column("Result", justify="center")

        best_dir = max(dir_votes, key=dir_votes.get)
        dir_total = sum(dir_votes.values())
        vol_total = sum(vol_votes.values())
        best_vol = max(vol_votes, key=vol_votes.get)

        vote_table.add_row("Direction",
                           f"Bull:{dir_votes['Bull']} Bear:{dir_votes['Bear']} Side:{dir_votes['Sideways']}",
                           f"[bold]{best_dir}[/bold] ({result['direction_confidence']}%)")
        vote_table.add_row("Volatility",
                           f"Quiet:{vol_votes['Quiet']} Volatile:{vol_votes['Volatile']}",
                           f"[bold]{best_vol}[/bold] ({result['volatility_confidence']}%)")
        self.console.print(vote_table)

        ind_table = Table(title="Key Indicators", show_header=True, header_style="bold")
        ind_table.add_column("Indicator", style="cyan")
        ind_table.add_column("Value", justify="right")
        ind_table.add_column("Signal", justify="center")

        price = ind['Price']
        ema20 = ind['EMA20']
        ema_signal = "Bull" if price > ema20 else "Bear"
        ind_table.add_row("Price", str(price), ema_signal)
        ind_table.add_row("EMA20", str(ema20), ema_signal)
        ind_table.add_row("ADX", str(ind['ADX']),
                          "Trend" if ind['ADX'] > 20 else "Range")
        ind_table.add_row("ATR %ile", f"{ind['ATR_Percentile']}%",
                          "High Vol" if ind['ATR_Percentile'] >= 50 else "Low Vol")
        ind_table.add_row("BB Width %ile", f"{ind['BB_Width_Percentile']}%",
                          "Wide" if ind['BB_Width_Percentile'] >= 50 else "Narrow")
        ind_table.add_row("MACD", str(ind['MACD']),
                          "Bull" if ind['MACD'] > ind['MACD_Signal'] else "Bear")
        ind_table.add_row("RSI", str(ind['RSI']),
                          "Overbought" if ind['RSI'] > 70 else "Oversold" if ind['RSI'] < 30 else "Neutral")
        self.console.print(ind_table)

        desc_panel = Panel(desc, title="Trading Guidance", border_style=color)
        self.console.print(desc_panel)

    def _display_plain(self, symbol: str, timeframe: str, result: dict):
        regime = result['regime']
        emoji = result['emoji']
        conf = result['confidence']
        ind = result['indicators']
        votes = result['votes']

        print("=" * 55)
        print(f"  CAPITALURE REGIME DETECTOR")
        print("=" * 55)
        print(f"  Asset:     {symbol}")
        print(f"  Timeframe: {timeframe}")
        print(f"  Date:      {result['timestamp']}")
        print()
        print(f"  REGIME:    {emoji} {regime}")
        print(f"  Confidence: {conf}%")
        print()
        print(f"  Votes — Direction: Bull={votes['direction']['Bull']}, "
              f"Bear={votes['direction']['Bear']}, "
              f"Sideways={votes['direction']['Sideways']}")
        print(f"  Votes — Volatility: Quiet={votes['volatility']['Quiet']}, "
              f"Volatile={votes['volatility']['Volatile']}")
        print()
        print(f"  Indicators:")
        print(f"    Price: {ind['Price']} | EMA20: {ind['EMA20']}")
        print(f"    ADX: {ind['ADX']} | ATR %ile: {ind['ATR_Percentile']}%")
        print(f"    BB Width %ile: {ind['BB_Width_Percentile']}%")
        print(f"    MACD: {ind['MACD']} | RSI: {ind['RSI']}")
        print()
        print(f"  Guidance: {result['description']}")
        print("=" * 55)

    def _cmd_position(self, args: argparse.Namespace):
        calc = PositionSizeCalculator(
            account_balance=args.balance or 10000,
            risk_percent=args.risk or 1.0,
        )
        result = calc.calculate_all(
            entry=args.entry, stop_loss=args.sl,
            take_profit=args.tp,
            symbol=args.symbol.upper(),
            leverage=args.leverage or 100,
        )
        if RICH_AVAILABLE:
            self._display_position_rich(result)
        else:
            self._display_position_plain(result)

    def _display_position_rich(self, result: dict):
        if 'error' in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
            return

        table = Table(title="Position Size Calculator", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Account Balance", f"${result['account_balance']:,.2f}")
        table.add_row("Risk %", f"{result['risk_percent']}%")
        table.add_row("Risk Amount", f"${result['risk_amount']:,.2f}")
        table.add_row("")
        table.add_row("Position Size (lots)", str(result['position_size_lots']))
        table.add_row("Position Size (units)", str(result['position_size_units']))
        table.add_row("SL Distance (pips)", str(result['sl_pips']))
        table.add_row("Risk per Lot", f"${result['risk_per_lot']:,.2f}")
        table.add_row("Actual Risk", f"${result['actual_risk_amount']:,.2f}")
        table.add_row("Margin Required", f"${result['margin_required']:,.2f}")

        if 'take_profit' in result:
            table.add_row("")
            table.add_row("Take Profit", str(result['take_profit']))
            table.add_row("TP Distance (pips)", str(result['tp_pips']))
            table.add_row("Reward:Risk", f"{result['reward_risk']}:1")
            table.add_row("R Multiple", str(result['r_multiple']))
            table.add_row("Potential Profit", f"${result['potential_profit']:,.2f}")

        self.console.print(table)

    def _display_position_plain(self, result: dict):
        if 'error' in result:
            print(f"Error: {result['error']}")
            return
        print("=" * 45)
        print("  POSITION SIZE CALCULATOR")
        print("=" * 45)
        print(f"  Balance:      ${result['account_balance']:,.2f}")
        print(f"  Risk:         {result['risk_percent']}% (${result['risk_amount']:,.2f})")
        print(f"  Size:         {result['position_size_lots']} lots ({result['position_size_units']} units)")
        print(f"  SL:           {result['sl_pips']} pips")
        print(f"  Risk/Lot:     ${result['risk_per_lot']:,.2f}")
        print(f"  Actual Risk:  ${result['actual_risk_amount']:,.2f}")
        if 'take_profit' in result:
            print(f"  TP:           {result['tp_pips']} pips")
            print(f"  R:R:          {result['reward_risk']}:1")
            print(f"  Profit:       ${result['potential_profit']:,.2f}")
        print("=" * 45)

    def _cmd_pnl(self, args: argparse.Namespace):
        result = PnLCalculator.calculate(
            entry_price=args.entry, exit_price=args.exit,
            position_size_lots=args.lots, symbol=args.symbol.upper(),
            direction=args.direction or 'long',
            commission_per_lot=args.commission or 0,
            spread_pips=args.spread or 0,
        )
        if RICH_AVAILABLE:
            self._display_pnl_rich(result)
        else:
            self._display_pnl_plain(result)

    def _display_pnl_rich(self, result: dict):
        color = "green" if result['net_pnl'] >= 0 else "red"
        table = Table(title="P&L Calculator", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Direction", result['direction'].title())
        table.add_row("Pips", str(result['pips']))
        table.add_row("Gross P&L", f"${result['gross_pnl']:,.2f}", style=color)
        table.add_row("Commission", f"(${result['commission']:,.2f})")
        table.add_row("Spread Cost", f"(${result['spread_cost']:,.2f})")
        table.add_row("Net P&L", f"${result['net_pnl']:,.2f}", style=f"bold {color}")
        table.add_row("ROI", f"{result['roi']}%")

        self.console.print(table)

    def _display_pnl_plain(self, result: dict):
        color = "+" if result['net_pnl'] >= 0 else ""
        print("=" * 45)
        print("  P&L CALCULATOR")
        print("=" * 45)
        print(f"  Direction:    {result['direction'].title()}")
        print(f"  Pips:         {result['pips']}")
        print(f"  Gross P&L:    ${result['gross_pnl']:,.2f}")
        print(f"  Commission:   (${result['commission']:,.2f})")
        print(f"  Spread Cost:  (${result['spread_cost']:,.2f})")
        print(f"  Net P&L:      ${color}{result['net_pnl']:,.2f}")
        print(f"  ROI:          {result['roi']}%")
        print("=" * 45)

    def _cmd_dashboard(self, args: argparse.Namespace):
        from regime_dashboard import RegimeDashboard
        symbol = args.symbol.upper() if args.symbol else 'EURUSD'
        timeframes = ['M15', 'H1', 'H4', 'D1']
        bars = args.bars or 100
        source = args.source or 'auto'

        data = self.connector.fetch_multi_timeframe(symbol, timeframes, bars)
        results = self.detector.detect_multi_timeframe(data)
        output = args.output or f"regime_dashboard_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        dashboard = RegimeDashboard()
        dashboard.generate(symbol, results, data, output)
        print(f"Dashboard saved to: {output}")

    def _cmd_analyze(self, args: argparse.Namespace):
        symbol = args.symbol.upper()
        source = args.source or 'auto'
        bars = args.bars or 100

        all_results = {}
        all_data = {}
        for tf in self.TIMEFRAMES:
            df = self.connector.fetch(symbol, tf, bars, source)
            if df is not None:
                all_data[tf] = df
                result = self.detector.detect(df)
                if result:
                    if not _supports_emoji():
                        result['emoji'] = ''
                    all_results[tf] = result

        if not all_results:
            print(f"No data available for {symbol}")
            return

        if RICH_AVAILABLE:
            self._display_mtf_rich(symbol, all_results)
        else:
            self._display_mtf_plain(symbol, all_results)

    def _display_mtf_rich(self, symbol: str, results: dict):
        table = Table(title=f"Multi-Timeframe Regime Analysis — {symbol}",
                      show_header=True, header_style="bold")
        table.add_column("TF", style="cyan", justify="center")
        table.add_column("Regime", justify="center")
        table.add_column("Conf", justify="center")
        table.add_column("ADX", justify="right")
        table.add_column("ATR%ile", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("Guidance", style="dim")

        for tf in ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']:
            if tf not in results:
                continue
            r = results[tf]
            ind = r['indicators']
            table.add_row(
                tf,
                f"{r['emoji']} {r['regime']}",
                f"{r['confidence']}%",
                str(ind['ADX']),
                f"{ind['ATR_Percentile']}%",
                str(ind['RSI']),
                r['description'][:50] + '...',
                style=r['color'],
            )
        self.console.print(table)

    def _display_mtf_plain(self, symbol: str, results: dict):
        print("=" * 70)
        print(f"  MULTI-TIMEFRAME REGIME ANALYSIS — {symbol}")
        print("=" * 70)
        print(f"{'TF':<5} {'Regime':<20} {'Conf':<6} {'ADX':<6} {'ATR%':<6} {'RSI':<6}")
        print("-" * 70)
        for tf in ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']:
            if tf not in results:
                continue
            r = results[tf]
            ind = r['indicators']
            print(f"{tf:<5} {r['emoji']} {r['regime']:<18} {r['confidence']}%  "
                  f"{ind['ADX']:<6} {ind['ATR_Percentile']:<5}% {ind['RSI']:<6}")
        print("=" * 70)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='capitalure',
        description='Capitalure Prime — Market Regime Detector & Trading Calculator',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p_regime = sub.add_parser('regime', help='Detect market regime for an asset')
    p_regime.add_argument('symbol', help='Symbol (e.g., EURUSD, BTCUSD)')
    p_regime.add_argument('--timeframe', '-tf', default='H1',
                          help='Timeframe: M1/M5/M15/M30/H1/H4/D1/W1')
    p_regime.add_argument('--bars', '-b', type=int, default=100,
                          help='Number of bars to analyze')
    p_regime.add_argument('--source', '-s', default='auto',
                          choices=['auto', 'yfinance', 'mt5'])

    p_pos = sub.add_parser('position', help='Calculate position size')
    p_pos.add_argument('symbol', help='Symbol')
    p_pos.add_argument('entry', type=float, help='Entry price')
    p_pos.add_argument('sl', type=float, help='Stop loss price')
    p_pos.add_argument('--tp', type=float, help='Take profit price', default=None)
    p_pos.add_argument('--balance', type=float, default=10000,
                       help='Account balance')
    p_pos.add_argument('--risk', '-r', type=float, default=1.0,
                       help='Risk percent per trade')
    p_pos.add_argument('--leverage', '-l', type=int, default=100,
                       help='Leverage')

    p_pnl = sub.add_parser('pnl', help='Calculate profit/loss for a trade')
    p_pnl.add_argument('symbol', help='Symbol')
    p_pnl.add_argument('entry', type=float, help='Entry price')
    p_pnl.add_argument('exit', type=float, help='Exit price')
    p_pnl.add_argument('lots', type=float, help='Position size in lots')
    p_pnl.add_argument('--direction', '-d', default='long',
                       choices=['long', 'short'])
    p_pnl.add_argument('--commission', '-c', type=float, default=0,
                       help='Commission per lot')
    p_pnl.add_argument('--spread', '-sp', type=float, default=0,
                       help='Spread in pips')

    p_dash = sub.add_parser('dashboard', help='Generate HTML regime dashboard')
    p_dash.add_argument('--symbol', '-s', default='EURUSD',
                        help='Symbol to analyze')
    p_dash.add_argument('--bars', '-b', type=int, default=100)
    p_dash.add_argument('--output', '-o', help='Output HTML file path')
    p_dash.add_argument('--source', default='auto',
                        choices=['auto', 'yfinance', 'mt5'])

    p_analyze = sub.add_parser('analyze', help='Multi-timeframe regime analysis')
    p_analyze.add_argument('symbol', help='Symbol')
    p_analyze.add_argument('--bars', '-b', type=int, default=100)
    p_analyze.add_argument('--source', '-s', default='auto',
                           choices=['auto', 'yfinance', 'mt5'])

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    cli = RegimeCLI()
    cli.run(args)


if __name__ == '__main__':
    main()
