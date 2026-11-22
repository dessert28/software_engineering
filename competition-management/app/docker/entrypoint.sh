#!/bin/sh
# 根据第一个参数选择角色：api 或 web。
set -e

case "$1" in
  api)
    if [ "$#" -gt 1 ]; then
      shift
      exec "$@"
    fi
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  web)
    exec nginx -g "daemon off;"
    ;;
  *)
    exec "$@"
    ;;
esac
