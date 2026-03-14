# pages/02_Optimierung.py

import streamlit as st
import optuna
import pandas as pd
from utils import get_top_30_symbols, fetch_bitget_data, calculate_strategy, run_backtest

st.set_page_config(page_title="Multi-Asset Optimierung (ATR)", layout="wide")

if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Bitte zuerst auf der Hauptseite einloggen.")
    st.stop()

st.title("🔧 Multi-Asset & Multi-Timeframe Optimierung (ATR-basiert)")
st.markdown("""
Wähle mehrere Symbole und Timeframes aus. Für jede Kombination wird eine eigene Optimierung gestartet.  
Die besten 5 Ergebnisse (nach Bewertungsmetrik) werden unten in einer Tabelle angezeigt.  
Mit **Übernehmen** gelangst du zurück zur Hauptseite, wo Symbol, Timeframe und die optimierten Parameter bereits eingestellt sind.
""")

all_symbols = get_top_30_symbols()
selected_symbols = st.multiselect("Symbole", all_symbols, default=['BTC/USDT', 'ETH/USDT'])
timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
selected_timeframes = st.multiselect("Timeframes", timeframes, default=['15m', '1h'])

limit = st.slider("Anzahl Kerzen pro Backtest", 500, 5000, 1500, 100)
n_trials = st.number_input("Optimierungsdurchläufe pro Kombination", 10, 200, 30, 10)

# Feste Parameter (werden nicht optimiert)
fixed_params = {
    'left_bars': 5,
    'right_bars': 6,
    'max_levels': 4,
    'use_st': True,
    'use_wick': True,
    'use_bullish': False,
    'use_vol': True,
    'use_side': False,
    # Diese Werte werden von der Optimierung überschrieben, aber hier als Default
    'st_factor': 10.0,
    'st_period': 8,
    'atr_period': 8,
    'zone_atr_mult': 0.4,
    'wick_mult': 6.0,
    'vol_len': 15,
    'vol_mult': 1.3,
    'adx_len': 9,
    'adx_thresh': 25,
}

def optimize_for(symbol, timeframe):
    def objective(trial):
        params = fixed_params.copy()
        params.update({
            'st_factor': trial.suggest_float('st_factor', 5.0, 20.0, step=0.5),
            'st_period': trial.suggest_int('st_period', 5, 20),
            'atr_period': trial.suggest_int('atr_period', 5, 20),
            'zone_atr_mult': trial.suggest_float('zone_atr_mult', 0.2, 2.0, step=0.1),
            'wick_mult': trial.suggest_float('wick_mult', 2.0, 10.0, step=0.5),
            'vol_len': trial.suggest_int('vol_len', 10, 30),
            'vol_mult': trial.suggest_float('vol_mult', 1.0, 2.5, step=0.1),
            'adx_len': trial.suggest_int('adx_len', 7, 20),
            'adx_thresh': trial.suggest_int('adx_thresh', 20, 35),
        })
        df = fetch_bitget_data(symbol, timeframe, limit)
        if df is None or df.empty:
            return -9999
        data, _, _, _ = calculate_strategy(df, params)
        profit_pct, _, winrate, _, _ = run_backtest(data, params)
        return profit_pct + winrate / 10

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    params = fixed_params.copy()
    params.update(best_params)
    df = fetch_bitget_data(symbol, timeframe, limit)
    data, _, _, _ = calculate_strategy(df, params)
    profit_pct, profit_usdt, winrate, num_trades, trades_df = run_backtest(data, params)

    # Profitfaktor
    if not trades_df.empty:
        closed = trades_df[trades_df['type'].str.contains('Exit')]
        if not closed.empty:
            gains = closed[closed['profit_pct'] > 0]['profit_pct'].sum()
            losses = abs(closed[closed['profit_pct'] < 0]['profit_pct'].sum())
            profit_factor = gains / losses if losses != 0 else float('inf')
        else:
            profit_factor = 0
    else:
        profit_factor = 0

    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'best_value': study.best_value,
        'profit_pct': profit_pct,
        'profit_usdt': profit_usdt,
        'winrate': winrate,
        'num_trades': num_trades,
        'profit_factor': profit_factor,
        'params': best_params,
        'trades_df': trades_df
    }

if st.button("Batch-Optimierung starten"):
    if not selected_symbols or not selected_timeframes:
        st.error("Bitte mindestens ein Symbol und ein Timeframe auswählen.")
        st.stop()

    total_combinations = len(selected_symbols) * len(selected_timeframes)
    progress_bar = st.progress(0)
    status_text = st.empty()

    results = []
    count = 0

    for sym in selected_symbols:
        for tf in selected_timeframes:
            count += 1
            status_text.text(f"Optimiere {sym} ({tf}) – {count}/{total_combinations}")
            try:
                res = optimize_for(sym, tf)
                results.append(res)
            except Exception as e:
                st.warning(f"Fehler bei {sym} ({tf}): {e}")
            progress_bar.progress(count / total_combinations)

    progress_bar.empty()
    status_text.text("Optimierung abgeschlossen!")

    if results:
        results.sort(key=lambda x: x['best_value'], reverse=True)
        top5 = results[:5]

        st.subheader("🏆 Top 5 Ergebnisse")

        # Tabelle
        table_data = []
        for i, res in enumerate(top5):
            table_data.append({
                'Rang': i+1,
                'Symbol': res['symbol'],
                'Timeframe': res['timeframe'],
                'Profit %': f"{res['profit_pct']:.2f}",
                'Winrate %': f"{res['winrate']:.1f}",
                'Trades': res['num_trades'],
                'Profit Faktor': f"{res['profit_factor']:.2f}",
                **res['params']
            })
        df_top = pd.DataFrame(table_data)
        st.dataframe(df_top, use_container_width=True, hide_index=True)

        st.subheader("Details und Übernahme")
        for i, res in enumerate(top5):
            with st.expander(f"#{i+1}: {res['symbol']} {res['timeframe']} – Profit: {res['profit_pct']:.2f}%", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Winrate", f"{res['winrate']:.1f}%")
                    st.metric("Trades", res['num_trades'])
                with col2:
                    st.metric("Profit Faktor", f"{res['profit_factor']:.2f}")
                    st.metric("Gesamtprofit USDT", f"{res['profit_usdt']:.2f}")
                with col3:
                    st.write("Optimierte Parameter:")
                    st.json(res['params'])

                # Trades anzeigen
                if st.button(f"Trades für #{i+1} anzeigen", key=f"show_trades_{i}"):
                    st.subheader(f"Trade-Liste für {res['symbol']} {res['timeframe']}")
                    if not res['trades_df'].empty:
                        display = res['trades_df'].copy()
                        display['time'] = display['time'].dt.strftime('%Y-%m-%d %H:%M')
                        display['profit_pct'] = display['profit_pct'].round(2).astype(str) + ' %'
                        display['profit_usdt'] = display['profit_usdt'].round(2).astype(str) + ' USDT'
                        st.dataframe(display[['type', 'time', 'price', 'profit_pct', 'profit_usdt']],
                                     use_container_width=True, hide_index=True)
                    else:
                        st.info("Keine Trades.")

                # Übernehmen-Button
                if st.button(f"Übernehmen #{i+1}", key=f"take_{i}"):
                    # Alle relevanten Daten in die Session schreiben
                    st.session_state['optimized_symbol'] = res['symbol']
                    st.session_state['optimized_timeframe'] = res['timeframe']
                    st.session_state['optimized_limit'] = limit
                    st.session_state['optimized_params'] = res['params']
                    st.session_state['use_optimized'] = True
                    st.session_state['show_optimized_message'] = True
                    # Zur Hauptseite wechseln
                    st.switch_page("app.py")
    else:
        st.warning("Keine Ergebnisse – bitte Einstellungen prüfen.")
