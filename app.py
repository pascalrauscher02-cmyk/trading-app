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

# --- Haupt-App ---
st.set_page_config(page_title="S/R + Wick Rejection + Supertrend", layout="wide")

def main():
    st.title("S/R + Wick Rejection + Supertrend (ohne ATR)")

    # Sidebar – Assets & Live
    st.sidebar.header("Asset & Live-Modus")
    symbols = get_top_30_symbols()
    symbol = st.sidebar.selectbox("Symbol", symbols, index=0 if symbols else 0)
    live_mode = st.sidebar.checkbox("Live-Update alle 30 Sekunden", value=True)

    # Parameter
    st.sidebar.header("Strategie-Einstellungen")

    # Prüfen, ob optimierte Parameter in der Session vorhanden sind
    if 'optimized_params' in st.session_state:
        st.sidebar.success("Optimierte Parameter verfügbar!")
        if st.sidebar.button("Optimierte Parameter übernehmen"):
            st.session_state['use_optimized'] = True
            st.rerun()

    # Funktion zum Holen eines Parameters mit Priorität: erst optimierte, dann User-Input
    def get_param(key, default):
        if st.session_state.get('use_optimized', False) and key in st.session_state.get('optimized_params', {}):
            return st.session_state['optimized_params'][key]
        else:
            return default

    # Input-Felder mit dynamischen Defaults
    params = {
        'st_factor': st.sidebar.number_input("Supertrend Multiplier", 1.0, 6.0,
                                              value=get_param('st_factor', 3.0), step=0.1),
        'st_period': st.sidebar.number_input("Supertrend Periode", 5, 30,
                                              value=get_param('st_period', 10), step=1),
        'use_st': st.sidebar.checkbox("Supertrend als Filter + Exit",
                                       value=get_param('use_st', True)),
        'left_bars': st.sidebar.number_input("Pivot Left Bars", 3, 20,
                                              value=get_param('left_bars', 5)),
        'right_bars': st.sidebar.number_input("Pivot Right Bars", 3, 20,
                                               value=get_param('right_bars', 5)),
        'max_levels': st.sidebar.number_input("Max. historische Levels", 3, 20,
                                               value=get_param('max_levels', 8)),
        'zone_pct': st.sidebar.number_input("S/R-Zone Breite (%)", 0.1, 3.0,
                                             value=get_param('zone_pct', 0.6), step=0.05),
        'wick_mult': st.sidebar.number_input("Wick × Body", 1.0, 5.0,
                                              value=get_param('wick_mult', 2.0), step=0.1),
        'use_wick': st.sidebar.checkbox("Wick Rejection prüfen",
                                         value=get_param('use_wick', True)),
        'use_bullish': st.sidebar.checkbox("Kerzenrichtung prüfen",
                                            value=get_param('use_bullish', True)),
        'vol_len': st.sidebar.number_input("Volumen-SMA Länge", 10, 60,
                                            value=get_param('vol_len', 20)),
        'vol_mult': st.sidebar.number_input("Volumen-Multiplikator", 1.0, 3.0,
                                             value=get_param('vol_mult', 1.3), step=0.1),
        'use_vol': st.sidebar.checkbox("Hohes Volumen erforderlich",
                                        value=get_param('use_vol', True)),
        'adx_len': st.sidebar.number_input("ADX Periode", 8, 25,
                                            value=get_param('adx_len', 14)),
        'adx_thresh': st.sidebar.number_input("ADX < = Seitwärts", 15, 40,
                                               value=get_param('adx_thresh', 25)),
        'use_side': st.sidebar.checkbox("Seitwärts-Filter (keine Trades)",
                                         value=get_param('use_side', False)),
    }

    # Nachdem die Parameter gesetzt sind, setze use_optimized zurück
    if st.session_state.get('use_optimized', False):
        st.session_state['use_optimized'] = False

    # Daten laden & Strategie ausführen
    df = fetch_bitget_data(symbol)
    data, st_col, sup_levels, res_levels = calculate_strategy(df, params)

    profit, winrate, num_trades, trades_df = run_backtest(data, params)

    # Daten in Session speichern für Performance-Seite
    st.session_state['trades_df'] = trades_df
    st.session_state['data'] = data

    # Metriken
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gesamtprofit %", f"{profit:.2f}%")
    col2.metric("Win-Rate", f"{winrate:.1f}%")
    col3.metric("Anzahl Trades", num_trades)
    col4.metric("Aktuelles Symbol", symbol)

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
    for lvl in sup_levels:
        fig.add_hline(y=lvl, line_dash="dash", line_color="lime", opacity=0.6)
    for lvl in res_levels:
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

    # Volume
    vol_colors = ['lime' if c >= o else 'red' for o, c in zip(data['open'], data['close'])]
    fig.add_trace(go.Bar(x=data['timestamp'], y=data['volume'], marker_color=vol_colors, name='Volume'), row=2, col=1)

    fig.update_layout(
        height=750, template="plotly_dark",
        xaxis_rangeslider_visible=False,
        title=f"{symbol} 15m – S/R + Wick + Supertrend"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Signale + Begründung
    st.subheader("Letzte Signale & Begründung")
    recent_signals = data[data['reason'] != ""].tail(5)
    if recent_signals.empty:
        st.info("Keine Signale in den letzten Kerzen.")
    else:
        for _, row in recent_signals.iterrows():
            direction = "LONG" if row['long_cond'] else "SHORT"
            color = "green" if row['long_cond'] else "red"
            st.markdown(f"<span style='color:{color}'><b>{direction}</b></span> {row['timestamp'].strftime('%H:%M')} → {row['reason']}", unsafe_allow_html=True)

    # Trades
    st.subheader("Trade-Historie")
    if not trades_df.empty:
        display_df = trades_df.tail(15).copy()
        display_df['time'] = display_df['time'].dt.strftime('%Y-%m-%d %H:%M')
        display_df['profit_pct'] = display_df['profit_pct'].round(2).astype(str) + ' %'
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Noch keine Trades.")

    # Live-Refresh mit Countdown (weniger störend)
    if live_mode:
        placeholder = st.empty()
        for seconds in range(30, 0, -1):
            placeholder.text(f"Nächstes Update in {seconds} Sekunden")
            time.sleep(1)
        placeholder.empty()
        st.rerun()

if __name__ == "__main__":
    main()
