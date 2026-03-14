# pages/02_Optimierung.py

import streamlit as st
import optuna
from utils import get_top_30_symbols, fetch_bitget_data, calculate_strategy, run_backtest

st.set_page_config(page_title="Parameter-Optimierung", layout="wide")

st.title("🔧 Automatische Parameter-Optimierung")

if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Bitte zuerst auf der Hauptseite einloggen.")
    st.stop()

st.markdown("""
Hier kannst du die Strategie-Parameter automatisch optimieren lassen.
Optuna sucht nach der Kombination, die den Gesamtgewinn maximiert.
""")

symbol = st.selectbox("Symbol", get_top_30_symbols())
n_trials = st.number_input("Anzahl Optimierungsdurchläufe", min_value=10, max_value=500, value=50, step=10)

# Feste Parameter (nicht optimiert)
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

def objective(trial):
    params = fixed_params.copy()
    params.update({
        'st_factor': trial.suggest_float('st_factor', 1.5, 5.0, step=0.1),
        'st_period': trial.suggest_int('st_period', 5, 20),
        'zone_pct': trial.suggest_float('zone_pct', 0.2, 2.0, step=0.1),
        'wick_mult': trial.suggest_float('wick_mult', 1.2, 4.0, step=0.1),
    })
    df = fetch_bitget_data(symbol, limit=1500)
    data, _, _, _ = calculate_strategy(df, params)
    profit, winrate, num_trades, _ = run_backtest(data, params)
    # Kombinierte Metrik: Profit + Winrate/10 (um auch gute Winrate zu belohnen)
    return profit + winrate / 10

if st.button("Optimierung starten"):
    with st.spinner("Optimiere... (das kann einige Minuten dauern)"):
        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    st.success("Optimierung abgeschlossen!")
    st.subheader("Beste gefundene Parameter")
    st.json(study.best_params)
    st.write(f"Bester Zielwert (Profit + Winrate/10): {study.best_value:.2f}")

    # Button zum Übernehmen der besten Parameter in die Hauptsession
    if st.button("Diese Parameter in der Hauptseite verwenden"):
        # Speichere die Parameter in st.session_state, damit Hauptseite sie nutzen kann
        st.session_state['optimized_params'] = study.best_params
        st.success("Parameter wurden gespeichert. Gehe zurück zur Hauptseite und lade sie dort.")
