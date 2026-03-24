import os

class Config:
    # Obtén estos datos de https://my.telegram.org
    API_ID = int(os.environ.get("API_ID", 123456)) 
    API_HASH = os.environ.get("API_HASH", "tu_api_hash_aqui")
    
    # Obtén este de @BotFather
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "tu_token_de_bot")
    
    # Tu ID de Telegram (para comandos /stats y /update)
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 00000000))
    
    # String Session (Opcional, dejar en None si no la tienes)
    SESSION_STRING = os.environ.get("SESSION_STRING", None)
    
    # Carpeta de trabajo
    DOWNLOAD_PATH = "./downloads/"
