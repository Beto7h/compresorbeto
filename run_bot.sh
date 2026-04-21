#!/bin/bash

# Actualizar yt-dlp cada vez que inicie el bot
pip install -U yt-dlp

echo "🌐 Iniciando servidor Aria2 RPC..."
aria2c --enable-rpc --rpc-listen-all --dir=/app --daemon=true

sleep 2

echo "🚀 Lanzando CompresorBeto..."
python3 main.py
