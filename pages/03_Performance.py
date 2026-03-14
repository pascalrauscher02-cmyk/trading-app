# pages/03_Performance.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import run_backtest  # nur für Typen

st.set_page_config(page_title="Performance-Details", layout="wide")

if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Bitte zuerst auf der Hauptseite einloggen.")
    st.stop()

st.title("📊 Detaillierte Performance")

# Prüfen, ob Trades in der Session vorhanden sind (müssten von der Hauptseite gespeichert werden)
if 'trades_df' not in st.session_state:
    st.info("Bitte führe zuerst einen Backtest auf der Hauptseite aus.")
    st.stop()

trades_df = st.session_state['trades_df']
data = st.session_state.get('data', None)  # optional für Equity-Kurve

if trades_df.empty:
    st.warning("Keine Trades vorhanden.")
else:
    st.subheader("Trade-Liste")
    display_df = trades_df.copy()
    display_df['time'] = display_df['time'].dt.strftime('%Y-%m-%d %H:%M')
    display_df['profit_pct'] = display_df['profit_pct'].round(2)
    st.dataframe(display_df, use_container_width=True)

    # Kennzahlen
    closed = trades_df[trades_df['type'].str.contains('Exit')]
    if not closed.empty:
        total_profit = closed['profit_pct'].sum()
        win_rate = (closed['profit_pct'] > 0).mean() * 100
        avg_win = closed[closed['profit_pct'] > 0]['profit_pct'].mean() if any(closed['profit_pct'] > 0) else 0
        avg_loss = closed[closed['profit_pct'] < 0]['profit_pct'].mean() if any(closed['profit_pct'] < 0) else 0
        profit_factor = abs(closed[closed['profit_pct'] > 0]['profit_pct'].sum() / closed[closed['profit_pct'] < 0]['profit_pct'].sum()) if any(closed['profit_pct'] < 0) else float('inf')

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Gesamtprofit %", f"{total_profit:.2f}")
        col2.metric("Win-Rate", f"{win_rate:.1f}%")
        col3.metric("Ø Gewinn", f"{avg_win:.2f}%" if avg_win else "-")
        col4.metric("Ø Verlust", f"{avg_loss:.2f}%" if avg_loss else "-")
        col5.metric("Profit Factor", f"{profit_factor:.2f}")

    # Equity-Kurve
    if data is not None and not trades_df.empty:
        # Einfache Equity-Kurve: kumulierte Profits
        closed = trades_df[trades_df['type'].str.contains('Exit')].copy()
        closed = closed.sort_values('time')
        closed['cum_profit'] = closed['profit_pct'].cumsum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=closed['time'], y=closed['cum_profit'], mode='lines+markers', name='Equity'))
        fig.update_layout(title='Equity-Kurve (kumulierter Profit %)', xaxis_title='Datum', yaxis_title='Profit %')
        st.plotly_chart(fig, use_container_width=True)
