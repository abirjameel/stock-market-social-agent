FROM python:3.12-slim

WORKDIR /app

# matplotlib/Pillow need a couple of system libs for font/image handling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 --worker-class uvicorn.workers.UvicornWorker main:app
