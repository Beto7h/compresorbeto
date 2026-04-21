#!/bin/bash

# --- PASO A: Iniciar el motor de Aria2 ---
# --enable-rpc: Activa la comunicación con el bot
# --rpc-listen-all: Permite que escuche peticiones
# --daemon=true: Lo lanza en segundo plano
echo "🌐 Iniciando servidor Aria2 RPC..."
aria2c --enable-rpc --rpc-listen-all --daemon=true

# --- PASO B: Pequeña espera ---
# Damos 2 segundos para que Aria2 termine de levantar el puerto
sleep 2

# --- PASO C: Iniciar el Bot ---
echo "🚀 Lanzando CompresorBeto..."
python3 main.py
