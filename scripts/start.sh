#!/bin/sh
# Migrations first, then serve. Running them here is what makes `docker compose up` the only
# command somebody needs. The library itself is loaded separately with import_library.py,
# because the media is not mine to publish.
set -e
alembic upgrade head
exec gunicorn esn_engine.api:app \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 -w 2 --access-logfile -
