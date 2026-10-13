# Build context = this actor/ directory (Apify default). Library code is vendored in ./src by scripts/sync_actor.py.
FROM python:3.12-slim
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY main.py ./
ENV PYTHONPATH=/usr/src/app/src
CMD ["python", "main.py"]
