FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PANEL_HOST=0.0.0.0 PANEL_PORT=8080
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

EXPOSE 8080
CMD ["python", "-m", "app"]
