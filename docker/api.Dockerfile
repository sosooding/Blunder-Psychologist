FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# psycopg2-binary ships wheels, so no libpq build deps are needed here.
COPY core/ /app/
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "blunder.api:app", "--host", "0.0.0.0", "--port", "8000"]
