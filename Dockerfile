FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PANEL_HOST=0.0.0.0 PANEL_PORT=8080 PANEL_DATA_DIR=/data

# Client docker + compose : sert au conteneur « updater » pour reconstruire le panel.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:cli /usr/local/libexec/docker/cli-plugins /usr/local/lib/docker/cli-plugins

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Commit GitHub dont est issue cette image (renseigné par la mise à jour depuis l'interface).
ARG APP_SHA=
ENV APP_SHA=${APP_SHA}

EXPOSE 8080
CMD ["python", "-m", "app"]
