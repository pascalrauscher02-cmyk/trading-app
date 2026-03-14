# app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from utils import get_top_30_symbols, fetch_bitget_data, calculate_strategy, run_backtest

# --- Passwortschutz ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Login")
    password_input = st.text_input("Passwort", type="password")
    if st.button("Einloggen"):
        if "password" in st.secrets and password_input == st.secrets["password"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Falsches Passwort")
    st.stop()

st.set_page_config(page_title="S/R + Wick Rejection + Supertrend (ATR-basiert)", layout="wide")

def main():
    st.title("📈 Dynamische S/R + Wick Rejection + Supertrend (ATR-basiert)")

    if st.session_state.get('show_optimized_message', False):
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            st.success("✅ Optimierte Parameter wurden übernommen!")
        with col2:
            if st.button("✖", key="close_msg"):
                st.session_state['show_optimized_message'] = False
                st.rerun()

    # Sidebar
    st.sidebar.header("Asset & Daten")
    symbols = get_top_30_symbols()
    # Standard: gespeichertes Symbol oder erstes
    default_symbol = st.session_state.get('optimized_symbol', symbols[0] if symbols else 'BTC/USDT')
    # Falls das gespeicherte Symbol nicht mehr in der Liste ist (z.B. nach Update), Fallback
    if default_symbol not in symbols:
        default_symbol = symbols[0]
    symbol = st.sidebar.selectbox("Symbol", symbols, index=symbols.index(default_symbol))

    timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
    default_tf = st.session_state.get('optimized_timeframe', '15m')
    if default_tf not in timeframes:
        default_tf = '15m'
    timeframe = st.sidebar.selectbox("Timeframe", timeframes, index=timeframes.index(default_tf))

    default_limit = st.session_state.get('optimized_limit', 1500)
    limit = st.sidebar.slider("Anzahl Kerzen", min_value=500, max_value=5000, value=default_limit, step=100)

    capital = st.sidebar.number_input("Handelskapital (USDT)", min_value=100, max_value=1000000, value=1000, step=100)
    live_mode = st.sidebar.checkbox("Live-Update alle 30 Sekunden", value=True)

    # Strategie-Parameter
    st.sidebar.header("Strategie-Einstellungen")
    if 'optimized_params' in st.session_state:
        st.sidebar.success("Optimierte Parameter verfügbar!")
        if st.sidebar.button("Optimierte Parameter übernehmen"):
            st.session_state['use_optimized'] = True
            st.rerun()

    def get_param(key, default):
        if st.session_state.get('use_optimized', False) and key in st.session_state.get('optimized_params', {}):
            return st.session_state['optimized_params'][key]
        else:
            return default

    params = {
        # Supertrend
        'st_factor': st.sidebar.number_input("Supertrend Multiplier", 1.0, 20.0,
                                              value=get_param('st_factor', 10.0), step=0.5),
        'st_period': st.sidebar.number_input("Supertrend Periode", 1, 50,
                                              value=get_param('st_period', 8), step=1),
        'use_st': st.sidebar.checkbox("Supertrend als Filter + Exit",
                                       value=get_param('use_st', True)),
        # S/R Pivots
        'left_bars': st.sidebar.number_input("Pivot Left Bars", 1, 20,
                                              value=get_param('left_bars', 5)),
        'right_bars': st.sidebar.number_input("Pivot Right Bars", 1, 20,
                                               value=get_param('right_bars', 6)),
        'max_levels': st.sidebar.number_input("Max. S/R Levels", 1, 20,
                                               value=get_param('max_levels', 4)),
        'atr_period': st.sidebar.number_input("ATR Periode (für Zone)", 1, 50,
                                               value=get_param('atr_period', 8)),
        'zone_atr_mult': st.sidebar.number_input("Zone-Toleranz (ATR x)", 0.1, 5.0,
                                                  value=get_param('zone_atr_mult', 0.4), step=0.1),
        # Wick
        'wick_mult': st.sidebar.number_input("Wick Stärke (× Body)", 1.0, 10.0,
                                              value=get_param('wick_mult', 6.0), step=0.5),
        'use_wick': st.sidebar.checkbox("Wick Rejection prüfen",
                                         value=get_param('use_wick', True)),
        'use_bullish': st.sidebar.checkbox("Bullische Kerze (close>open) bei Long",
                                            value=get_param('use_bullish', False)),
        # Volume
        'vol_len': st.sidebar.number_input("Volume SMA Länge", 1, 100,
                                            value=get_param('vol_len', 15)),
        'vol_mult': st.sidebar.number_input("Volume Multiplier", 1.0, 5.0,
                                             value=get_param('vol_mult', 1.3), step=0.1),
        'use_vol': st.sidebar.checkbox("Volume-Filter",
                                        value=get_param('use_vol', True)),
        # ADX / Seitwärts
        'adx_len': st.sidebar.number_input("ADX Länge", 1, 50,
                                            value=get_param('adx_len', 9)),
        'adx_thresh': st.sidebar.number_input("ADX Threshold (unter = Seitwärts)", 1, 100,
                                               value=get_param('adx_thresh', 25)),
        'use_side': st.sidebar.checkbox("Seitwärts-Filter (keine Trades bei low ADX)",
                                         value=get_param('use_side', False)),
    }

    if st.session_state.get('use_optimized', False):
        st.session_state['use_optimized'] = False
        st.session_state['show_optimized_message'] = True

    # Daten laden & Strategie berechnen
    df = fetch_bitget_data(symbol, timeframe, limit)
    data, st_col, sup_levels, res_levels = calculate_strategy(df, params)
    profit_pct, profit_usdt, winrate, num_trades, trades_df = run_backtest(data, params, capital)

    # In Session speichern für Performance-Seite
    st.session_state['trades_df'] = trades_df
    st.session_state['data'] = data

    # Metriken
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Gesamtprofit %", f"{profit_pct:.2f}%")
    col2.metric("Gesamtprofit (USDT)", f"{profit_usdt:.2f} USDT")
    col3.metric("Win-Rate", f"{winrate:.1f}%")
    col4.metric("Anzahl Trades", num_trades)
    col5.metric("Aktuelles Symbol", f"{symbol} ({timeframe})")

    # Chart
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25])
    fig.add_trace(go.Candlestick(
        x=data['timestamp'], open=data['open'], high=data['high'],
        low=data['low'], close=data['close'], name='Price'
    ), row=1, col=1)

    if st_col and st_col in data.columns:
        fig.add_trace(go.Scatter(
            x=data['timestamp'], y=data[st_col],
            line=dict(color='orange', width=2.5), name='Supertrend'
        ), row=1, col=1)

    # S/R-Linien
    for lvl in sup_levels[-params['max_levels']:]:
        fig.add_hline(y=lvl, line_dash="dash", line_color="lime", opacity=0.6)
    for lvl in res_levels[-params['max_levels']:]:
        fig.add_hline(y=lvl, line_dash="dash", line_color="red", opacity=0.6)

    longs = data[data['long_cond']]
    shorts = data[data['short_cond']]

    fig.add_trace(go.Scatter(
        x=longs['timestamp'], y=longs['low'] * 0.995,
        mode='markers', marker=dict(symbol='triangle-up', size=14, color='lime'),
        name='LONG'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=shorts['timestamp'], y=shorts['high'] * 1.005,
        mode='markers', marker=dict(symbol='triangle-down', size=14, color='red'),
        name='SHORT'
    ), row=1, col=1)

    vol_colors = ['lime' if c >= o else 'red' for o, c in zip(data['open'], data['close'])]
    fig.add_trace(go.Bar(x=data['timestamp'], y=data['volume'], marker_color=vol_colors, name='Volume'), row=2, col=1)

    fig.update_layout(
        height=750, template="plotly_dark",
        xaxis_rangeslider_visible=False,
        title=f"{symbol} {timeframe} – S/R + Wick + Supertrend"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Letzte Signale
    st.subheader("Letzte Signale & Begründung")
    recent_signals = data[data['reason'] != ""].tail(5)
    if recent_signals.empty:
        st.info("Keine Signale in den letzten Kerzen.")
    else:
        for _, row in recent_signals.iterrows():
            direction = "LONG" if row['long_cond'] else "SHORT"
            color = "green" if row['long_cond'] else "red"
            st.markdown(f"<span style='color:{color}'><b>{direction}</b></span> {row['timestamp'].strftime('%H:%M')} → {row['reason']}", unsafe_allow_html=True)

    # Alle Trades anzeigen
    st.subheader("📋 Vollständige Trade-Historie")
    if not trades_df.empty:
        display_df = trades_df.copy()
        display_df['time'] = display_df['time'].dt.strftime('%Y-%m-%d %H:%M')
        display_df['profit_pct'] = display_df['profit_pct'].round(2).astype(str) + ' %'
        display_df['profit_usdt'] = display_df['profit_usdt'].round(2).astype(str) + ' USDT'
        st.dataframe(display_df[['type', 'time', 'price', 'profit_pct', 'profit_usdt']],
                     use_container_width=True, hide_index=True)
    else:
        st.info("Noch keine Trades.")

    # Live-Refresh
    if live_mode:
        placeholder = st.empty()
        for seconds in range(30, 0, -1):
            placeholder.text(f"Nächstes Update in {seconds} Sekunden")
            time.sleep(1)
        placeholder.empty()
        st.rerun()

if __name__ == "__main__":
    main()
