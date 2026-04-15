#!/usr/bin/with-contenv bashio
echo "Starting Web Monitor Browser service..."
cd /app
exec python3 -m uvicorn server:app --host 0.0.0.0 --port 8099 --log-level info
