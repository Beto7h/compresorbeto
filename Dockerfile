FROM python:3.11-slim

# Instalar dependencias del sistema (Aria2 y FFmpeg)
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    & rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos e instalar (Aquí no hay error de "managed environment")
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Dar permisos al script de arranque
RUN chmod +x run_bot.sh

# Ejecutar el script que lanza Aria2 y el Bot
CMD ["./run_bot.sh"]
