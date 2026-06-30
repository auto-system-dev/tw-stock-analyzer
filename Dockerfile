FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

COPY requirements.txt pyproject.toml README.md ./
RUN for i in 1 2 3; do \
        pip install --upgrade pip \
        && pip install --retries 10 --timeout 120 -r requirements.txt \
        && break; \
        echo "pip install attempt $i failed, retrying..."; \
        sleep 15; \
    done

COPY tw_stock_analyzer ./tw_stock_analyzer
COPY .streamlit ./.streamlit
RUN for i in 1 2 3; do \
        pip install --retries 10 --timeout 120 -e . \
        && break; \
        echo "pip install -e attempt $i failed, retrying..."; \
        sleep 15; \
    done

EXPOSE 8501

# 使用 sh -c 以讀取 Railway 注入的 PORT，避免 start.sh 在 Windows 的 CRLF 問題
CMD sh -c "python -m streamlit run tw_stock_analyzer/dashboard/app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false"
