---

### 📄 Copia y pega esto en tu archivo `README.md`

```markdown
# 🚀 CompresorBeto Elite Bot

Bot de Telegram avanzado diseñado para descargar videos mediante enlaces (Leech), comprimirlos usando FFmpeg con configuraciones personalizables y subirlos de nuevo a Telegram. Utiliza **Aria2** con comunicación RPC para descargas ultra rápidas con barra de progreso en tiempo real.

---

## ✨ Características principal
- **Descarga Rápida (Leech):** Integración con Aria2 (soporta links directos, Yandex, etc.).
- **Barra de Progreso Real:** Visualización estilo "Mirror Bot" cada 12 segundos.
- **Compresión Personalizable:** Ajuste de resolución (480p, 720p, 1080p), calidad (CRF) y velocidad (Presets).
- **Extracción de Audio:** Opción para convertir cualquier video a MP3/AAC.
- **Docker Ready:** Despliegue simplificado con aislamiento total del sistema.

---

## 🛠️ Requisitos previos
- **Telegram API:** `API_ID` y `API_HASH` (obtener en [my.telegram.org](https://my.telegram.org)).
- **Bot Token:** Obtener en [@BotFather](https://t.me/BotFather).
- **Docker:** (Recomendado) Para evitar conflictos de dependencias.

---

## 🐳 Instalación con Docker (Método Recomendado)

Este método instala automáticamente Aria2, FFmpeg y todas las librerías de Python.

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/Beto7h/compresorbeto.git](https://github.com/Beto7h/compresorbeto.git)
   cd compresorbeto
   ```

2. **Configurar variables:**
   Edita el archivo `config.py` con tus credenciales de Telegram.

3. **Construir la imagen:**
   ```bash
   docker build -t compresor-bot .
   ```

4. **Ejecutar el contenedor:**
   ```bash
   docker run -d --name mi-bot-corriendo compresor-bot
   ```

---

## 💻 Instalación Manual (Sin Docker)

Si prefieres no usar Docker, asegúrate de estar en un sistema Linux (Debian/Ubuntu):

1. **Instalar dependencias del sistema:**
   ```bash
   sudo apt update && sudo apt install -y aria2 ffmpeg python3-pip
   ```

2. **Instalar librerías de Python:**
   ```bash
   pip install -r requirements.txt --break-system-packages
   ```

3. **Iniciar servidor Aria2 RPC:**
   ```bash
   aria2c --enable-rpc --rpc-listen-all --daemon=true
   ```

4. **Ejecutar el bot:**
   ```bash
   python3 main.py
   ```

---

## ⚙️ Estructura del Proyecto
- `main.py`: Lógica principal del bot y monitor de progreso.
- `Dockerfile`: Instrucciones de construcción para el contenedor.
- `run_bot.sh`: Script de arranque que sincroniza Aria2 y el Bot.
- `config.py`: Configuración de tokens y claves.
- `requirements.txt`: Dependencias necesarias (`pyrogram`, `aria2p`, etc.).

---

## 📝 Notas de Uso
- **Intervalo de Progreso:** La barra de progreso se actualiza cada **12 segundos** para evitar límites de inundación (FloodWait) de Telegram.
- **Limpieza:** El bot limpia automáticamente los archivos temporales al iniciar para ahorrar espacio en disco.
- **Cancelación:** Puedes detener cualquier proceso de descarga o compresión usando el botón 🛑 en el mensaje de progreso.

---

## 🤝 Contribuciones
¡Siéntete libre de hacer un fork, abrir un issue o enviar un PR para mejorar el compresor!
```

---

### 💡 Información adicional para ti (Beto):

1.  **Imágenes de estado**: Si quieres que tu README se vea aún mejor, puedes añadir capturas de pantalla de la barra de progreso que ya te funcionó. Solo sube la imagen a GitHub y añade esto al README: `![Progreso](ruta/de/la/imagen.png)`.
2.  **Archivo de Configuración**: No olvides añadir `config.py` a tu `.gitignore` si planeas hacer el repositorio público, para que nadie robe tus tokens de Telegram.
3.  **Hachoir**: He mantenido `hachoir` en el texto del README si es que lo usas para generar metadatos, pero recuerda que lo importante para la barra es `aria2p`.

¿Te parece que falta algún paso o quieres que detallemos más alguna sección?
