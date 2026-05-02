FROM python:3.11-slim

# Prophet needs these system libs for Stan compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
