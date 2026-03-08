FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY rules/ rules/
COPY demo/ demo/

RUN pip install --no-cache-dir ".[otel]" opentelemetry-exporter-otlp-proto-grpc

CMD ["python", "demo/run_demo.py", "--otel"]
