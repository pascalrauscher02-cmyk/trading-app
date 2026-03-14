# utils.py

import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np

@st.cache_data(ttl=300)
def get_top_30_symbols():
    try:
        exchange = ccxt.bitget()
        tickers = exchange.fetch_tickers()
        usdt = {k: v for k, v in tickers.items() if k.endswith('/USDT')}
        sorted_pairs = sorted(usdt.items(), key=lambda x: x[1].get('quoteVolume', 0) or 0, reverse=True)
        return [sym for sym, _ in sorted_pairs[:30]]
    except Exception as e:
        st.warning(f"Top-Symbole konnten nicht geladen werden: {e}")
        return [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'BNB/USDT', 'DOGE/USDT',
            'ADA/USDT', 'TRX/USDT', 'AVAX/USDT', 'TON/USDT', 'SHIB/USDT', 'LINK/USDT',
            'DOT/USDT', 'MATIC/USDT', 'LTC/USDT', 'BCH/USDT', 'NEAR/USDT', 'UNI/USDT'
        ]

@st.cache_data(ttl=30)
def fetch_bitget_data(symbol='BTC/USDT', timeframe='15m', limit=1500):
    try:
        exchange = ccxt.bitget()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"Daten-Ladefehler für {symbol} ({timeframe}): {e}")
        return None

def calculate_strategy(df, params):
    if df is None or df.empty:
        st.warning("Keine Daten verfügbar.")
        return pd.DataFrame(), None, [], []

    data = df.copy()

    # --- ATR (für S/R-Zonen) ---
    try:
        data['atr'] = ta.atr(data['high'], data['low'], data['close'], length=params['atr_period'])
    except:
        data['atr'] = 0.0  # Fallback

    # --- Supertrend ---
    st_col = None
    if len(data) >= params['st_period'] and params['use_st']:
        try:
            st_df = data.ta.supertrend(period=params['st_period'], multiplier=params['st_factor'])
            if st_df is not None and not st_df.empty:
                trend_cols = [c for c in st_df.columns if c.startswith('SUPERT_')]
                dir_cols = [c for c in st_df.columns if c.startswith('SUPERTd_')]
                if trend_cols and dir_cols:
                    st_col = trend_cols[0]
                    dir_col = dir_cols[0]
                    data = pd.concat([data, st_df[[st_col, dir_col]]], axis=1)
                    data['bullish_trend'] = data[dir_col] < 0
                    data['bearish_trend'] = data[dir_col] > 0
                else:
                    data['bullish_trend'] = False
                    data['bearish_trend'] = False
            else:
                data['bullish_trend'] = False
                data['bearish_trend'] = False
        except Exception as e:
            data['bullish_trend'] = False
            data['bearish_trend'] = False
    else:
        data['bullish_trend'] = False
        data['bearish_trend'] = False

    # --- Volume SMA ---
    try:
        data.ta.sma(close='volume', length=params['vol_len'], append=True)
        vol_sma_col = next((c for c in data.columns if f"SMA_{params['vol_len']}" in c), None)
        data['high_volume'] = data['volume'] > data[vol_sma_col] * params['vol_mult'] if vol_sma_col else False
    except:
        data['high_volume'] = False

    # --- ADX ---
    try:
        adx_df = data.ta.adx(length=params['adx_len'])
        adx_col = next((c for c in adx_df.columns if c.startswith('ADX_')), None)
        if adx_col:
            data[adx_col] = adx_df[adx_col]
            data['in_sideways'] = data[adx_col] < params['adx_thresh']
        else:
            data['in_sideways'] = True
    except:
        data['in_sideways'] = True

    # --- Wick & Kerzen ---
    data['body'] = abs(data['close'] - data['open'])
    data['lower_wick'] = data[['open', 'close']].min(axis=1) - data['low']
    data['upper_wick'] = data['high'] - data[['open', 'close']].max(axis=1)
    data['lower_rejection'] = data['lower_wick'] > (data['body'] * params['wick_mult'])
    data['upper_rejection'] = data['upper_wick'] > (data['body'] * params['wick_mult'])
    data['is_bullish_candle'] = data['close'] > data['open']

    # --- Dynamische S/R Level (Pivot-basiert) ---
    sup_levels = []      # Liste der aktuellen Support-Level (Preise)
    res_levels = []      # Liste der aktuellen Resistance-Level (Preise)
    sup_indices = []     # Bar-Index, an dem das Level erstellt wurde (für FIFO)
    res_indices = []

    window = params['left_bars'] + params['right_bars'] + 1
    # Pivot-Low: Tiefstpreis im Fenster
    data['pivot_low'] = data['low'] == data['low'].rolling(window=window, center=False).min()
    data['pivot_high'] = data['high'] == data['high'].rolling(window=window, center=False).max()
    data['pivot_low'] = data['pivot_low'].fillna(False)
    data['pivot_high'] = data['pivot_high'].fillna(False)

    # Arrays für vektorisierte Näheprüfung vorbereiten
    near_support = np.zeros(len(data), dtype=bool)
    near_resistance = np.zeros(len(data), dtype=bool)

    # Wir durchlaufen die Daten, um Level zu sammeln und gleichzeitig die Nähe zu prüfen
    # (geht nicht vollständig vektorisiert, aber die Schleife ist nur über die Anzahl der Level, nicht über alle Zeilen)
    for i in range(len(data)):
        # Neues Pivot? (Indizierung: Pivot wird am Bar i-rightBars erkannt)
        if i >= params['right_bars']:
            idx = i - params['right_bars']
            if data['pivot_low'].iloc[idx]:
                sup_levels.append(data['low'].iloc[idx])
                sup_indices.append(idx)
                # maxLevels begrenzen (FIFO)
                if len(sup_levels) > params['max_levels']:
                    sup_levels.pop(0)
                    sup_indices.pop(0)
            if data['pivot_high'].iloc[idx]:
                res_levels.append(data['high'].iloc[idx])
                res_indices.append(idx)
                if len(res_levels) > params['max_levels']:
                    res_levels.pop(0)
                    res_indices.pop(0)

        # Für den aktuellen Bar prüfen wir die Nähe zu den aktuellen Levels
        # Zone = ATR * zone_atr_mult
        zone = data['atr'].iloc[i] * params['zone_atr_mult']
        if sup_levels:
            # Prüfe, ob low innerhalb der Zone eines Supports liegt
            for lvl in sup_levels:
                if abs(data['low'].iloc[i] - lvl) <= zone:
                    near_support[i] = True
                    break
        if res_levels:
            for lvl in res_levels:
                if abs(data['high'].iloc[i] - lvl) <= zone:
                    near_resistance[i] = True
                    break

    data['near_support'] = near_support
    data['near_resistance'] = near_resistance

    # --- Entry-Bedingungen (wie in Pine Script) ---
    data['long_cond'] = (
        data['near_support'] &
        (~pd.Series(not params['use_wick'], index=data.index) | data['lower_rejection']) &
        (~pd.Series(not params['use_vol'], index=data.index) | data['high_volume']) &
        (~pd.Series(not params['use_bullish'], index=data.index) | data['is_bullish_candle']) &
        (~pd.Series(not params['use_st'], index=data.index) | data['bullish_trend']) &
        (~pd.Series(not params['use_side'], index=data.index) | ~data['in_sideways'])
    )

    data['short_cond'] = (
        data['near_resistance'] &
        (~pd.Series(not params['use_wick'], index=data.index) | data['upper_rejection']) &
        (~pd.Series(not params['use_vol'], index=data.index) | data['high_volume']) &
        (~pd.Series(not params['use_bullish'], index=data.index) | ~data['is_bullish_candle']) &
        (~pd.Series(not params['use_st'], index=data.index) | data['bearish_trend']) &
        (~pd.Series(not params['use_side'], index=data.index) | ~data['in_sideways'])
    )

    # Begründung (optional)
    def get_reason(row, direction):
        reasons = []
        if direction == 'long':
            if row['near_support']: reasons.append("nahe Support")
            if row['lower_rejection'] and params['use_wick']: reasons.append("Wick Rejection")
            if row['high_volume'] and params['use_vol']: reasons.append("hohes Volumen")
            if row['is_bullish_candle'] and params['use_bullish']: reasons.append("bullische Kerze")
            if row['bullish_trend'] and params['use_st']: reasons.append("Supertrend ↑")
            if not row['in_sideways'] and params['use_side']: reasons.append("Trend vorhanden")
        else:
            if row['near_resistance']: reasons.append("nahe Resistance")
            if row['upper_rejection'] and params['use_wick']: reasons.append("Wick Rejection")
            if row['high_volume'] and params['use_vol']: reasons.append("hohes Volumen")
            if not row['is_bullish_candle'] and params['use_bullish']: reasons.append("bärische Kerze")
            if row['bearish_trend'] and params['use_st']: reasons.append("Supertrend ↓")
            if not row['in_sideways'] and params['use_side']: reasons.append("Trend vorhanden")
        return " + ".join(reasons) if reasons else "—"

    data['reason'] = data.apply(
        lambda r: get_reason(r, 'long') if r['long_cond'] else get_reason(r, 'short') if r['short_cond'] else "", axis=1
    )

    return data, st_col, sup_levels, res_levels

def run_backtest(data, params, capital=1000, fee=0.001):
    required = ['long_cond', 'short_cond', 'bullish_trend', 'bearish_trend', 'timestamp', 'close']
    missing = [col for col in required if col not in data.columns]

    if missing:
        return 0.0, 0.0, 0.0, 0, pd.DataFrame(columns=['type', 'time', 'price', 'profit_pct', 'profit_usdt'])

    position = 0  # 1 = long, -1 = short
    entry_price = 0
    balance = capital
    trades = []

    for i in range(1, len(data)):
        row = data.iloc[i]

        # Exit
        if position == 1 and params['use_st'] and row['bearish_trend']:
            exit_price = row['close']
            raw_return = (exit_price - entry_price) / entry_price
            net_return = raw_return - 2 * fee
            profit_usdt = balance * net_return
            balance += profit_usdt
            profit_pct = net_return * 100
            trades.append({'type': 'Exit Long', 'time': row['timestamp'], 'price': exit_price,
                           'profit_pct': profit_pct, 'profit_usdt': profit_usdt})
            position = 0
        elif position == -1 and params['use_st'] and row['bullish_trend']:
            exit_price = row['close']
            raw_return = (entry_price - exit_price) / entry_price
            net_return = raw_return - 2 * fee
            profit_usdt = balance * net_return
            balance += profit_usdt
            profit_pct = net_return * 100
            trades.append({'type': 'Exit Short', 'time': row['timestamp'], 'price': exit_price,
                           'profit_pct': profit_pct, 'profit_usdt': profit_usdt})
            position = 0

        # Entry
        if position == 0:
            if row['long_cond']:
                position = 1
                entry_price = row['close']
                trades.append({'type': 'Enter Long', 'time': row['timestamp'], 'price': entry_price,
                               'profit_pct': 0, 'profit_usdt': 0})
            elif row['short_cond']:
                position = -1
                entry_price = row['close']
                trades.append({'type': 'Enter Short', 'time': row['timestamp'], 'price': entry_price,
                               'profit_pct': 0, 'profit_usdt': 0})

    # Offener Trade am Ende
    if position != 0:
        last = data.iloc[-1]
        if position == 1:
            exit_price = last['close']
            raw_return = (exit_price - entry_price) / entry_price
            net_return = raw_return - 2 * fee
            profit_usdt = balance * net_return
            profit_pct = net_return * 100
            trades.append({'type': 'Exit Long (Ende)', 'time': last['timestamp'], 'price': exit_price,
                           'profit_pct': profit_pct, 'profit_usdt': profit_usdt})
        else:
            exit_price = last['close']
            raw_return = (entry_price - exit_price) / entry_price
            net_return = raw_return - 2 * fee
            profit_usdt = balance * net_return
            profit_pct = net_return * 100
            trades.append({'type': 'Exit Short (Ende)', 'time': last['timestamp'], 'price': exit_price,
                           'profit_pct': profit_pct, 'profit_usdt': profit_usdt})

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return 0.0, 0.0, 0.0, 0, trades_df

    closed = trades_df[trades_df['type'].str.contains('Exit')]
    total_profit_usdt = closed['profit_usdt'].sum()
    total_profit_pct = (balance - capital) / capital * 100
    win_rate = (closed['profit_pct'] > 0).mean() * 100 if not closed.empty else 0.0
    num_trades = len(closed)

    return total_profit_pct, total_profit_usdt, win_rate, num_trades, trades_df
