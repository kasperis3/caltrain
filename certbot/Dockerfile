FROM certbot/certbot:latest
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*
COPY deploy-hook.sh /deploy-hook.sh
RUN chmod +x /deploy-hook.sh
USER certbot
