"""Run backtest on already-trained v2 model."""
import pandas as pd
import numpy as np
import joblib
import json
import xgboost as xgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, '.')
from train_model_v2 import load_all, build_mtf_dataset

MODEL_DIR = "D:/Trading_Model/model_v2"
scaler    = joblib.load(f"{MODEL_DIR}/scaler.pkl")
lgb_model = joblib.load(f"{MODEL_DIR}/lgb_model.pkl")
xgb_model = xgb.XGBClassifier()
xgb_model.load_model(f"{MODEL_DIR}/xgb_model.json")
feat_cols = json.load(open(f"{MODEL_DIR}/feature_cols.json"))
weights   = json.load(open(f"{MODEL_DIR}/model_weights.json"))
print(f"Model v2 loaded — {len(feat_cols)} features")

df5, df15, df60 = load_all()
df_merged       = build_mtf_dataset(df5, df15, df60)

# Deduplicate columns immediately after merge
df_merged = df_merged.loc[:, ~df_merged.columns.duplicated()].copy()
print(f"Columns after dedup: {df_merged.shape[1]}")

# Verify all features present
missing = [c for c in feat_cols if c not in df_merged.columns]
if missing:
    print(f"Missing features: {missing}")
    for c in missing:
        df_merged[c] = 0.0

keep = feat_cols + ["time","label_direction","strike","type","atm_offset"]
keep = list(dict.fromkeys(keep))  # deduplicate keep list
keep = [c for c in keep if c in df_merged.columns]
df_clean = df_merged[keep].dropna().copy()
df_clean["label"] = df_clean["label_direction"].astype(int)
print(f"Clean rows: {len(df_clean):,}")

# Backtest on last 20%
CONFIDENCE_THRESHOLD = 0.65
BARRIER_UP   =  0.005
BARRIER_DOWN = -0.005
total_cost   =  0.002 * 2 + 0.0005

split = int(len(df_clean) * 0.80)
test  = df_clean.iloc[split:].copy().reset_index(drop=True)
print(f"Test period: {test['time'].min().date()} -> {test['time'].max().date()}")
print(f"Test rows: {len(test):,}")

X_test = scaler.transform(test[feat_cols].values)
p_xgb  = xgb_model.predict_proba(X_test)[:,1]
p_lgb  = lgb_model.predict_proba(X_test)[:,1]
p_ens  = weights['xgb'] * p_xgb + weights['lgb'] * p_lgb

test = test.copy()
test["prob"]   = p_ens
test["signal"] = (p_ens >= CONFIDENCE_THRESHOLD).astype(int)

atm     = (test[test["atm_offset"].abs() <= 2]
           .sort_values(["time","prob"], ascending=[True, False])
           .groupby("time").head(1).reset_index(drop=True))
signals = atm[atm["signal"] == 1].copy()
print(f"Signals: {len(signals)}")

if len(signals) == 0:
    print("No signals — lower CONFIDENCE_THRESHOLD")
    exit()

trades = []
for _, row in signals.iterrows():
    label     = int(row["label"])
    predicted = 1 if row["prob"] >= 0.5 else 0
    if predicted == 1:
        gross = BARRIER_UP if label == 1 else BARRIER_DOWN
    else:
        gross = abs(BARRIER_DOWN) if label == 0 else -BARRIER_UP
    net = gross - total_cost
    trades.append({
        "time": row["time"], "strike": row.get("strike", 0), "type": row.get("type", ""),
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

print()
print("=== v2 BACKTEST RESULTS ===")
print(f"Trades       : {len(tdf)}")
print(f"Accuracy     : {correct:.1%}")
print(f"Win rate     : {win_rate:.1%}")
print(f"Total return : {total_ret:.2%}")
print(f"Max drawdown : {max_dd:.2%}")
print(f"Sharpe       : {sharpe:.2f}")
print(f"Avg net/trade: {avg_net*100:.3f}%")

print()
print("=== CONFIDENCE THRESHOLD SWEEP ===")
for thresh in [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
    mask = p_ens >= thresh
    if mask.sum() > 50:
        acc  = (test["label"].values[mask] == (p_ens[mask] >= 0.5).astype(int)).mean()
        rate = mask.mean()
        print(f"  conf>={thresh:.2f}: acc={acc:.4f}  signal_rate={rate:.2%}  n={mask.sum():,}")

tdf.to_csv(f"{MODEL_DIR}/backtest_report.csv", index=False)

fig, ax = plt.subplots(figsize=(13, 5))
ax.plot(tdf["equity"].values, color="steelblue", linewidth=1.5)
ax.axhline(1.0, color="gray", linestyle="--")
ax.fill_between(range(len(tdf)), tdf["equity"].values, 1,
                where=tdf["equity"].values >= 1, alpha=0.15, color="green")
ax.fill_between(range(len(tdf)), tdf["equity"].values, 1,
                where=tdf["equity"].values < 1, alpha=0.15, color="red")
ax.set_title(f"v2 | Acc={correct:.1%} Win={win_rate:.1%} Sharpe={sharpe:.2f} MaxDD={max_dd:.1%}")
ax.set_ylabel("Equity"); ax.set_xlabel("Trade #")
plt.tight_layout()
plt.savefig(f"{MODEL_DIR}/equity_curve.png", dpi=150)
plt.close()
print(f"\nSaved: {MODEL_DIR}/backtest_report.csv")
print(f"Saved: {MODEL_DIR}/equity_curve.png")
