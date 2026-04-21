#!/bin/bash

echo "🌐 Iniciando servidor Aria2 RPC..."
# Añadimos --dir=/app para sincronizar rutas con el bot
aria2c --enable-rpc --rpc-listen-all --dir=/app --daemon=true

sleep 2

echo "🚀 Lanzando CompresorBeto..."
python3 main.py
