FROM python:3.10-slim-buster

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg aria2 p7zip-full p7zip-rar git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python3", "main.py"]
