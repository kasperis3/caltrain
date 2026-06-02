FROM certbot/certbot:latest
USER root
RUN apk add --no-cache docker-cli
COPY deploy-hook.sh /deploy-hook.sh
RUN chmod +x /deploy-hook.sh
USER certbot
