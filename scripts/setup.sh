#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo 'Copy .env.example to .env and choose your own passwords before running setup.'
  exit 1
fi
docker compose up -d db
docker compose run --rm odoo odoo -d workshop -i workshop_hub --without-demo=all --stop-after-init
docker compose run --rm -T odoo odoo shell -d workshop --no-http < scripts/seed_demo.py
docker compose up -d odoo
echo 'Odoo: http://localhost:8069 — login admin with WORKSHOP_ADMIN_PASSWORD from .env'
