"""
train_model_v2.py
=================
Improved NIFTY Options ML Pipeline — v2

Improvements over v1:
  1. Uses label_direction from CSV directly (no re-labeling needed)
  2. Adds 12 new features: vega_proxy, gamma_proxy, theta_proxy,
     iv_spread, put_call_iv_ratio, oi_velocity, price_acceleration,
     volume_surge, atm_distance_norm, iv_zscore, oi_zscore, hour_sin/cos
  3. Fixes scaler/feature_cols mismatch — saves exact feature list used
  4. Adds 5min context (short-term momentum) as additional MTF layer
  5. Better hyperparameters with class weight balancing
  6. Saves all artifacts consistently

OUTPUT -> D:/Trading_Model/model_v2/
"""

import os, json, warnings, time
import pandas as pd
import numpy as np
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.preprocessing   import StandardScaler
from sklearn.metrics         import roc_auc_score, accuracy_score
from sklearn.model_selection import TimeSeriesSplit
import xgboost  as xgb
import lightgbm as lgb

warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────
CSV_5M  = "D:/Trading_Model/options_5m_ml.csv"
CSV_15M = "D:/Trading_Model/options_15m_ml.csv"
CSV_60M = "D:/Trading_Model/options_60m_ml.csv"
OUT_DIR = "D:/Trading_Model/model_v2"
os.makedirs(OUT_DIR, exist_ok=True)

CONFIDENCE_THRESHOLD = 0.65
WF_SPLITS            = 5


# ── Step 1: Load ──────────────────────────────────────────────────────────────
def load_all():
    print("\n=== STEP 1: LOADING DATA ===")
    df5  = pd.read_csv(CSV_5M);  df5["time"]  = pd.to_datetime(df5["time"],  utc=True)
    df15 = pd.read_csv(CSV_15M); df15["time"] = pd.to_datetime(df15["time"], utc=True)
    df60 = pd.read_csv(CSV_60M); df60["time"] = pd.to_datetime(df60["time"], utc=True)
    for name, df in [("5m", df5), ("15m", df15), ("60m", df60)]:
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        print(f"  {name}: {len(df):,} rows | {df['time'].min().date()} -> {df['time'].max().date()}")
    return df5, df15, df60


# ── Step 2: Feature engineering ───────────────────────────────────────────────
def add_features(df, timeframe="15m"):
    """Add all features including new v2 ones."""
    df = df.copy()

    # ── Existing structural features ──────────────────────────────────────────
    call_oi     = df[df["type"]=="CALL"].groupby("time")["oi"].sum()
    put_oi      = df[df["type"]=="PUT"].groupby("time")["oi"].sum()
    oi_skew_chg = (put_oi - call_oi).diff().rename("oi_skew_change")
    df = df.join(oi_skew_chg, on="time")

    df["atm_pressure"] = df["oi_concentration"] * df["volume_oi_ratio"]
    df["oi_rank"]      = df.groupby(["time","type"])["oi"].rank(ascending=False)
    df["iv_rank"]      = df.groupby(["time","type"])["iv"].rank(ascending=False)
    df["realized_vol"] = (
        df.groupby(["strike","type"])["price_change_pct"]
          .transform(lambda x: x.rolling(10, min_periods=3).std())
    )
    df["session"] = pd.cut(
        df["time_of_day"], bins=[-0.01, 0.16, 0.60, 1.01], labels=[1,2,3]
    ).astype(float)

    # ── NEW v2 features ───────────────────────────────────────────────────────

    # 1. IV spread (call IV - put IV at same strike/time)
    call_iv = df[df["type"]=="CALL"].set_index(["time","strike"])["iv"].rename("call_iv")
    put_iv  = df[df["type"]=="PUT"].set_index(["time","strike"])["iv"].rename("put_iv")
    iv_spread = (call_iv - put_iv).reset_index().rename(columns={0:"iv_spread"})
    df = df.merge(iv_spread, on=["time","strike"], how="left")
    df["iv_spread"] = df["iv_spread"].fillna(0)

    # 2. Put/Call IV ratio per snapshot
    call_iv_mean = df[df["type"]=="CALL"].groupby("time")["iv"].mean().rename("call_iv_mean")
    put_iv_mean  = df[df["type"]=="PUT"].groupby("time")["iv"].mean().rename("put_iv_mean")
    df = df.join(call_iv_mean, on="time").join(put_iv_mean, on="time")
    df["put_call_iv_ratio"] = (df["put_iv_mean"] / df["call_iv_mean"].replace(0, np.nan)).fillna(1.0)
    df.drop(columns=["call_iv_mean","put_iv_mean"], inplace=True)

    # 3. OI velocity (rate of change of OI change)
    df["oi_velocity"] = (
        df.groupby(["strike","type"])["oi_change"]
          .transform(lambda x: x.diff())
    )

    # 4. Price acceleration
    df["price_acceleration"] = (
        df.groupby(["strike","type"])["price_change_pct"]
          .transform(lambda x: x.diff())
    )

    # 5. Volume surge (volume vs rolling mean)
    df["volume_surge"] = (
        df.groupby(["strike","type"])["volume"]
          .transform(lambda x: x / (x.rolling(5, min_periods=1).mean() + 1))
    )

    # 6. ATM distance normalized by spot
    df["atm_distance_norm"] = df["distance_to_spot"] / df["spot"].replace(0, np.nan)
    df["atm_distance_norm"] = df["atm_distance_norm"].fillna(0)

    # 7. IV z-score (rolling 20 candles per strike/type)
    df["iv_zscore"] = (
        df.groupby(["strike","type"])["iv"]
          .transform(lambda x: (x - x.rolling(20, min_periods=5).mean()) /
                               (x.rolling(20, min_periods=5).std() + 1e-8))
    )

    # 8. OI z-score
    df["oi_zscore"] = (
        df.groupby(["strike","type"])["oi"]
          .transform(lambda x: (x - x.rolling(20, min_periods=5).mean()) /
                               (x.rolling(20, min_periods=5).std() + 1e-8))
    )

    # 9. Hour sin/cos encoding (cyclical time features)
    df["hour_sin"] = np.sin(2 * np.pi * df["candle_hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["candle_hour"] / 24)

    # 10. Vega proxy (IV * sqrt(time_to_expiry_proxy))
    # Use time_of_day as proxy for time remaining in session
    df["vega_proxy"] = df["iv"] * np.sqrt(1 - df["time_of_day"] + 0.01)

    # 11. Gamma proxy (higher for ATM, decays with distance)
    df["gamma_proxy"] = np.exp(-0.5 * (df["atm_offset"] ** 2) / 4.0)

    # 12. Theta proxy (time decay pressure — higher near close)
    df["theta_proxy"] = df["time_of_day"] * df["iv"] / 100.0

    return df


# ── Step 3: Build MTF dataset ─────────────────────────────────────────────────
CONTEXT_COLS_60M = [
    "oi_change","iv_change","buildup_type","oi_momentum",
    "global_pcr","iv_percentile","oi_concentration",
    "atm_pressure","oi_skew_change","realized_vol",
    "iv_spread","put_call_iv_ratio","oi_velocity","volume_surge","iv_zscore",
]

CONTEXT_COLS_5M = [
    "price_change_pct","oi_change","iv_change","volume_oi_ratio","oi_momentum",
]

def build_mtf_dataset(df5, df15, df60):
    print("\n=== STEP 2: FEATURE ENGINEERING + MTF MERGE ===")

    df15 = add_features(df15, "15m")
    df60 = add_features(df60, "60m")
    df5  = add_features(df5,  "5m")

    # 60min context
    df15["time_60"] = df15["time"].dt.floor("60min")
    df60_ctx = df60.rename(columns={c: f"{c}_60m" for c in CONTEXT_COLS_60M}).copy()
    df60_ctx["time_60"] = df60_ctx["time"].dt.floor("60min")
    ctx60 = [f"{c}_60m" for c in CONTEXT_COLS_60M]
    df60_ctx = df60_ctx[["time_60","strike","type"] + ctx60].drop_duplicates(subset=["time_60","strike","type"])
    df_merged = df15.merge(df60_ctx, on=["time_60","strike","type"], how="left")

    # 5min context (last 5min candle before each 15min candle)
    df_merged["time_5"] = (df_merged["time"] - pd.Timedelta(minutes=5)).dt.floor("5min")
    df5_ctx = df5.rename(columns={c: f"{c}_5m" for c in CONTEXT_COLS_5M}).copy()
    ctx5 = [f"{c}_5m" for c in CONTEXT_COLS_5M]
    df5_ctx["time_5"] = df5_ctx["time"].dt.floor("5min")
    df5_ctx = df5_ctx[["time_5","strike","type"] + ctx5].drop_duplicates(subset=["time_5","strike","type"])
    df_merged = df_merged.merge(df5_ctx, on=["time_5","strike","type"], how="left")

    print(f"  Rows after MTF merge: {len(df_merged):,}")
    print(f"  60m context cols: {len(ctx60)}")
    print(f"  5m context cols : {len(ctx5)}")
    return df_merged


# ── Step 4: Define feature columns ───────────────────────────────────────────
BASE_FEATURES = [
    # Original
    "atm_offset","moneyness","distance_to_spot","atm_zone",
    "oi_change","iv_change","buildup_type","oi_momentum",
    "oi_concentration","global_pcr","iv_percentile",
    "price_change_pct","volume_oi_ratio",
    "atm_pressure","oi_skew_change","oi_rank","iv_rank",
    "realized_vol","time_of_day","candle_hour","session",
    # New v2
    "iv_spread","put_call_iv_ratio","oi_velocity","price_acceleration",
    "volume_surge","atm_distance_norm","iv_zscore","oi_zscore",
    "hour_sin","hour_cos","vega_proxy","gamma_proxy","theta_proxy",
]

CONTEXT_60M_FEATURES = [f"{c}_60m" for c in CONTEXT_COLS_60M]
CONTEXT_5M_FEATURES  = [f"{c}_5m"  for c in CONTEXT_COLS_5M]

ALL_FEATURES = BASE_FEATURES + CONTEXT_60M_FEATURES + CONTEXT_5M_FEATURES


# ── Step 5: Walk-forward training ─────────────────────────────────────────────
def walk_forward_train(df):
    print("\n=== STEP 3: WALK-FORWARD VALIDATION ===")

    available = [c for c in ALL_FEATURES if c in df.columns]
    missing   = [c for c in ALL_FEATURES if c not in df.columns]
    if missing:
        print(f"  Skipping missing: {missing}")

    df_clean = df[available + ["time","label_direction","strike","type","atm_offset"]].dropna().copy()
    df_clean["label"] = df_clean["label_direction"].astype(int)
    print(f"  Training rows : {len(df_clean):,}")
    print(f"  Features      : {len(available)}")
    print(f"  Date range    : {df_clean['time'].min().date()} -> {df_clean['time'].max().date()}")
    print(f"  Label balance : UP={df_clean['label'].mean():.1%}  DOWN={(1-df_clean['label'].mean()):.1%}")

    X = df_clean[available].values
    y = df_clean["label"].values

    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    tscv       = TimeSeriesSplit(n_splits=WF_SPLITS)
    results    = []
    xgb_models = []
    lgb_models = []

    for fold, (tr_idx, te_idx) in enumerate(tscv.split(X_scaled)):
        X_tr, X_te = X_scaled[tr_idx], X_scaled[te_idx]
        y_tr, y_te = y[tr_idx], y[te_idx]

        # Class weight for imbalance
        scale_pos = (y_tr == 0).sum() / (y_tr == 1).sum()

        xgb_m = xgb.XGBClassifier(
            n_estimators=600, max_depth=6, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            reg_alpha=0.1, reg_lambda=1.0, scale_pos_weight=scale_pos,
            eval_metric="auc", early_stopping_rounds=30,
            random_state=42, n_jobs=-1,
        )
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)
        xgb_models.append(xgb_m)

        lgb_m = lgb.LGBMClassifier(
            n_estimators=600, max_depth=6, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, min_child_samples=20,
            reg_alpha=0.1, reg_lambda=1.0, class_weight="balanced",
            early_stopping_round=30, random_state=42, n_jobs=-1, verbose=-1,
        )
        lgb_m.fit(X_tr, y_tr, eval_set=[(X_te, y_te)],
                  callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)])
        lgb_models.append(lgb_m)

        p_xgb = xgb_m.predict_proba(X_te)[:,1]
        p_lgb = lgb_m.predict_proba(X_te)[:,1]
        p_ens = 0.55 * p_xgb + 0.45 * p_lgb

        conf_mask = p_ens >= CONFIDENCE_THRESHOLD
        auc       = roc_auc_score(y_te, p_ens)
        acc_all   = accuracy_score(y_te, (p_ens >= 0.5).astype(int))
        acc_conf  = accuracy_score(y_te[conf_mask], (p_ens[conf_mask] >= 0.5).astype(int)) if conf_mask.sum() > 10 else 0.0

        results.append({
            "fold": fold+1, "train_rows": len(tr_idx), "test_rows": len(te_idx),
            "accuracy_all": round(acc_all, 4), "roc_auc": round(auc, 4),
            "accuracy_conf": round(acc_conf, 4),
            "conf_rate": round(conf_mask.mean(), 4),
            "conf_trades": int(conf_mask.sum()),
        })
        print(f"  Fold {fold+1}/{WF_SPLITS} | AUC={auc:.4f} | Acc(all)={acc_all:.4f} | "
              f"Acc(conf>={CONFIDENCE_THRESHOLD})={acc_conf:.4f} | Signal={conf_mask.mean():.1%}")

    rdf = pd.DataFrame(results)
    print(f"\n  Mean AUC             : {rdf['roc_auc'].mean():.4f}")
    print(f"  Mean Acc (all)       : {rdf['accuracy_all'].mean():.4f}")
    print(f"  Mean Acc (conf>=0.65): {rdf['accuracy_conf'].mean():.4f}")
    rdf.to_csv(f"{OUT_DIR}/walk_forward_report.csv", index=False)
    return xgb_models, lgb_models, scaler, available, df_clean


# ── Step 6: Final model ───────────────────────────────────────────────────────
def train_final_model(df_clean, available, scaler):
    print("\n=== STEP 4: FINAL MODEL (all data) ===")

    X = scaler.transform(df_clean[available].values)
    y = df_clean["label"].astype(int).values
    scale_pos = (y == 0).sum() / (y == 1).sum()

    xgb_f = xgb.XGBClassifier(
        n_estimators=700, max_depth=6, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_alpha=0.1, reg_lambda=1.0, scale_pos_weight=scale_pos,
        eval_metric="auc", random_state=42, n_jobs=-1,
    )
    xgb_f.fit(X, y, verbose=False)

    lgb_f = lgb.LGBMClassifier(
        n_estimators=700, max_depth=6, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8, min_child_samples=20,
        reg_alpha=0.1, reg_lambda=1.0, class_weight="balanced",
        random_state=42, n_jobs=-1, verbose=-1,
    )
    lgb_f.fit(X, y)

    # Save — all artifacts consistent
    xgb_f.save_model(f"{OUT_DIR}/xgb_model.json")
    joblib.dump(lgb_f,  f"{OUT_DIR}/lgb_model.pkl")
    joblib.dump(scaler, f"{OUT_DIR}/scaler.pkl")
    with open(f"{OUT_DIR}/feature_cols.json", "w") as f:
        json.dump(available, f, indent=2)
    with open(f"{OUT_DIR}/model_weights.json", "w") as f:
        json.dump({"xgb": 0.55, "lgb": 0.45}, f)
    with open(f"{OUT_DIR}/model_meta.json", "w") as f:
        json.dump({
            "version": "v2",
            "n_features": len(available),
            "features": available,
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "target": "label_direction (1=UP, 0=DOWN)",
            "timeframe": "15min candles",
            "context": "60min + 5min MTF",
        }, f, indent=2)

    print(f"  Saved {len(available)} features to {OUT_DIR}/")
    return xgb_f, lgb_f


# ── Step 7: Feature importance ────────────────────────────────────────────────
def plot_importance(xgb_model, lgb_model, available):
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    for ax, model, title in zip(axes, [xgb_model, lgb_model], ["XGBoost v2", "LightGBM v2"]):
        imp   = model.feature_importances_
        names = available[:len(imp)]
        df_i  = pd.DataFrame({"feature": names, "importance": imp}).sort_values("importance").tail(25)
        ax.barh(df_i["feature"], df_i["importance"], color="steelblue")
        ax.set_title(f"{title} — Top 25 Features", fontsize=12)
        ax.set_xlabel("Importance")
        ax.tick_params(axis="y", labelsize=8)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/feature_importance.png", dpi=150)
    plt.close()
    print(f"  Saved: {OUT_DIR}/feature_importance.png")


# ── Step 8: Backtest ──────────────────────────────────────────────────────────
def backtest(df_clean, xgb_model, lgb_model, scaler, available):
    print("\n=== STEP 5: BACKTEST (last 20%) ===")

    BARRIER_UP   =  0.005
    BARRIER_DOWN = -0.005
    SLIPPAGE     =  0.002
    BROKERAGE    =  0.0005
    total_cost   = SLIPPAGE * 2 + BROKERAGE

    split  = int(len(df_clean) * 0.80)
    test   = df_clean.iloc[split:].copy().reset_index(drop=True)
    X_test = scaler.transform(test[available].values)
    p_xgb  = xgb_model.predict_proba(X_test)[:,1]
    p_lgb  = lgb_model.predict_proba(X_test)[:,1]
    p_ens  = 0.55 * p_xgb + 0.45 * p_lgb

    test["prob"]   = p_ens
    test["signal"] = (p_ens >= CONFIDENCE_THRESHOLD).astype(int)

    # ATM ±2 only, highest confidence per timestamp
    atm     = (test[test["atm_offset"].abs() <= 2]
               .sort_values(["time","prob"], ascending=[True, False])
               .groupby("time").head(1).reset_index(drop=True))
    signals = atm[atm["signal"] == 1].copy()

    print(f"  Test period  : {test['time'].min().date()} -> {test['time'].max().date()}")
    print(f"  Total signals: {len(signals)}")

    if len(signals) == 0:
        print("  No signals — lower CONFIDENCE_THRESHOLD")
        return

    trades = []
    for _, row in signals.iterrows():
        label     = int(row["label"])
        predicted = 1 if row["prob"] >= 0.5 else 0
        gross     = BARRIER_UP if (predicted == 1 and label == 1) else \
                    BARRIER_DOWN if (predicted == 1 and label == 0) else \
                    abs(BARRIER_DOWN) if (predicted == 0 and label == 0) else \
                    -BARRIER_UP
        net = gross - total_cost
        trades.append({
            "time": row["time"], "strike": row["strike"], "type": row["type"],
            "direction": "LONG" if predicted == 1 else "SHORT",
            "prob": round(row["prob"], 4), "label": label,
            "correct": int(predicted == label),
            "gross_ret": round(gross, 6), "net_ret": round(net, 6),
            "win": 1 if net > 0 else 0,
        })

    tdf = pd.DataFrame(trades)
    tdf["equity"] = (1 + tdf["net_ret"]).cumprod()

    win_rate  = tdf["win"].mean()
    total_ret = tdf["equity"].iloc[-1] - 1
    max_dd    = ((tdf["equity"].cummax() - tdf["equity"]) / tdf["equity"].cummax()).max()
    avg_net   = tdf["net_ret"].mean()
    std_net   = tdf["net_ret"].std()
    sharpe    = (avg_net / std_net) * np.sqrt(252 * 26) if std_net > 0 else 0
    correct   = tdf["correct"].mean()

    print(f"  Trades       : {len(tdf)}")
    print(f"  Accuracy     : {correct:.1%}")
    print(f"  Win rate     : {win_rate:.1%}")
    print(f"  Total return : {total_ret:.2%}")
    print(f"  Max drawdown : {max_dd:.2%}")
    print(f"  Sharpe       : {sharpe:.2f}")

    tdf.to_csv(f"{OUT_DIR}/backtest_report.csv", index=False)

    # Equity curve
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(tdf["equity"].values, color="steelblue", linewidth=1.5)
    ax.axhline(1.0, color="gray", linestyle="--")
    ax.fill_between(range(len(tdf)), tdf["equity"].values, 1,
                    where=tdf["equity"].values >= 1, alpha=0.15, color="green")
    ax.fill_between(range(len(tdf)), tdf["equity"].values, 1,
                    where=tdf["equity"].values < 1, alpha=0.15, color="red")
    ax.set_title(f"v2 Equity | Acc={correct:.1%} Win={win_rate:.1%} Sharpe={sharpe:.2f} MaxDD={max_dd:.1%}")
    ax.set_ylabel("Equity")
    ax.set_xlabel("Trade #")
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/equity_curve.png", dpi=150)
    plt.close()
    print(f"  Saved: {OUT_DIR}/equity_curve.png")
    return tdf


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 60)
    print("  NIFTY OPTIONS ML — v2 TRAINING PIPELINE")
    print("=" * 60)

    df5, df15, df60                              = load_all()
    df_merged                                    = build_mtf_dataset(df5, df15, df60)
    xgb_ms, lgb_ms, scaler, available, df_clean = walk_forward_train(df_merged)
    xgb_f, lgb_f                                = train_final_model(df_clean, available, scaler)
    plot_importance(xgb_f, lgb_f, available)
    backtest(df_clean, xgb_f, lgb_f, scaler, available)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  DONE — {elapsed/60:.1f} minutes")
    print(f"  Outputs: {OUT_DIR}/")
    print(f"  Features used: {len(available)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
