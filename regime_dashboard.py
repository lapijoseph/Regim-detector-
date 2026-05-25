import base64
import io
from datetime import datetime
from typing import Dict, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from regime_detector import RegimeDetector


class RegimeDashboard:
    REGIME_COLORS = {
        'Bull Volatile': '#ff6b35', 'Bull Quiet': '#00b894',
        'Bear Volatile': '#d63031', 'Bear Quiet': '#636e72',
        'Sideways Volatile': '#fdcb6e', 'Sideways Quiet': '#74b9ff',
    }

    def __init__(self):
        self.detector = RegimeDetector()

    def generate(self, symbol: str, results: Dict[str, dict],
                 data: Dict[str, pd.DataFrame],
                 output_path: str = 'regime_dashboard.html'):
        price_chart = self._create_price_chart(symbol, results, data)
        radar_chart = self._create_regime_radar(results)
        mtf_table = self._create_mtf_table(results)
        indicator_charts = self._create_indicator_charts(data)

        main_tf = 'H1'
        if main_tf in results:
            current = results[main_tf]
        else:
            current = list(results.values())[0] if results else None

        html = self._build_html(symbol, current, results, price_chart,
                                radar_chart, mtf_table, indicator_charts, data)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

    def _create_price_chart(self, symbol: str, results: Dict[str, dict],
                            data: Dict[str, pd.DataFrame]) -> str:
        fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=120)
        fig.suptitle(f'{symbol} — Multi-Timeframe Regime Analysis',
                     fontsize=18, fontweight='bold', y=0.98)

        timeframes_plot = [('M15', 'M15'), ('H1', 'H1'), ('H4', 'H4'), ('D1', 'D1')]
        for idx, (tf_name, tf_key) in enumerate(timeframes_plot):
            ax = axes[idx // 2][idx % 2]
            if tf_key not in data or data[tf_key] is None:
                ax.set_title(f'{tf_name} — No Data')
                continue

            df = data[tf_key].copy()
            if df.empty:
                ax.set_title(f'{tf_name} — No Data')
                continue

            self._plot_price_with_regime(ax, df, results.get(tf_key), tf_name)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        return self._fig_to_b64(fig)

    def _plot_price_with_regime(self, ax, df: pd.DataFrame,
                                 result: Optional[dict], tf_name: str):
        ax.plot(df.index, df['Close'], color='#2d3436', linewidth=1.5, label='Price')

        if 'EMA20' in df.columns:
            ax.plot(df.index, df['EMA20'], color='#e17055', linewidth=1,
                    alpha=0.7, label='EMA20')
        if 'EMA50' in df.columns:
            ax.plot(df.index, df['EMA50'], color='#0984e3', linewidth=1,
                    alpha=0.7, label='EMA50')

        if result:
            color = result['color']
            regime = result['regime']
            conf = result['confidence']
            ax.set_title(f'{tf_name} — {regime} ({conf}%)',
                         fontweight='bold', color=color, fontsize=13)
            ax.axhspan(0, 1, color=color, alpha=0.05,
                       transform=ax.get_xaxis_transform())
        else:
            ax.set_title(tf_name, fontweight='bold', fontsize=13)

        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.tick_params(axis='x', rotation=45)

    def _create_regime_radar(self, results: Dict[str, dict]) -> str:
        fig, ax = plt.subplots(figsize=(8, 8), dpi=120, subplot_kw=dict(polar=True))

        timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
        available = [tf for tf in timeframes if tf in results]
        if not available:
            plt.close(fig)
            return ''

        n = len(available)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]

        confidences = [results[tf]['confidence'] for tf in available]
        confidences += confidences[:1]
        ax.plot(angles, confidences, 'o-', linewidth=2, color='#6c5ce7')
        ax.fill(angles, confidences, alpha=0.25, color='#6c5ce7')

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(available, fontsize=11, fontweight='bold')
        ax.set_ylim(0, 100)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'], fontsize=8)
        ax.set_title('Regime Confidence Across Timeframes',
                     fontsize=14, fontweight='bold', pad=20)

        for i, tf in enumerate(available):
            r = results[tf]
            color = r['color']
            ax.annotate(f"{r['emoji']} {r['regime']}",
                        xy=(angles[i], confidences[i]),
                        fontsize=8, color=color, fontweight='bold',
                        ha='center', va='bottom')

        return self._fig_to_b64(fig)

    def _create_indicator_charts(self, data: Dict[str, pd.DataFrame]) -> str:
        fig, axes = plt.subplots(1, 3, figsize=(18, 4.5), dpi=120)

        main_df = data.get('H1')
        if main_df is None or main_df.empty:
            main_df = data.get('D1')
        if main_df is None or main_df.empty:
            plt.close(fig)
            return ''

        df = main_df.copy()

        if 'ADX' in df.columns:
            ax = axes[0]
            ax.plot(df.index, df['ADX'], color='#6c5ce7', linewidth=1.5)
            ax.axhline(20, color='#d63031', linestyle='--', alpha=0.5, label='Trend threshold')
            ax.axhline(30, color='#00b894', linestyle='--', alpha=0.5, label='Strong trend')
            ax.fill_between(df.index, 0, df['ADX'], alpha=0.2, color='#6c5ce7')
            ax.set_title('ADX (Trend Strength)', fontweight='bold')
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

        if 'ATR_Percentile' in df.columns:
            ax = axes[1]
            ax.plot(df.index, df['ATR_Percentile'], color='#e17055', linewidth=1.5)
            ax.axhline(50, color='#636e72', linestyle='--', alpha=0.5, label='Vol threshold')
            ax.fill_between(df.index, 0, df['ATR_Percentile'], alpha=0.2, color='#e17055')
            ax.set_title('ATR %ile (Volatility)', fontweight='bold')
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

        if 'BB_Width_Percentile' in df.columns:
            ax = axes[2]
            ax.plot(df.index, df['BB_Width_Percentile'], color='#0984e3', linewidth=1.5)
            ax.axhline(50, color='#636e72', linestyle='--', alpha=0.5, label='Width threshold')
            ax.fill_between(df.index, 0, df['BB_Width_Percentile'], alpha=0.2, color='#0984e3')
            ax.set_title('BB Width %ile (Expansion)', fontweight='bold')
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_b64(fig)

    def _create_mtf_table(self, results: Dict[str, dict]) -> str:
        timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
        rows = []
        for tf in timeframes:
            if tf not in results:
                continue
            r = results[tf]
            ind = r['indicators']
            rows.append({
                'tf': tf,
                'regime': r['regime'],
                'emoji': r['emoji'],
                'color': r['color'],
                'conf': r['confidence'],
                'dir_conf': r['direction_confidence'],
                'vol_conf': r['volatility_confidence'],
                'adx': ind['ADX'],
                'atr_pct': ind['ATR_Percentile'],
                'bbw_pct': ind['BB_Width_Percentile'],
                'rsi': ind['RSI'],
                'desc': r['description'],
            })
        return self._render_mtf_table_html(rows)

    def _render_mtf_table_html(self, rows: list) -> str:
        if not rows:
            return '<p>No regime data available</p>'
        html = '''<table class="mtf-table">
            <thead><tr>
                <th>TF</th><th>Regime</th><th>Conf</th>
                <th>Dir</th><th>Vol</th>
                <th>ADX</th><th>ATR%ile</th><th>BBW%ile</th><th>RSI</th>
                <th>Guidance</th>
            </tr></thead><tbody>
        '''
        for r in rows:
            html += f'''<tr style="border-left: 4px solid {r['color']}">
                <td><strong>{r['tf']}</strong></td>
                <td style="color:{r['color']};font-weight:bold">{r['emoji']} {r['regime']}</td>
                <td>{r['conf']}%</td>
                <td>{r['dir_conf']}%</td>
                <td>{r['vol_conf']}%</td>
                <td>{r['adx']}</td>
                <td>{r['atr_pct']}%</td>
                <td>{r['bbw_pct']}%</td>
                <td>{r['rsi']}</td>
                <td style="font-size:12px;color:#636e72">{r['desc'][:60]}...</td>
            </tr>'''
        html += '</tbody></table>'
        return html

    def _build_html(self, symbol: str, current: Optional[dict],
                    results: Dict[str, dict],
                    price_chart: str, radar_chart: str,
                    mtf_table: str, indicator_charts: str,
                    data: Dict[str, pd.DataFrame]) -> str:
        current_html = ''
        if current:
            ind = current['indicators']
            votes = current['votes']
            dir_best = max(votes['direction'], key=votes['direction'].get)
            vol_best = max(votes['volatility'], key=votes['volatility'].get)

            current_html = f'''
            <div class="current-regime" style="border-left:6px solid {current['color']}">
                <div class="regime-badge" style="background:{current['color']}">
                    {current['emoji']} {current['regime']}
                </div>
                <div class="regime-meta">
                    <span class="confidence">Confidence: {current['confidence']}%</span>
                    <span class="direction">Direction: {dir_best} ({current['direction_confidence']}%)</span>
                    <span class="volatility">Volatility: {vol_best} ({current['volatility_confidence']}%)</span>
                </div>
                <div class="regime-desc">{current['description']}</div>
                <div class="indicator-grid">
                    <div class="ind-item"><label>Price</label><span>{ind['Price']}</span></div>
                    <div class="ind-item"><label>EMA20</label><span>{ind['EMA20']}</span></div>
                    <div class="ind-item"><label>ADX</label><span>{ind['ADX']}</span></div>
                    <div class="ind-item"><label>ATR %ile</label><span>{ind['ATR_Percentile']}%</span></div>
                    <div class="ind-item"><label>BBW %ile</label><span>{ind['BB_Width_Percentile']}%</span></div>
                    <div class="ind-item"><label>MACD</label><span>{ind['MACD']}</span></div>
                    <div class="ind-item"><label>RSI</label><span>{ind['RSI']}</span></div>
                    <div class="ind-item"><label>MACD Signal</label><span>{ind['MACD_Signal']}</span></div>
                </div>
            </div>'''

        legend_items = ''.join(
            f'<span class="legend-item"><span class="legend-dot" style="background:{c}"></span>{r}</span>'
            for r, c in self.REGIME_COLORS.items()
        )

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capitalure Regime Dashboard — {symbol}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:#0a0a0f; color:#dfe6e9; padding:20px; }}
.container {{ max-width:1400px; margin:0 auto; }}
.header {{ text-align:center; padding:30px 0; }}
.header h1 {{ font-size:28px; background:linear-gradient(135deg,#6c5ce7,#00b894); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.header .subtitle {{ color:#636e72; font-size:14px; margin-top:5px; }}
.header .symbol {{ font-size:22px; color:#dfe6e9; font-weight:bold; }}
.legend {{ display:flex; flex-wrap:wrap; gap:12px; justify-content:center; margin:20px 0; padding:12px; background:#1a1a2e; border-radius:10px; }}
.legend-item {{ display:flex; align-items:center; gap:6px; font-size:12px; color:#b2bec3; }}
.legend-dot {{ width:12px; height:12px; border-radius:50%; display:inline-block; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:20px 0; }}
.grid-full {{ grid-column:1/-1; }}
.card {{ background:#1a1a2e; border-radius:12px; padding:20px; border:1px solid #2d2d44; }}
.card h2 {{ font-size:16px; margin-bottom:15px; color:#b2bec3; text-transform:uppercase; letter-spacing:1px; }}
.current-regime {{ background:#1a1a2e; border-radius:12px; padding:25px; margin-bottom:20px; border:1px solid #2d2d44; }}
.regime-badge {{ display:inline-block; padding:10px 24px; border-radius:25px; color:#fff; font-size:20px; font-weight:bold; margin-bottom:12px; }}
.regime-meta {{ display:flex; gap:20px; margin:10px 0; flex-wrap:wrap; }}
.regime-meta span {{ font-size:14px; color:#b2bec3; }}
.regime-meta .confidence {{ color:#00b894; font-weight:bold; }}
.regime-desc {{ font-size:14px; color:#b2bec3; margin:10px 0; line-height:1.5; }}
.indicator-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-top:15px; }}
.ind-item {{ background:#0a0a1f; padding:10px 12px; border-radius:8px; }}
.ind-item label {{ display:block; font-size:11px; color:#636e72; text-transform:uppercase; }}
.ind-item span {{ font-size:15px; font-weight:bold; color:#dfe6e9; font-family:'Consolas',monospace; }}
.mtf-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.mtf-table th {{ text-align:left; padding:10px 8px; border-bottom:2px solid #2d2d44; color:#636e72; font-size:11px; text-transform:uppercase; }}
.mtf-table td {{ padding:10px 8px; border-bottom:1px solid #2d2d44; }}
.mtf-table tbody tr:hover {{ background:#2d2d44; }}
.chart-img {{ width:100%; border-radius:8px; }}
.tabs {{ display:flex; gap:10px; margin-bottom:20px; }}
.tab {{ padding:8px 20px; border-radius:20px; border:1px solid #2d2d44; background:transparent; color:#b2bec3; cursor:pointer; font-size:13px; }}
.tab.active {{ background:#6c5ce7; border-color:#6c5ce7; color:#fff; }}
@media(max-width:900px){{ .grid {{ grid-template-columns:1fr; }} }}
.footer {{ text-align:center; padding:30px 0; color:#636e72; font-size:12px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚡ CAPITALURE PRIME</h1>
        <div class="symbol">{symbol}</div>
        <div class="subtitle">Regime Detection Dashboard — Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>
    <div class="legend">{legend_items}</div>
    {current_html}
    <div class="grid">
        <div class="card grid-full">
            <h2>Price Charts by Timeframe</h2>
            <img class="chart-img" src="data:image/png;base64,{price_chart}" alt="Price Charts">
        </div>
    </div>
    <div class="grid">
        <div class="card">
            <h2>Regime Confidence Radar</h2>
            <img class="chart-img" src="data:image/png;base64,{radar_chart}" alt="Regime Radar">
        </div>
        <div class="card">
            <h2>Indicator Overview (H1/D1)</h2>
            <img class="chart-img" src="data:image/png;base64,{indicator_charts}" alt="Indicators">
        </div>
    </div>
    <div class="card grid-full">
        <h2>Multi-Timeframe Regime Matrix</h2>
        {mtf_table}
    </div>
    <div class="footer">
        Capitalure Prime v1.0 — Data: {'MT5 / yfinance'} — Not financial advice
    </div>
</div>
</body>
</html>'''

    @staticmethod
    def _fig_to_b64(fig) -> str:
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    facecolor='#0a0a0f', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
