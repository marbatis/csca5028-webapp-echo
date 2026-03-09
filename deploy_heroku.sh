#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:-csca5028-echo-$(date +%s)}"

if ! heroku auth:whoami >/dev/null 2>&1; then
  echo "You are not logged in to Heroku CLI. Run: heroku login"
  exit 1
fi

if ! heroku apps:info -a "$APP_NAME" >/dev/null 2>&1; then
  heroku create "$APP_NAME"
fi

if git remote get-url heroku >/dev/null 2>&1; then
  git remote set-url heroku "https://git.heroku.com/${APP_NAME}.git"
else
  git remote add heroku "https://git.heroku.com/${APP_NAME}.git"
fi

git push heroku main
heroku ps:scale web=1 -a "$APP_NAME"

APP_URL="$(heroku apps:info -a "$APP_NAME" | awk '/Web URL:/ {print $3}')"
echo "Deployed URL: ${APP_URL%/}"
