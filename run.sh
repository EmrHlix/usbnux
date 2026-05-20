#!/usr/bin/env bash
# GTK ortam değişkenlerini koruyarak root olarak başlatır
cd "$(dirname "$0")"

export GSETTINGS_BACKEND=memory   # dconf uyarısını susturur

if [ "$EUID" -eq 0 ]; then
    python3 main.py
else
    sudo -E GSETTINGS_BACKEND=memory python3 main.py
fi
