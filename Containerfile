FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY feast_mcp/ feast_mcp/

RUN pip install --no-cache-dir . gunicorn uvicorn

EXPOSE 8000

ENTRYPOINT ["gunicorn", "feast_mcp.asgi:app", \
            "-k", "uvicorn.workers.UvicornWorker", \
            "--bind", "0.0.0.0:8000"]
CMD ["-w", "4"]
