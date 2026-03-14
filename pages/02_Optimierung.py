# pages/02_Optimierung.py

import streamlit as st
import optuna
import pandas as pd
from utils import get_top_30_symbols, fetch_bitget_data, calculate_strategy, run_backtest

st.set_page_config(page_title="Multi-Asset Optimierung", layout="wide")

if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Bitte zuerst auf der Hauptseite einloggen.")
    st.stop()

st.title("🔧 Multi-Asset & Multi-Timeframe Optimierung")
st.markdown("""
Wähle mehrere Symbole und Timeframes aus. Für jede Kombination wird eine eigene Optimierung gestartet.  
Die besten 5 Ergebnisse (nach Bewertungsmetrik) werden unten in einer Tabelle angezeigt.  
Mit dem Button **Übernehmen** gelangst du zurück zur Hauptseite, wo Symbol, Timeframe und die optimierten Parameter bereits eingestellt sind.
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
    'right_bars': 5,
    'max_levels': 8,
    'use_st': True,
    'use_wick': True,
    'use_bullish': True,
    'vol_len': 20,
    'vol_mult': 1.3,
    'use_vol': True,
    'adx_len': 14,
    'adx_thresh': 25,
    'use_side': False,
}

def optimize_for(symbol, timeframe):
    def objective(trial):
        params = fixed_params.copy()
        params.update({
            'st_factor': trial.suggest_float('st_factor', 1.5, 5.0, step=0.1),
            'st_period': trial.suggest_int('st_period', 5, 20),
            'zone_pct': trial.suggest_float('zone_pct', 0.2, 2.0, step=0.1),
            'wick_mult': trial.suggest_float('wick_mult', 1.2, 4.0, step=0.1),
        })
        df = fetch_bitget_data(symbol, timeframe, limit)
        if df is None or df.empty:
            return -9999
        data, _, _, _ = calculate_strategy(df, params)
        profit, _, winrate, num_trades, _ = run_backtest(data, params)  # profit in %, winrate in %
        # Kombinierte Metrik: Profit + Winrate/10
        return profit + winrate / 10

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    
    best_params = study.best_params
    params = fixed_params.copy()
    params.update(best_params)
    df = fetch_bitget_data(symbol, timeframe, limit)
    data, _, _, _ = calculate_strategy(df, params)
    profit_pct, profit_usdt, winrate, num_trades, trades_df = run_backtest(data, params)
    
    # Profitfaktor berechnen
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
        'winrate': winrate,
        'num_trades': num_trades,
        'profit_factor': profit_factor,
        'params': best_params
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
                'st_factor': res['params']['st_factor'],
                'st_period': res['params']['st_period'],
                'zone_pct': res['params']['zone_pct'],
                'wick_mult': res['params']['wick_mult'],
            })
        
        df_top = pd.DataFrame(table_data)
        st.dataframe(df_top, use_container_width=True, hide_index=True)
        
        st.subheader("Parameter übernehmen")
        st.markdown("Klicke auf **Übernehmen** für das gewünschte Ergebnis – du wirst zur Hauptseite weitergeleitet.")
        
        for i, res in enumerate(top5):
            col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 2, 2, 2, 2])
            col1.write(f"**#{i+1}**")
            col2.write(res['symbol'])
            col3.write(res['timeframe'])
            col4.write(f"{res['profit_pct']:.2f}%")
            col5.write(f"{res['winrate']:.1f}%")
            col6.write(f"{res['profit_factor']:.2f}")
            if col7.button(f"Übernehmen", key=f"btn_{i}"):
                # Alles in Session speichern
                st.session_state['optimized_symbol'] = res['symbol']
                st.session_state['optimized_timeframe'] = res['timeframe']
                st.session_state['optimized_limit'] = limit
                st.session_state['optimized_params'] = res['params']
                st.session_state['use_optimized'] = True
                st.session_state['show_optimized_message'] = True
                st.switch_page("app.py")
    else:
        st.warning("Keine Ergebnisse – bitte Einstellungen prüfen.")
