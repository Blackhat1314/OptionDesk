import pandas as pd
import numpy as np

df5  = pd.read_csv('D:/Trading_Model/options_5m_ml.csv')
df15 = pd.read_csv('D:/Trading_Model/options_15m_ml.csv')
df60 = pd.read_csv('D:/Trading_Model/options_60m_ml.csv')

for name, df in [('5min', df5), ('15min', df15), ('60min', df60)]:
    print(f'=== {name} ===')
    print(f'Rows: {len(df)} | Cols: {df.shape[1]}')
    print(f'Columns: {list(df.columns)}')
    print(f'Date range: {df["time"].min()} -> {df["time"].max()}')
    print(f'Null counts: {df.isnull().sum().sum()} total nulls')
    print()

print('=== 15min sample row ===')
print(df15.iloc[0].to_dict())

print()
print('=== 15min numeric stats ===')
print(df15.describe().to_string())
