#!/bin/bash
set -e

VPS="root@104.218.100.67"
REMOTE_DIR="/var/www/changelog"

echo "Generating site..."
/opt/homebrew/bin/python3 "$(dirname "$0")/generate.py"

echo "Syncing to VPS..."
rsync -avz --delete site/ "$VPS:$REMOTE_DIR/"

echo "Verifying..."
sleep 1
HTTP_CODE=$(curl --noproxy '*' -s -o /dev/null -w "%{http_code}" https://changelog.tianlizeng.cloud)
if [ "$HTTP_CODE" = "200" ]; then
  echo "Deployed! https://changelog.tianlizeng.cloud"
else
  echo "HTTP $HTTP_CODE — check Nginx config"
fi
