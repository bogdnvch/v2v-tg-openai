FROM python:3.11

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY . .

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
ENV PYTHONPATH=/app
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
