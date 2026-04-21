FROM python:3.11-slim

# 1. Instalamos aria2 y ffmpeg (necesarios para descargar y procesar)
# Usamos -y para que no pida confirmación y borramos basura para que pese menos
RUN apt-get update && apt-get install -y \
    aria2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 2. Establecemos la carpeta de trabajo
WORKDIR /app

# 3. Copiamos e instalamos los requerimientos de Python
# En Docker no necesitas el --break-system-packages porque es un entorno aislado
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos todo el código de tu repositorio al contenedor
COPY . .

# 5. Damos permisos de ejecución al script de arranque
RUN chmod +x run_bot.sh

# 6. Comando final: Ejecutar el script que lanza Aria2 y el Bot
CMD ["./run_bot.sh"]
