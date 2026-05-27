FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

# Layer order is deliberate — cheapest cache invalidation last:
#  1. CPU-only torch (no preceding COPY, so this layer is stable across the repo).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

#  2. Heavy, slow-changing deps (sentence-transformers + transformers).
COPY requirements-base.txt .
RUN pip install -r requirements-base.txt

#  3. Bake the embedding model into the image so the service starts offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

#  4. App deps — changing these does NOT re-download torch or re-bake the model.
COPY requirements.txt .
RUN pip install -r requirements.txt

#  5. App source — changes here only rebuild this layer.
COPY . .

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
