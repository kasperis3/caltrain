#!/bin/sh
set -e
docker exec nginx nginx -s reload
echo "nginx reloaded after cert renewal"
