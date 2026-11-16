#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose stop odoo
docker compose run --rm odoo odoo -d workshop -u workshop_hub --stop-after-init
docker compose run --rm -T odoo odoo shell -d workshop --no-http < scripts/link_existing_jobs.py
docker compose up -d odoo
echo 'Workshop Hub updated. Restart Next.js and Expo after installing their dependencies.'
