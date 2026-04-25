#!/bin/bash
# Verify ML model is available inside the container
# Model files are baked into the image at /app/ml_model/
# No manual copying needed — just rebuild the image.

echo "Verifying ML model inside container..."
docker exec optionsdesk_backend python3 -c "
import sys; sys.path.insert(0, '/app')
from features.ml_signals import is_model_available, _load_model
print('Model available:', is_model_available())
print('Model loads OK:', _load_model())
"
echo "Done. If model not available, rebuild: docker compose build backend && docker compose up -d backend"
