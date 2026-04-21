#!/bin/bash

echo "🔄 Actualizando motores de extracción..."
# Esto asegura que los links de Drive/YouTube no fallen por falta de parches
pip install -U yt-dlp

echo "🌐 Iniciando servidor Aria2 RPC..."
# Añadimos parámetros para que Aria2 sea más agresivo y rápido
aria2c --enable-rpc \
       --rpc-listen-all=false \
       --rpc-listen-port=6800 \
       --max-connection-per-server=10 \
       --split=10 \
       --min-split-size=1M \
       --daemon=true \
       --allow-overwrite=true \
       --dir=/app

sleep 2

echo "🚀 Lanzando Compresor Élite..."
# Ejecutamos el bot
python3 main.py
