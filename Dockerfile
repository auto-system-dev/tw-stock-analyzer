FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY tw_stock_analyzer ./tw_stock_analyzer
COPY .streamlit ./.streamlit
RUN pip install -e .

EXPOSE 8501

# 使用 sh -c 以讀取 Railway 注入的 PORT，避免 start.sh 在 Windows 的 CRLF 問題
CMD sh -c "python -m streamlit run tw_stock_analyzer/dashboard/app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false"
