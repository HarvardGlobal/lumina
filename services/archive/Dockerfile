FROM python:3.12-slim

WORKDIR /app
COPY services/archive/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/archive /app

EXPOSE 8200
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8200"]
