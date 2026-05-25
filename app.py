import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import traceback
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mt5_connector import DataConnector
from regime_detector import RegimeDetector
from calculators import PositionSizeCalculator, PnLCalculator
from dotenv import dotenv_values


st.set_page_config(
    page_title='Capitalure Prime',
    page_icon='⚡',
    layout='wide',
    initial_sidebar_state='expanded',
)


CUSTOM_CSS = '''
<style>
    .main > div { padding: 0 1rem; }
    .stApp { background: #0a0a0f; }
    h1, h2, h3 { color: #dfe6e9 !important; }
    .stButton button {
        background: linear-gradient(135deg, #6c5ce7, #00b894);
        color: white; border: none; border-radius: 8px;
        font-weight: bold; padding: 0.5rem 2rem;
    }
    .stButton button:hover { opacity: 0.9; }
    .stTextInput input, .stSelectbox select, .stNumberInput input {
        background: #2d2d44 !important; color: #dfe6e9 !important;
        border: 1px solid #3d3d54 !important; border-radius: 6px;
    }
    label { color: #b2bec3 !important; }
    .block-container { padding-top: 1rem; }
    [data-testid="stSidebar"] { background: #1a1a2e; border-right: 1px solid #2d2d44; }
    [data-testid="stSidebar"] h2 { color: #6c5ce7 !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: #1a1a2e; padding: 8px; border-radius: 10px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 20px; color: #b2bec3; }
    .stTabs [aria-selected="true"] { background: #6c5ce7 !important; color: white !important; }
    .stDataFrame { background: #1a1a2e; border-radius: 8px; }
    .stAlert { background: #1a1a2e; border: 1px solid #2d2d44; color: #dfe6e9; }
    hr { border-color: #2d2d44; }
    .stMetric label { color: #b2bec3 !important; }
    .stMetric [data-testid="stMetricValue"] { color: #dfe6e9 !important; }
</style>
'''

REGIME_COLORS = {
    'Bull Volatile': '#ff6b35', 'Bull Quiet': '#00b894',
    'Bear Volatile': '#d63031', 'Bear Quiet': '#636e72',
    'Sideways Volatile': '#fdcb6e', 'Sideways Quiet': '#74b9ff',
}

REGIME_EMOJIS = {
    'Bull Volatile': '🔥', 'Bull Quiet': '🌿',
    'Bear Volatile': '⚡', 'Bear Quiet': '❄️',
    'Sideways Volatile': '🌀', 'Sideways Quiet': '🌊',
}

REGIME_DESCRIPTIONS = {
    'Bull Volatile': 'Strong bullish momentum with high volatility. Trend-following ideal. Widen stops.',
    'Bull Quiet': 'Steady bullish climb with low volatility. Favorable for trend trades.',
    'Bear Volatile': 'Aggressive selling with high volatility. Short entries, wide stops needed.',
    'Bear Quiet': 'Controlled bearish decline. Steady short trades with tight risk.',
    'Sideways Volatile': 'Choppy whipsaw with wide swings. High risk of false breakouts.',
    'Sideways Quiet': 'Low-activity consolidation. Mean-reversion works. Expect breakout soon.',
}


@st.cache_resource
def get_connector():
    cfg = dotenv_values()
    return DataConnector(
        mt5_login=cfg.get('MT5_LOGIN'),
        mt5_password=cfg.get('MT5_PASSWORD'),
        mt5_server=cfg.get('MT5_SERVER'),
    )


@st.cache_data(ttl=300)
def fetch_data_cached(symbol, timeframe, bars, source, login, password, server):
    conn = DataConnector(mt5_login=login, mt5_password=password, mt5_server=server)
    return conn.fetch(symbol, timeframe, bars, source)


@st.cache_data(ttl=300)
def fetch_multi_cached(symbol, bars, source, login, password, server):
    conn = DataConnector(mt5_login=login, mt5_password=password, mt5_server=server)
    timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
    return conn.fetch_multi_timeframe(symbol, timeframes, bars, source)


def safe_render(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            st.error(f'Error: {str(e)}')
            st.code(traceback.format_exc(), language='python')
    return wrapper


def regime_card_html(regime, confidence, description):
    color = REGIME_COLORS.get(regime, '#636e72')
    emoji = REGIME_EMOJIS.get(regime, '')
    return f'''
    <div style="background:{color}15; border:2px solid {color}; border-radius:16px;
                padding:24px; margin:10px 0; text-align:center;">
        <div style="font-size:52px;">{emoji}</div>
        <div style="font-size:30px; font-weight:bold; color:{color}; margin:8px 0;">
            {regime}
        </div>
        <div style="font-size:18px; color:#b2bec3;">
            Confidence: {confidence}%
        </div>
        <div style="font-size:13px; color:#636e72; margin-top:10px; line-height:1.5;">
            {description}
        </div>
    </div>'''


@safe_render
def render_regime_tab(detector):
    col1, col2 = st.columns([2, 1])

    cfg = dotenv_values()
    login = cfg.get('MT5_LOGIN', '')
    password = cfg.get('MT5_PASSWORD', '')
    server = cfg.get('MT5_SERVER', '')

    with st.sidebar:
        st.markdown('### 🔍 Query')
        symbol = st.text_input('Symbol', value=st.session_state.get('symbol', 'EURUSD')).upper()
        st.session_state.symbol = symbol
        tf_options = ['M1','M5','M15','M30','H1','H4','D1','W1']
        tf_default = tf_options.index(st.session_state.get('tf', 'H1'))
        tf = st.selectbox('Timeframe', tf_options, index=tf_default)
        st.session_state.tf = tf
        bars = st.slider('Bars', 50, 500, st.session_state.get('bars', 100))
        st.session_state.bars = bars
        source = st.selectbox('Data Source', ['auto', 'yfinance', 'mt5'],
                              index=['auto', 'yfinance', 'mt5'].index(
                                  st.session_state.get('source', 'auto')))
        st.session_state.source = source
        analyze_btn = st.button('🔍 Analyze Regime', type='primary', use_container_width=True)

    if analyze_btn or 'last_regime' not in st.session_state:
        with st.spinner(f'Analyzing {symbol} ({tf})...'):
            df = fetch_data_cached(symbol, tf, bars, source, login, password, server)
            if df is not None and len(df) > 30:
                result = detector.detect(df)
                data_mtf = fetch_multi_cached(symbol, bars, source, login, password, server)
                results_mtf = detector.detect_multi_timeframe(data_mtf)
                st.session_state.last_regime = result
                st.session_state.last_data = df
                st.session_state.mtf_results = results_mtf
                st.session_state.mtf_data = data_mtf
            else:
                st.error(f'Could not fetch data for {symbol} ({tf}). '
                        f'Tried source: {source}. Check symbol or try a different source.')
                st.session_state.pop('last_regime', None)
                return

    result = st.session_state.get('last_regime')
    if not result:
        st.info('Enter a symbol and click 🔍 Analyze Regime to begin')
        return

    with col1:
        st.markdown(f'## ⚡ {symbol} — {tf}')
        regime = result['regime']
        st.markdown(regime_card_html(regime, result['confidence'],
                   REGIME_DESCRIPTIONS.get(regime, '')), unsafe_allow_html=True)

        ind = result['indicators']
        cols = st.columns(4)
        metrics = [
            ('Price', f'{ind["Price"]:.5f}'),
            ('ADX', f'{ind["ADX"]}'),
            ('ATR %ile', f"{ind['ATR_Percentile']:.0f}%"),
            ('BBW %ile', f"{ind['BB_Width_Percentile']:.0f}%"),
            ('RSI', f'{ind["RSI"]:.0f}'),
            ('MACD', f'{ind["MACD"]:.5f}'),
            ('EMA20', f'{ind["EMA20"]:.5f}'),
            ('Signal', f'{"Bull 📈" if ind["Price"] > ind["EMA20"] else "Bear 📉"}'),
        ]
        for i, (label, val) in enumerate(metrics):
            with cols[i % 4]:
                st.metric(label, val)

    with col2:
        st.markdown('### Vote Breakdown')
        votes = result['votes']
        dir_best = max(votes['direction'], key=votes['direction'].get)
        vol_best = max(votes['volatility'], key=votes['volatility'].get)
        st.markdown(f"""
        | Metric | Votes | Result |
        |--------|-------|--------|
        | **Direction** | B:{votes['direction']['Bull']} / B:{votes['direction']['Bear']} / S:{votes['direction']['Sideways']} | **{dir_best}** ({result['direction_confidence']}%) |
        | **Volatility** | Q:{votes['volatility']['Quiet']} / V:{votes['volatility']['Volatile']} | **{vol_best}** ({result['volatility_confidence']}%) |
        """)

        mtf = st.session_state.get('mtf_results', {})
        if mtf:
            st.markdown('### Multi-Timeframe')
            mtf_rows = []
            for tf_name in ['M5','M15','M30','H1','H4','D1']:
                r = mtf.get(tf_name)
                if r:
                    mtf_rows.append({
                        'TF': tf_name,
                        'Regime': f"{REGIME_EMOJIS.get(r['regime'],'')} {r['regime']}",
                        'Conf': f"{r['confidence']}%",
                    })
            if mtf_rows:
                st.dataframe(pd.DataFrame(mtf_rows), hide_index=True, use_container_width=True)

    chart_data = st.session_state.get('last_data')
    if chart_data is not None:
        st.markdown('### Price Chart')
        fig, ax = plt.subplots(figsize=(16, 4.5), dpi=100)
        fig.patch.set_facecolor('#0a0a0f')
        ax.set_facecolor('#0a0a0f')
        ax.plot(chart_data.index, chart_data['Close'], color='#dfe6e9',
                linewidth=1.5, label='Price')
        if 'EMA20' in chart_data.columns:
            ax.plot(chart_data.index, chart_data['EMA20'], color='#e17055',
                    linewidth=1, alpha=0.7, label='EMA20')
        if 'EMA50' in chart_data.columns:
            ax.plot(chart_data.index, chart_data['EMA50'], color='#0984e3',
                    linewidth=1, alpha=0.7, label='EMA50')
        color = REGIME_COLORS.get(result['regime'], '#636e72')
        ax.fill_between(chart_data.index, chart_data['Close'].min(),
                        chart_data['Close'].max(), color=color, alpha=0.05)
        ax.legend(loc='upper left', fontsize=10, labelcolor='#b2bec3')
        ax.grid(True, alpha=0.15, color='#2d2d44')
        ax.tick_params(colors='#636e72')
        ax.set_ylabel('Price', color='#636e72')
        st.pyplot(fig)

    df = st.session_state.get('last_data')
    if df is not None:
        with st.expander('📊 Indicator Charts', expanded=False):
            fig, axes = plt.subplots(1, 3, figsize=(18, 4), dpi=100)
            fig.patch.set_facecolor('#0a0a0f')
            for ax in axes:
                ax.set_facecolor('#0a0a0f')
                ax.tick_params(colors='#636e72')
            if 'ADX' in df.columns:
                axes[0].plot(df.index, df['ADX'], color='#6c5ce7', linewidth=1.5)
                axes[0].axhline(20, color='#d63031', ls='--', alpha=0.5)
                axes[0].fill_between(df.index, 0, df['ADX'], alpha=0.2, color='#6c5ce7')
                axes[0].set_title('ADX (Trend)', color='#b2bec3', fontweight='bold')
                axes[0].grid(True, alpha=0.15, color='#2d2d44')
            if 'ATR_Percentile' in df.columns:
                axes[1].plot(df.index, df['ATR_Percentile'], color='#e17055', linewidth=1.5)
                axes[1].axhline(50, color='#636e72', ls='--', alpha=0.5)
                axes[1].fill_between(df.index, 0, df['ATR_Percentile'], alpha=0.2, color='#e17055')
                axes[1].set_title('ATR %ile (Volatility)', color='#b2bec3', fontweight='bold')
                axes[1].grid(True, alpha=0.15, color='#2d2d44')
            if 'RSI' in df.columns:
                axes[2].plot(df.index, df['RSI'], color='#00b894', linewidth=1.5)
                axes[2].axhline(70, color='#d63031', ls='--', alpha=0.5)
                axes[2].axhline(30, color='#00b894', ls='--', alpha=0.5)
                axes[2].fill_between(df.index, 30, df['RSI'], alpha=0.15, color='#00b894')
                axes[2].set_title('RSI (Momentum)', color='#b2bec3', fontweight='bold')
                axes[2].grid(True, alpha=0.15, color='#2d2d44')
            plt.tight_layout()
            st.pyplot(fig)


@safe_render
def render_calculator_tab():
    st.markdown('## 🧮 Trading Calculators')
    tab1, tab2 = st.tabs(['📐 Position Size', '💰 P&L'])

    with tab1:
        col1, col2 = st.columns([1, 1])
        with col1:
            sym = st.text_input('Symbol', value='EURUSD', key='pos_sym').upper()
            entry = st.number_input('Entry Price', value=1.1000, step=0.0001, format='%.5f', key='pos_entry')
            sl = st.number_input('Stop Loss', value=1.0950, step=0.0001, format='%.5f', key='pos_sl')
            has_tp = st.checkbox('Set Take Profit', value=True, key='pos_has_tp')
            tp = st.number_input('Take Profit', value=1.1100, step=0.0001, format='%.5f', key='pos_tp', disabled=not has_tp)
        with col2:
            balance = st.number_input('Account Balance ($)', value=10000.0, step=1000.0, format='%.2f', key='pos_bal')
            risk_pct = st.slider('Risk per Trade (%)', 0.1, 5.0, 1.0, 0.1, key='pos_risk')
            leverage = st.select_slider('Leverage', options=[1, 10, 20, 30, 50, 100, 200, 500], value=100, key='pos_lev')
            calc_btn = st.button('Calculate Position', type='primary', use_container_width=True, key='pos_btn')

        if calc_btn:
            calc = PositionSizeCalculator(account_balance=balance, risk_percent=risk_pct)
            tp_val = tp if has_tp else None
            result = calc.calculate_all(entry, sl, tp_val, sym, leverage)
            if 'error' in result:
                st.error(result['error'])
            else:
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.metric('Position Size', f"{result['position_size_lots']} lots")
                col_b.metric('Units', f"{result['position_size_units']:,}")
                col_c.metric('Risk Amount', f"${result['risk_amount']:,.2f}")
                col_d.metric('Actual Risk', f"${result['actual_risk_amount']:,.2f}")
                col_e, col_f, col_g, col_h = st.columns(4)
                col_e.metric('SL (pips)', f"{result['sl_pips']}")
                col_f.metric('Risk per Lot', f"${result['risk_per_lot']:,.2f}")
                col_g.metric('Margin Required', f"${result['margin_required']:,.2f}")
                if 'take_profit' in result:
                    col_h.metric('Reward:Risk', f"{result['reward_risk']}:1")
                if 'take_profit' in result:
                    st.success(f"**Potential Profit:** ${result['potential_profit']:,.2f} "
                              f"at {result['tp_pips']} pips ({result['reward_risk']}:1 R:R)")

    with tab2:
        col1, col2 = st.columns([1, 1])
        with col1:
            sym2 = st.text_input('Symbol', value='EURUSD', key='pnl_sym').upper()
            entry2 = st.number_input('Entry Price', value=1.1000, step=0.0001, format='%.5f', key='pnl_entry')
            exit2 = st.number_input('Exit Price', value=1.1080, step=0.0001, format='%.5f', key='pnl_exit')
        with col2:
            lots2 = st.number_input('Position Size (lots)', value=0.2, step=0.01, format='%.2f', key='pnl_lots')
            direction2 = st.selectbox('Direction', ['long', 'short'], key='pnl_dir')
            commission2 = st.number_input('Commission ($/lot)', value=0.0, step=0.5, format='%.2f', key='pnl_comm')
            spread2 = st.number_input('Spread (pips)', value=0.0, step=0.1, format='%.1f', key='pnl_spread')
            pnl_btn = st.button('Calculate P&L', type='primary', use_container_width=True, key='pnl_btn')

        if pnl_btn:
            result = PnLCalculator.calculate(
                entry_price=entry2, exit_price=exit2,
                position_size_lots=lots2, symbol=sym2,
                direction=direction2, commission_per_lot=commission2,
                spread_pips=spread2,
            )
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric('Gross P&L', f"${result['gross_pnl']:,.2f}")
            col_b.metric('Net P&L', f"${result['net_pnl']:,.2f}",
                        delta=f"{result['pips']} pips {'📈' if result['net_pnl'] >= 0 else '📉'}")
            col_c.metric('Commission', f"(${result['commission']:,.2f})")
            col_d.metric('ROI', f"{result['roi']:.2f}%")
            st.info(f"**{result['pips']} pips** "
                   f"{'✅ profit' if result['net_pnl'] >= 0 else '❌ loss'} "
                   f"on {result['direction']} position")


@safe_render
def render_dashboard_tab():
    st.markdown('## 📊 Multi-Timeframe Dashboard')
    mtf_results = st.session_state.get('mtf_results')
    mtf_data = st.session_state.get('mtf_data')

    if not mtf_results:
        st.info('Go to **🔍 Regime Detection** tab first and click Analyze Regime')
        return

    rows = []
    for tf in ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']:
        r = mtf_results.get(tf)
        if not r:
            continue
        ind = r['indicators']
        rows.append({
            'TF': tf,
            'Regime': f"{REGIME_EMOJIS.get(r['regime'],'')} {r['regime']}",
            'Conf': f"{r['confidence']}%",
            'Dir%': f"{r['direction_confidence']}%",
            'Vol%': f"{r['volatility_confidence']}%",
            'ADX': f"{ind['ADX']:.1f}",
            'ATR%ile': f"{ind['ATR_Percentile']:.0f}%",
            'RSI': f"{ind['RSI']:.0f}",
        })

    if rows:
        st.markdown('### Regime Matrix')
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.markdown('### Price Charts')
    tf_options = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']
    available_tfs = [t for t in tf_options if t in mtf_data and mtf_data[t] is not None]
    tf_to_plot = st.multiselect('Select timeframes', available_tfs, default=available_tfs[:2])

    if tf_to_plot:
        n_cols = min(len(tf_to_plot), 3)
        for i in range(0, len(tf_to_plot), n_cols):
            cols = st.columns(n_cols)
            for j, tf_name in enumerate(tf_to_plot[i:i + n_cols]):
                with cols[j]:
                    df = mtf_data.get(tf_name)
                    r = mtf_results.get(tf_name)
                    if df is not None and not df.empty:
                        color = REGIME_COLORS.get(r['regime'], '#636e72') if r else '#636e72'
                        fig, ax = plt.subplots(figsize=(6, 3), dpi=100)
                        fig.patch.set_facecolor('#0a0a0f')
                        ax.set_facecolor('#0a0a0f')
                        ax.plot(df.index, df['Close'], color='#dfe6e9', linewidth=1.5)
                        if r:
                            ax.set_title(f"{tf_name} — {r['regime']} ({r['confidence']}%)",
                                        color=color, fontweight='bold', fontsize=10)
                        ax.grid(True, alpha=0.15, color='#2d2d44')
                        ax.tick_params(colors='#636e72')
                        st.pyplot(fig)


@safe_render
def render_mtf_heatmap_tab():
    st.markdown('## 🗺️ Regime Analysis Map')
    mtf_results = st.session_state.get('mtf_results')
    if not mtf_results:
        st.info('Go to **🔍 Regime Detection** tab first and click Analyze Regime')
        return

    timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
    data = []
    for tf in timeframes:
        r = mtf_results.get(tf)
        if r:
            data.append({
                'Timeframe': tf,
                'Direction': r['direction'],
                'Volatility': r['volatility'],
                'Confidence': f"{r['confidence']}%",
            })

    if not data:
        st.warning('No multi-timeframe data available')
        return

    df = pd.DataFrame(data)
    st.dataframe(df, hide_index=True, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('#### Direction by Timeframe')
        for r in data:
            emoji = '📈' if r['Direction'] == 'Bull' else '📉' if r['Direction'] == 'Bear' else '➡️'
            st.markdown(f"**{r['Timeframe']}**: {emoji} {r['Direction']} ({r['Confidence']})")
    with col2:
        st.markdown('#### Volatility by Timeframe')
        for r in data:
            emoji = '🌊' if r['Volatility'] == 'Volatile' else '🌅'
            st.markdown(f"**{r['Timeframe']}**: {emoji} {r['Volatility']} ({r['Confidence']})")

    st.markdown('### Regime Summary')
    dir_counts = pd.Series([d['Direction'] for d in data]).value_counts()
    vol_counts = pd.Series([d['Volatility'] for d in data]).value_counts()

    cols = st.columns(2)
    with cols[0]:
        for direction in ['Bull', 'Bear', 'Sideways']:
            cnt = dir_counts.get(direction, 0)
            pct = f"{cnt/len(data)*100:.0f}%" if data else "0%"
            st.metric(f'{direction}', cnt, pct)

    with cols[1]:
        for vol in ['Quiet', 'Volatile']:
            cnt = vol_counts.get(vol, 0)
            pct = f"{cnt/len(data)*100:.0f}%" if data else "0%"
            st.metric(f'{vol}', cnt, pct)


def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div style='text-align:center; padding:10px 0;'>
        <h1 style='background:linear-gradient(135deg,#6c5ce7,#00b894);
                   -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                   font-size:38px; margin:0;'>⚡ CAPITALURE PRIME</h1>
        <p style='color:#636e72; font-size:14px; margin:0;'>
            Elite Market Regime Detector & Trading Calculator</p>
    </div>
    """, unsafe_allow_html=True)

    detector = RegimeDetector()

    tab_names = ['🔍 Regime Detection', '🧮 Calculators', '📊 Dashboard', '🗺️ Regime Map']
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_regime_tab(detector)
    with tabs[1]:
        render_calculator_tab()
    with tabs[2]:
        render_dashboard_tab()
    with tabs[3]:
        render_mtf_heatmap_tab()

    st.markdown("""
    <div style='text-align:center; padding:20px 0; color:#636e72; font-size:12px;'>
        Capitalure Prime v1.0 — Data: MT5 / yfinance — Not financial advice
    </div>
    """, unsafe_allow_html=True)


if __name__ == '__main__':
    main()
