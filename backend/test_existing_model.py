"""
Test existing model — find the missing feature and measure real performance.
"""
import pandas as pd
import numpy as np
import joblib
import json
import xgboost as xgb
from sklearn.metrics import roc_auc_score, accuracy_score

MODEL_DIR = "D:/Trading_Model/model_output"
scaler    = joblib.load(f"{MODEL_DIR}/scaler.pkl")
lgb_model = joblib.load(f"{MODEL_DIR}/lgb_model.pkl")
xgb_model = xgb.XGBClassifier()
xgb_model.load_model(f"{MODEL_DIR}/xgb_model.json")
feat_cols = json.load(open(f"{MODEL_DIR}/feature_cols.json"))
weights   = json.load(open(f"{MODEL_DIR}/model_weights.json"))

print(f"Scaler expects: {scaler.n_features_in_} features")
print(f"feature_cols.json has: {len(feat_cols)} features")
print(f"Features: {feat_cols}")
print()

# Load
df15 = pd.read_csv("D:/Trading_Model/options_15m_ml.csv")
df60 = pd.read_csv("D:/Trading_Model/options_60m_ml.csv")
df15["time"] = pd.to_datetime(df15["time"], utc=True)
df60["time"] = pd.to_datetime(df60["time"], utc=True)
df15 = df15.sort_values("time").reset_index(drop=True)
df60 = df60.sort_values("time").reset_index(drop=True)

def add_structural_features(df):
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
    return df

CONTEXT_COLS_60M = ["oi_change","iv_change","buildup_type","oi_momentum",
                    "global_pcr","iv_percentile","oi_concentration",
                    "atm_pressure","oi_skew_change","realized_vol"]

print("Building features...")
df15 = add_structural_features(df15)
df60 = add_structural_features(df60)

df15["time_60"] = df15["time"].dt.floor("60min")
df60_ctx = df60.rename(columns={c: f"{c}_60m" for c in CONTEXT_COLS_60M}).copy()
df60_ctx["time_60"] = df60_ctx["time"].dt.floor("60min")
ctx_cols = [f"{c}_60m" for c in CONTEXT_COLS_60M]
df60_ctx = df60_ctx[["time_60","strike","type"] + ctx_cols].drop_duplicates(subset=["time_60","strike","type"])
df_merged = df15.merge(df60_ctx, on=["time_60","strike","type"], how="left")

# Find what's in feat_cols but not in df_merged
in_df     = set(df_merged.columns)
missing   = [c for c in feat_cols if c not in in_df]
available = [c for c in feat_cols if c in in_df]
print(f"Missing features: {missing}")
print(f"Available: {len(available)}/{len(feat_cols)}")

# Fill missing with 0 so we can still test
for c in missing:
    df_merged[c] = 0.0
    print(f"  Filled {c} with 0")

df_clean = df_merged[feat_cols + ["time","label_direction"]].dropna().copy()
df_clean["label"] = df_clean["label_direction"].astype(int)
print(f"Clean rows: {len(df_clean):,}")

# Test on last 20%
split  = int(len(df_clean) * 0.80)
test   = df_clean.iloc[split:].copy().reset_index(drop=True)
print(f"\nTest period: {test['time'].min().date()} -> {test['time'].max().date()}")
print(f"Test rows: {len(test):,}")

X_test = scaler.transform(test[feat_cols].values)
p_xgb  = xgb_model.predict_proba(X_test)[:,1]
p_lgb  = lgb_model.predict_proba(X_test)[:,1]
p_ens  = weights['xgb'] * p_xgb + weights['lgb'] * p_lgb
y_true = test["label"].values

print()
print("=== EXISTING MODEL — OUT-OF-SAMPLE PERFORMANCE ===")
print(f"ROC-AUC       : {roc_auc_score(y_true, p_ens):.4f}")
print(f"Accuracy(all) : {accuracy_score(y_true, (p_ens>=0.5).astype(int)):.4f}")
print()
for thresh in [0.55, 0.60, 0.65, 0.70, 0.75]:
    mask = p_ens >= thresh
    if mask.sum() > 50:
        acc  = accuracy_score(y_true[mask], (p_ens[mask]>=0.5).astype(int))
        rate = mask.mean()
        print(f"  conf>={thresh:.2f}: acc={acc:.4f}  signal_rate={rate:.2%}  n={mask.sum():,}")
