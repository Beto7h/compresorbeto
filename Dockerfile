FROM python:3.11-slim

# 1. Instalamos dependencias de sistema
# Añadimos p7zip-full y unrar para la nueva función de extracción
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    p7zip-full \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# 2. Establecemos la carpeta de trabajo
WORKDIR /app

# 3. Copiamos e instalamos los requerimientos de Python
# Asegúrate de que en requirements.txt estén: pyrogram, tgcrypto, aria2p, yt-dlp, psutil
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos todo el código al contenedor
COPY . .

# 5. Damos permisos de ejecución al script de arranque
RUN chmod +x run_bot.sh

# 6. Comando final
CMD ["./run_bot.sh"]
