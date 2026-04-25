#!/bin/bash
# Run this on the VM to copy model files into the Docker volume
# Usage: bash backend/setup_ml_model.sh

echo "Creating ml_model directory in Docker volume..."
docker exec optionsdesk_backend mkdir -p /app/data/ml_model

echo "Copying model files..."
for f in xgb_model.json lgb_model.pkl scaler.pkl feature_cols.json model_weights.json model_meta.json; do
    if [ -f "backend/data/ml_model/$f" ]; then
        docker cp "backend/data/ml_model/$f" "optionsdesk_backend:/app/data/ml_model/$f"
        echo "  Copied $f"
    else
        echo "  MISSING: $f — run training first"
    fi
done

echo "Verifying..."
docker exec optionsdesk_backend python3 -c "
import sys; sys.path.insert(0, '/app')
from features.ml_signals import is_model_available, _load_model
print('Model available:', is_model_available())
print('Model loads OK:', _load_model())
"
echo "Done."
