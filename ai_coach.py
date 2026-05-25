import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class AICoach:
    def __init__(self, journal):
        self.journal = journal

    def full_report(self, days_back: Optional[int] = None) -> Dict:
        return {
            'edge_analysis': self.edge_analysis(days_back),
            'regime_compliance': self.regime_compliance(days_back),
            'discipline_score': self.discipline_analysis(days_back),
            'pattern_mining': self.pattern_mining(days_back),
            'recommendations': self.recommendations(days_back),
        }

    def edge_analysis(self, days_back: Optional[int] = None) -> Dict:
        df = self.journal.get_trades(days_back=days_back)
        closed = df[df['result'].isin(['win', 'loss', 'breakeven'])].copy()
        total = len(closed)
        if total < 3:
            return {'status': 'insufficient_data', 'trades_needed': 3 - total}

        wins = closed[closed['result'] == 'win']
        losses = closed[closed['result'] == 'loss']
        n_wins = len(wins)
        n_losses = len(losses)
        win_rate = n_wins / total * 100 if total > 0 else 0

        avg_r_win = wins['r_multiple'].mean() if n_wins > 0 else 0
        avg_r_loss = losses['r_multiple'].abs().mean() if n_losses > 0 else 0
        avg_r_all = closed['r_multiple'].mean() if 'r_multiple' in closed.columns else 0

        total_pnl = closed['pnl'].sum() if 'pnl' in closed.columns else 0
        gross_win = wins['pnl'].sum() if n_wins > 0 else 0
        gross_loss = abs(losses['pnl'].sum()) if n_losses > 0 else 0
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else float('inf')

        expectancy = (win_rate / 100 * avg_r_win) - ((1 - win_rate / 100) * abs(avg_r_loss))
        expectancy_pnl = total_pnl / total if total > 0 else 0

        max_drawdown = self._calculate_max_drawdown(closed)

        sharpe = self._sharpe_ratio(closed)

        consecutive_wins = self._longest_streak(closed, 'win')
        consecutive_losses = self._longest_streak(closed, 'loss')

        verdicts = []
        score = 0
        if profit_factor >= 2:
            verdicts.append('✅ Profit Factor > 2.0 — Excellent edge');
            score += 2
        elif profit_factor >= 1.5:
            verdicts.append('✅ Profit Factor > 1.5 — Good edge');
            score += 1
        elif profit_factor < 1.0:
            verdicts.append('❌ Profit Factor < 1.0 — Edge is negative. Review strategy.')

        if expectancy > 0.5:
            verdicts.append(f'✅ Expectancy of {expectancy:.2f}R — Strong positive edge');
            score += 2
        elif expectancy > 0:
            verdicts.append(f'✅ Positive expectancy of {expectancy:.2f}R');
            score += 1
        else:
            verdicts.append(f'❌ Negative expectancy of {expectancy:.2f}R — You are losing edge')

        if win_rate >= 50:
            verdicts.append(f'✅ Win rate {win_rate:.0f}% — Above 50%');
            score += 1
        elif win_rate >= 40:
            verdicts.append(f'⚠️ Win rate {win_rate:.0f}% — Acceptable with good R:R');
            score += 0
        else:
            verdicts.append(f'⚠️ Win rate {win_rate:.0f}% — Below 40%, check if R:R compensates');
            score -= 1

        rating = self._rating_label(score)

        return {
            'status': 'ready',
            'total_trades': total,
            'wins': n_wins,
            'losses': n_losses,
            'win_rate': round(win_rate, 1),
            'avg_r_win': round(avg_r_win, 2),
            'avg_r_loss': round(avg_r_loss, 2),
            'avg_r_all': round(avg_r_all, 2),
            'profit_factor': profit_factor,
            'expectancy': round(expectancy, 2),
            'expectancy_pnl': round(expectancy_pnl, 2),
            'total_pnl': round(total_pnl, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe': round(sharpe, 2),
            'consecutive_wins': consecutive_wins,
            'consecutive_losses': consecutive_losses,
            'verdicts': verdicts,
            'edge_score': score,
            'edge_rating': rating,
        }

    def regime_compliance(self, days_back: Optional[int] = None) -> Dict:
        df = self.journal.get_trades(days_back=days_back)
        closed = df[df['result'].isin(['win', 'loss', 'breakeven'])].copy()
        total = len(closed)
        if total < 3 or 'regime_at_entry' not in closed.columns:
            return {'status': 'insufficient_data'}
        valid = closed[closed['regime_at_entry'].notna() & (closed['regime_at_entry'] != '')]
        if len(valid) < 3:
            return {'status': 'insufficient_regime_data'}

        best_regime = None
        best_win_rate = 0
        regime_stats = {}
        for regime in valid['regime_at_entry'].unique():
            subset = valid[valid['regime_at_entry'] == regime]
            n = len(subset)
            wins = len(subset[subset['result'] == 'win'])
            wr = wins / n * 100
            avg_r = subset['r_multiple'].mean() if 'r_multiple' in subset.columns else 0
            pnl = subset['pnl'].sum() if 'pnl' in subset.columns else 0
            regime_stats[regime] = {
                'trades': n,
                'win_rate': round(wr, 1),
                'avg_r': round(avg_r, 2),
                'pnl': round(pnl, 2),
            }
            if wr > best_win_rate and n >= 2:
                best_win_rate = wr
                best_regime = regime

        worst_regime = min(regime_stats, key=lambda r: regime_stats[r]['win_rate']) if regime_stats else None

        compliance_pct = 0
        if best_regime:
            compliant = len(valid[valid['regime_at_entry'] == best_regime])
            compliance_pct = round(compliant / len(valid) * 100, 1)

        return {
            'status': 'ready',
            'regime_stats': regime_stats,
            'best_regime': best_regime,
            'best_win_rate': round(best_win_rate, 1),
            'worst_regime': worst_regime,
            'compliance_pct': compliance_pct,
            'total_with_regime': len(valid),
        }

    def discipline_analysis(self, days_back: Optional[int] = None) -> Dict:
        df = self.journal.get_trades(days_back=days_back)
        closed = df[df['result'].isin(['win', 'loss', 'breakeven'])].copy()
        total = len(closed)
        if total < 3:
            return {'status': 'insufficient_data'}

        avg_discipline = closed['discipline_rating'].mean() if 'discipline_rating' in closed.columns else 0

        deviation_score = self._calculate_deviation(closed)

        premature_exits = 0
        if 'r_multiple' in closed.columns and 'take_profit' in closed.columns and 'stop_loss' in closed.columns:
            for _, t in closed.iterrows():
                if t['take_profit'] and t['stop_loss']:
                    target_r = abs(t['take_profit'] - t['entry_price']) / abs(t['stop_loss'] - t['entry_price'])
                    actual_r = abs(t['r_multiple']) if pd.notna(t['r_multiple']) else 0
                    if t['result'] == 'loss' and actual_r < target_r * 0.5 and actual_r > 0:
                        premature_exits += 1

        verdicts = []
        score = round(avg_discipline)
        if avg_discipline >= 8:
            verdicts.append(f'✅ Discipline rating {avg_discipline:.1f}/10 — Excellent')
        elif avg_discipline >= 6:
            verdicts.append(f'⚠️ Discipline rating {avg_discipline:.1f}/10 — Room for improvement')
        else:
            verdicts.append(f'❌ Discipline rating {avg_discipline:.1f}/10 — Needs serious work')

        return {
            'status': 'ready',
            'avg_discipline': round(avg_discipline, 1),
            'deviation_score': round(deviation_score, 1),
            'premature_exits': premature_exits,
            'verdicts': verdicts,
            'discipline_score': score,
        }

    def pattern_mining(self, days_back: Optional[int] = None) -> Dict:
        df = self.journal.get_trades(days_back=days_back)
        closed = df[df['result'].isin(['win', 'loss', 'breakeven'])].copy()
        total = len(closed)
        if total < 5:
            return {'status': 'insufficient_data'}

        patterns = {}

        if 'session' in closed.columns:
            session_stats = {}
            for sess in closed['session'].unique():
                if not sess:
                    continue
                sub = closed[closed['session'] == sess]
                wins = len(sub[sub['result'] == 'win'])
                session_stats[sess] = {
                    'trades': len(sub),
                    'win_rate': round(wins / len(sub) * 100, 1),
                    'pnl': round(sub['pnl'].sum(), 2),
                }
            if session_stats:
                patterns['session'] = session_stats

        symbol_stats = {}
        for sym in closed['symbol'].unique():
            sub = closed[closed['symbol'] == sym]
            if len(sub) >= 2:
                wins = len(sub[sub['result'] == 'win'])
                symbol_stats[sym] = {
                    'trades': len(sub),
                    'win_rate': round(wins / len(sub) * 100, 1),
                    'pnl': round(sub['pnl'].sum(), 2),
                }
        if symbol_stats:
            patterns['symbol'] = symbol_stats

        direction_stats = {}
        for direction in ['long', 'short']:
            sub = closed[closed['direction'] == direction]
            if len(sub) >= 2:
                wins = len(sub[sub['result'] == 'win'])
                direction_stats[direction] = {
                    'trades': len(sub),
                    'win_rate': round(wins / len(sub) * 100, 1),
                    'pnl': round(sub['pnl'].sum(), 2),
                }
        if direction_stats:
            patterns['direction'] = direction_stats

        if 'strategy' in closed.columns:
            strat_stats = {}
            for strat in closed['strategy'].unique():
                if not strat:
                    continue
                sub = closed[closed['strategy'] == strat]
                if len(sub) >= 2:
                    wins = len(sub[sub['result'] == 'win'])
                    strat_stats[strat] = {
                        'trades': len(sub),
                        'win_rate': round(wins / len(sub) * 100, 1),
                        'pnl': round(sub['pnl'].sum(), 2),
                    }
            if strat_stats:
                patterns['strategy'] = strat_stats

        closed['day_of_week'] = pd.to_datetime(closed['date']).dt.day_name()
        day_stats = {}
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            sub = closed[closed['day_of_week'] == day]
            if len(sub) >= 2:
                wins = len(sub[sub['result'] == 'win'])
                day_stats[day] = {
                    'trades': len(sub),
                    'win_rate': round(wins / len(sub) * 100, 1),
                    'pnl': round(sub['pnl'].sum(), 2),
                }
        if day_stats:
            patterns['day_of_week'] = day_stats

        best_pattern = None
        best_wr = 0
        for category, stats in patterns.items():
            for name, s in stats.items():
                if s['win_rate'] > best_wr and s['trades'] >= 3:
                    best_wr = s['win_rate']
                    best_pattern = f"{category}: {name} ({s['win_rate']}% WR)"

        worst_pattern = None
        worst_wr = 100
        for category, stats in patterns.items():
            for name, s in stats.items():
                if s['win_rate'] < worst_wr and s['trades'] >= 3:
                    worst_wr = s['win_rate']
                    worst_pattern = f"{category}: {name} ({s['win_rate']}% WR)"

        return {
            'status': 'ready',
            'patterns': patterns,
            'best_pattern': best_pattern,
            'worst_pattern': worst_pattern,
        }

    def recommendations(self, days_back: Optional[int] = None) -> List[str]:
        recs = []
        edge = self.edge_analysis(days_back)
        regime = self.regime_compliance(days_back)
        discipline = self.discipline_analysis(days_back)
        patterns = self.pattern_mining(days_back)

        if edge.get('status') == 'ready':
            if edge['profit_factor'] < 1.2:
                recs.append('⚠️ **Profit Factor low**: Review your strategy. Look for higher R:R setups or improve entries.')
            if edge['win_rate'] < 40 and edge['avg_r_win'] < 2:
                recs.append('❌ **Low win rate + low R:R**: This combination destroys accounts. Target min 1:2 R:R.')
            if edge['expectancy'] < 0:
                recs.append('❌ **Negative expectancy**: Your strategy is losing money on average. Pause trading and backtest changes.')
            if edge['consecutive_losses'] >= 5:
                recs.append(f'⚠️ **{edge["consecutive_losses"]} consecutive losses**: Take a break. Review if market regime has shifted against you.')
            if edge['sharpe'] < 0.5 and edge['total_trades'] > 10:
                recs.append('⚠️ **Low Sharpe ratio**: Your returns are inconsistent. Focus on higher-probability setups.')

        if regime.get('status') == 'ready':
            best = regime.get('best_regime')
            if best:
                recs.append(f'🎯 **Best regime**: {best} ({regime["best_win_rate"]}% WR). Prioritize trades in this condition.')
            if regime['compliance_pct'] < 40:
                recs.append(f'⚠️ **Regime compliance {regime["compliance_pct"]}%**: Only {regime["compliance_pct"]}% of trades in your best regime. Filter more carefully.')
            worst = regime.get('worst_regime')
            if worst:
                recs.append(f'🚫 **Worst regime**: {worst}. Avoid trading or adjust strategy in this regime.')

        if discipline.get('status') == 'ready':
            if discipline['avg_discipline'] < 7:
                recs.append(f'📋 **Discipline {discipline["avg_discipline"]}/10**: Stick to your plan. No moving stops, no premature exits.')
            if discipline['premature_exits'] > 0:
                recs.append(f'🚩 **{discipline["premature_exits"]} premature exits**: You exited trades before they hit SL. Let the trade breathe.')

        if patterns.get('status') == 'ready':
            if patterns.get('best_pattern'):
                recs.append(f'⭐ **What works**: {patterns["best_pattern"]}. Do more of this.')
            if patterns.get('worst_pattern'):
                recs.append(f'📉 **What fails**: {patterns["worst_pattern"]}. Do less of this.')

        if not recs:
            recs.append('✅ **No major issues found**. Keep executing your edge with discipline.')

        return recs

    @staticmethod
    def _calculate_max_drawdown(df: pd.DataFrame) -> float:
        if 'pnl' not in df.columns or len(df) < 2:
            return 0
        cumulative = df.sort_values('date')['pnl'].cumsum().values
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        return float(np.max(drawdown)) if len(drawdown) > 0 else 0

    @staticmethod
    def _sharpe_ratio(df: pd.DataFrame, risk_free: float = 0.02) -> float:
        if 'pnl' not in df.columns or len(df) < 5:
            return 0
        returns = df.sort_values('date')['pnl'].values
        if len(returns) < 2 or np.std(returns) == 0:
            return 0
        return float((np.mean(returns) - risk_free / 252) / np.std(returns) * np.sqrt(252))

    @staticmethod
    def _longest_streak(df: pd.DataFrame, result_type: str) -> int:
        if 'result' not in df.columns:
            return 0
        results = df.sort_values('date')['result'].values
        max_streak = 0
        current = 0
        for r in results:
            if r == result_type:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    @staticmethod
    def _calculate_deviation(df: pd.DataFrame) -> float:
        if 'r_multiple' not in df.columns or 'stop_loss' not in df.columns or 'take_profit' not in df.columns:
            return 0
        deviations = []
        for _, t in df.iterrows():
            if t['take_profit'] and t['stop_loss']:
                expected_r = abs(t['take_profit'] - t['entry_price']) / max(abs(t['stop_loss'] - t['entry_price']), 1e-10)
                actual_r = abs(t['r_multiple']) if pd.notna(t['r_multiple']) else 0
                if expected_r > 0:
                    deviations.append(abs(actual_r - expected_r) / expected_r * 100)
        return np.mean(deviations) if deviations else 0

    @staticmethod
    def _rating_label(score: int) -> str:
        if score >= 4: return '🟢 Elite'
        if score >= 2: return '🟢 Strong'
        if score >= 0: return '🟡 Developing'
        if score >= -2: return '🟠 Needs Work'
        return '🔴 At Risk'
