#!/bin/bash

# Iniciar Aria2 en segundo plano con el RPC activo
aria2c --enable-rpc --rpc-listen-all --daemon=true

# Lanzar el bot de Python
python3 main.py
