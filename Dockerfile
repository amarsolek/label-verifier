# TTB Label Verifier - container image for Render (or any Docker host).
# Includes Tesseract so free local-OCR mode works with no API key.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
    
# Tesseract's OpenMP threads thrash on fractional-CPU containers
ENV OMP_THREAD_LIMIT=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects PORT (default 10000); fall back for local `docker run`.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]
