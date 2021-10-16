#!/usr/bin/with-contenv bashio
set -e

echo "[Info] Starting cloudflare addon!"

api_key=$(bashio::config 'api_key')
zone=$(bashio::config 'zone')
record=$(bashio::config 'record')

echo "[Info] Updating Record $record in Zone $zone"

export API_KEY=$api_key
/scripts/cloudflare.sh update $zone $record | jq .

echo "[Info] Finished cloudflare"
