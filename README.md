---

```markdown
# 🎥 Compresor Beto Bot

Bot de Telegram para compresión de video y gestión de audio utilizando Python y FFmpeg. Optimizado para despliegues en servidores Linux (VPS).

## 🚀 Guía de Despliegue Rápido

Sigue estos pasos para instalar y ejecutar el bot desde cero en un servidor Ubuntu/Debian.

### 1. Preparar el Entorno
Primero, instala las herramientas del sistema necesarias:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install ffmpeg screen git python3-pip -y
```

### 2. Clonar y Configurar
Clona el repositorio y entra en la carpeta:
```bash
git clone [https://github.com/Beto7h/compresorbeto.git](https://github.com/Beto7h/compresorbeto.git)
cd compresorbeto
```

Crea o edita el archivo de configuración con tus credenciales:
```bash
nano config.py
```
*(Pega tu API_ID, API_HASH y BOT_TOKEN aquí)*

### 3. Instalar Dependencias Python
Debido a las restricciones de entornos gestionados en Linux, usa el siguiente comando:
```bash
pip3 install pyrogram psutil tgcrypto --break-system-packages
```

### 4. Ejecución Permanente (Screen)
Para que el bot no se apague al cerrar la terminal:

1. **Abrir sesión:** `screen -S betobot`
2. **Lanzar bot:** `python3 main.py`
3. **Salir (Detach):** Presiona `Ctrl + A` y luego la tecla `D`.

---

## 🛠️ Comandos de Mantenimiento

| Acción | Comando |
| :--- | :--- |
| **Volver a ver el bot** | `screen -rd betobot` |
| **Listar procesos** | `screen -ls` |
| **Matar proceso** | `screen -X -S betobot quit` |
| **Actualizar código** | `git pull` |
| **Limpiar basura** | `rm in_* out_* thumb_*` |

## ⚠️ Notas de Seguridad
- El bot utiliza nombres de archivos genéricos (`in_uid.mp4`) internamente para evitar errores de sintaxis con caracteres especiales en FFmpeg.
- Asegúrate de tener suficiente espacio en disco, ya que el procesamiento de video genera archivos temporales pesados.
```

---

### 💡 Un último consejo de "pro":
Si alguna vez el bot se queda "trabado" porque un video era demasiado grande y llenó el disco, usa este comando mágico para limpiar todo lo que se quedó a medias:
`rm -f in_* out_* thumb_*`

¡Con eso ya tienes tu bot documentado y listo para la eternidad! ¿Hay algo más en lo que te pueda ayudar con el código?
