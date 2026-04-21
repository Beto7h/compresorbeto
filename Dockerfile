FROM python:3.11-slim

# 1. Instalamos dependencias de sistema
# Eliminamos 'unrar' para evitar el error de "Package not found"
# p7zip-full se encargará de los archivos .zip, .7z y .rar
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

# 2. Establecemos la carpeta de trabajo
WORKDIR /app

# 3. Copiamos e instalamos los requerimientos de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos todo el código al contenedor
COPY . .

# 5. Damos permisos de ejecución al script de arranque
RUN chmod +x run_bot.sh

# 6. Comando final
CMD ["./run_bot.sh"]
