#!/usr/bin/env bash
# Rebuild the UI and copy it into the backend so one server serves everything.
set -e
cd "$(dirname "$0")/frontend"
npm install
npm run build
rm -rf ../backend/static && cp -r dist ../backend/static
echo "Frontend built into backend/static"
