#!/bin/sh
set -e
PORT="${PORT:-8501}"
exec python -m streamlit run tw_stock_analyzer/dashboard/app.py \
  --server.port="${PORT}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
