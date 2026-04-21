---

## 🛠️ Guía de Preparación del Servidor (Docker & Compose)

### 1. Verificar si ya tienes Docker instalado
Antes de instalar nada, corre estos comandos. Si te devuelven una versión, ya puedes saltar al paso de despliegue.

* **Para Docker:** `docker --version`
* **Para Docker Compose:** `docker-compose --version`

> **Nota:** Si te sale un mensaje como `command not found`, entonces procede con la instalación.

---

### 2. Instalación de Docker (Ubuntu/Debian)
Copia y pega este bloque de comandos para instalar el motor de Docker:

```bash
# Actualizar el sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias necesarias
sudo apt install apt-transport-https ca-certificates curl software-properties-common -y

# Añadir la llave oficial de Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Añadir el repositorio
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io -y

# Iniciar y habilitar Docker
sudo systemctl start docker
sudo systemctl enable docker
```

---

### 3. Instalación de Docker Compose
Docker Compose es el que nos permite usar el archivo `docker-compose.yml`.

```bash
# Descargar la última versión estable
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Dar permisos de ejecución
sudo chmod +x /usr/local/bin/docker-compose

# Verificar instalación
docker-compose --version
```

---

### 4. Despliegue del Bot en el nuevo VPS
Una vez que tienes Docker listo, estos son los pasos para subir tu bot:

1.  **Crea la carpeta de tu proyecto:**
    ```bash
    mkdir compresorbeto && cd compresorbeto
    ```
2.  **Sube tus archivos** (`main.py`, `config.py`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`).
3.  **Lanza el bot:**
    ```bash
    docker-compose up -d --build
    ```

---

### 5. Comandos de Supervivencia (Mantenimiento)
Si el bot se detiene o el disco se llena (como nos pasó antes), usa estos comandos:

| Objetivo | Comando |
| :--- | :--- |
| **¿Está vivo el bot?** | `docker ps` |
| **¿Qué errores hay?** | `docker logs -f compresor_beto_cont` |
| **Limpiar basura (Gigas)** | `docker system prune -a --volumes -f` |
| **Reiniciar todo** | `docker-compose restart` |
| **Ver espacio en disco** | `df -h` |

---

### 💡 Un último consejo de "pro"
Si usas un VPS con pocos recursos, Docker a veces puede consumir mucha RAM al construir la imagen. Si ves que se queda "pegado" al instalar, asegúrate de que no tienes otros procesos pesados corriendo con `top` o `htop`.

¡Con esto ya eres oficialmente el administrador de tu propia infraestructura! ¿Listo para conquistar otro VPS?
