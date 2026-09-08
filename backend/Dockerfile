FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY . .
RUN uv pip install --system -e .
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
