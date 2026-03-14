# pages/03_Performance.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Performance-Details", layout="wide")

if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Bitte zuerst auf der Hauptseite einloggen.")
    st.stop()

st.title("📊 Detaillierte Performance")

if 'trades_df' not in st.session_state or st.session_state['trades_df'].empty:
    st.info("Noch keine Trades vorhanden. Führe zuerst einen Backtest auf der Hauptseite aus.")
    st.stop()

trades_df = st.session_state['trades_df']
data = st.session_state.get('data', None)

st.subheader("Trade-Liste")
display_df = trades_df.copy()
display_df['time'] = display_df['time'].dt.strftime('%Y-%m-%d %H:%M')
display_df['profit_pct'] = display_df['profit_pct'].round(2)
display_df['profit_usdt'] = display_df['profit_usdt'].round(2)
st.dataframe(display_df[['type', 'time', 'price', 'profit_pct', 'profit_usdt']], use_container_width=True)

closed = trades_df[trades_df['type'].str.contains('Exit')]
if not closed.empty:
    total_profit_usdt = closed['profit_usdt'].sum()
    total_profit_pct = (total_profit_usdt / 1000) * 100
    win_rate = (closed['profit_pct'] > 0).mean() * 100
    avg_win = closed[closed['profit_pct'] > 0]['profit_pct'].mean() if any(closed['profit_pct'] > 0) else 0
    avg_loss = closed[closed['profit_pct'] < 0]['profit_pct'].mean() if any(closed['profit_pct'] < 0) else 0
    gains = closed[closed['profit_pct'] > 0]['profit_pct'].sum()
    losses = abs(closed[closed['profit_pct'] < 0]['profit_pct'].sum())
    profit_factor = gains / losses if losses != 0 else float('inf')

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Gesamtprofit USDT", f"{total_profit_usdt:.2f}")
    col2.metric("Win-Rate", f"{win_rate:.1f}%")
    col3.metric("Ø Gewinn %", f"{avg_win:.2f}%" if avg_win else "-")
    col4.metric("Ø Verlust %", f"{avg_loss:.2f}%" if avg_loss else "-")
    col5.metric("Profit Factor", f"{profit_factor:.2f}")

if data is not None and not trades_df.empty:
    closed = trades_df[trades_df['type'].str.contains('Exit')].copy()
    closed = closed.sort_values('time')
    closed['cum_profit'] = closed['profit_usdt'].cumsum()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=closed['time'], y=closed['cum_profit'], mode='lines+markers', name='Equity (USDT)'))
    fig.update_layout(title='Equity-Kurve (kumulierter Gewinn in USDT)', xaxis_title='Datum', yaxis_title='Gewinn (USDT)')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Für die Equity-Kurve werden zusätzliche Daten benötigt.")
