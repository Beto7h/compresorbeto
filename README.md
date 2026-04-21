---

# 🚀 Compresor Élite - Guía de Despliegue en VPS

Este documento contiene los pasos exactos para instalar y ejecutar el bot en una VPS limpia desde cero, utilizando **Docker** para evitar errores de rutas o dependencias.

## 📋 Requisitos Previos
* Una VPS con Ubuntu/Debian.
* Token de Bot de Telegram, API ID y API HASH (configurados en `config.py`).

---

## 🛠️ Paso 1: Instalación del Entorno (Solo una vez)
Si la VPS es nueva, Docker no estará instalado. Ejecuta esto para preparar el sistema:

```bash
# 1. Actualizar el sistema
apt update && apt upgrade -y

# 2. Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 3. Instalar Docker Compose
apt install docker-compose -y

# 4. Activar el servicio de Docker
systemctl start docker
systemctl enable docker
```

---

## 📂 Paso 2: Estructura de Archivos
Asegúrate de que tu carpeta (ej. `/root/compresorbeto`) tenga estos archivos:

1.  **`main.py`**: El código del bot (versión híbrida/Docker).
2.  **`config.py`**: Tus credenciales de Telegram.
3.  **`Dockerfile`**: Configuración del contenedor (Python 3.11 + FFmpeg + Aria2).
4.  **`run_bot.sh`**: Script que arranca Aria2 y el Bot.
5.  **`docker-compose.yml`**: Orquestador de la aplicación.
6.  **`requirements.txt`**: Librerías de Python.

---

## 🚀 Paso 3: Despliegue del Bot
Una vez tengas los archivos en la carpeta, ejecuta:

```bash
# Entrar a la carpeta
cd /root/compresorbeto

# Dar permisos al script de arranque
chmod +x run_bot.sh

# Construir y lanzar el contenedor en segundo plano
docker-compose up -d --build
```

---

## 📊 Paso 4: Comandos de Gestión
Para monitorear el bot una vez esté corriendo:

* **Ver logs en tiempo real** (Ideal para ver errores de descarga o FFmpeg):
  ```bash
  docker logs -f compresor_beto_cont
  ```
* **Detener el bot**:
  ```bash
  docker-compose down
  ```
* **Reiniciar el bot**:
  ```bash
  docker-compose restart
  ```

---

## 💡 Solución de Problemas Comunes

### 1. Error de Conexión (Connection Refused)
Si al ejecutar comandos de Docker recibes un error de conexión, el motor de Docker está apagado.
* **Solución**: `systemctl start docker`.

### 2. Archivo no encontrado tras descargar (Aria2)
Si el bot dice que el archivo no está en el disco, es porque la ruta de Aria2 y la del Bot no coinciden.
* **Solución**: Asegúrate de que el `run_bot.sh` tenga el parámetro `--dir=/app` y que el `docker-compose.yml` tenga el volumen `- .:/app` correctamente mapeado.

### 3. Error de ruta `/usr/src/app`
Este error ocurre cuando intentas ejecutar el bot fuera de Docker pero con configuración de Docker.
* **Solución**: Ejecuta siempre mediante `docker-compose up`. Si prefieres usar `screen`, asegúrate de que el código use rutas dinámicas con `BASE_DIR`.

---
*Guía generada para el proyecto CompresorBeto.*
