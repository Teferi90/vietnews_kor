#!/bin/bash
set -e

cd /home/ubuntu/vietnam-podcast
source venv/bin/activate
export PATH="/home/ubuntu/.local/bin:$PATH"

LOG_FILE="/home/ubuntu/vietnam-podcast/logs/$(date +%Y%m%d).log"
mkdir -p /home/ubuntu/vietnam-podcast/logs

exec python main.py >> "$LOG_FILE" 2>&1
