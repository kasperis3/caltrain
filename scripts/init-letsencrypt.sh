#!/bin/bash
# One-time setup for HTTPS. Run from repo root after setting DOMAIN and EMAIL in .env.
# Prerequisites: DNS for DOMAIN must point to this server, ports 80 and 443 open.

set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Create .env with DOMAIN and EMAIL. Copy from .env.example."
  exit 1
fi
source .env

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Set DOMAIN and EMAIL in .env (e.g. DOMAIN=nextcaltrain.com EMAIL=you@example.com)"
  exit 1
fi

echo "Obtaining certificate for $DOMAIN..."

# 1. Use HTTP-only config so nginx can start without certs
echo "Using HTTP-only nginx config..."
export DOMAIN EMAIL
envsubst '${DOMAIN}' < nginx/nginx-http-only.conf.template > nginx/nginx.conf

# 2. Ensure certbot webroot exists
mkdir -p certbot

# 3. Start/restart nginx so it loads the HTTP-only config (with acme-challenge location)
docker compose up -d backend
docker compose up -d --force-recreate nginx

# 4. Wait for nginx to be ready
sleep 3

# 5. Get certificate (override entrypoint: certbot service normally runs "renew" loop)
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos \
  --non-interactive \
  --force-renewal

# 6. Switch to full HTTPS config
envsubst '${DOMAIN}' < nginx/nginx.conf.template > nginx/nginx.conf

# 7. Reload nginx
docker compose exec nginx nginx -s reload

echo "HTTPS is ready. Visit https://$DOMAIN"
