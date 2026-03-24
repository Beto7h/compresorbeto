import os, time, asyncio, psutil, shutil, subprocess, re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from config import Config

app = Client("CompresorElite", Config.API_ID, Config.API_HASH, 
             bot_token=Config.BOT_TOKEN, session_string=Config.SESSION_STRING)

# --- GLOBALES ---
processing_queue = asyncio.Queue()
is_processing = False
user_settings = {} 
cancel_events = {}

DEFAULT_SETTINGS = {'crf': 24, 'preset': 'medium', 'q_label': 'Estándar', 'v_label': 'Medio'}

# --- UTILIDADES ---
def get_sys_stats():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    total, used, free = shutil.disk_usage(".")
    return f"🖥️ **CPU:** {cpu}% | 🧠 **RAM:** {ram}% | 💽 **Libre:** {free // (2**30)}GB"

def cleanup(uid):
    shutil.rmtree(Config.DOWNLOAD_PATH, ignore_errors=True)
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
    for f in os.listdir("."):
        if "_comprimido_" in f or f.endswith((".zip", ".rar", ".7z", ".mp4")):
            try: os.remove(f)
            except: pass

async def split_video(input_file):
    size_mb = os.path.getsize(input_file) / (1024 * 1024)
    if size_mb <= 1950: return [input_file]
    
    # Lógica simplificada de corte rápido
    base = os.path.splitext(input_file)[0]
    out = f"{base}_parte1.mp4"
    subprocess.run(["ffmpeg", "-i", input_file, "-t", "00:30:00", "-c", "copy", out])
    return [out] # Aquí iría la lógica completa de duración calculada

# --- MENÚS ---
def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 CALIDAD", callback_data="n"), InlineKeyboardButton("⚡ VELOCIDAD", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s['q_label']=='Baja' else ''}Baja", callback_data="set_q_30"),
         InlineKeyboardButton(f"{'✅ ' if s['v_label']=='Rápido' else ''}Rápido", callback_data="set_v_ultrafast")],
        [InlineKeyboardButton(f"{'✅ ' if s['q_label']=='Estándar' else ''}Estándar", callback_data="set_q_24"),
         InlineKeyboardButton(f"{'✅ ' if s['v_label']=='Medio' else ''}Medio", callback_data="set_v_medium")],
        [InlineKeyboardButton(f"{'✅ ' if s['q_label']=='Súper' else ''}Súper", callback_data="set_q_18"),
         InlineKeyboardButton(f"{'✅ ' if s['v_label']=='Lento' else ''}Lento", callback_data="set_v_slower")],
        [InlineKeyboardButton("🚀 INICIAR COMPRESIÓN", callback_data="run")]
    ])

# --- WORKER & LOGIC ---
async def worker():
    global is_processing
    while True:
        uid, msg, settings = await processing_queue.get()
        is_processing = True
        cancel_events[uid] = asyncio.Event()
        try:
            await msg.edit("🏗️ **Iniciando...**")
            # Lógica de FFmpeg aquí (resumida para el ejemplo)
            await asyncio.sleep(5) 
            await msg.edit("✅ **Proceso finalizado.**")
        finally:
            cleanup(uid)
            is_processing = False
            processing_queue.task_done()

# --- COMANDOS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    if not is_processing: asyncio.create_task(worker())
    await message.reply(f"👋 **¡Bienvenido!**\nEnvíame un video o link.\n\n{get_sys_stats()}", reply_markup=get_main_menu(message.from_user.id))

@app.on_message(filters.command("help"))
async def help(client, message):
    await message.reply("❓ **Ayuda:**\nSi el video supera los 2GB, se enviará en partes.\nUsa /stats para ver el disco.")

@app.on_message((filters.video | filters.document | filters.regex(r"https?://")) & filters.private)
async def input_h(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    await message.reply("🎬 **Video detectado.** Configuración estándar aplicada:", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb(client, query):
    uid = query.from_user.id
    if query.data == "run":
        await processing_queue.put((uid, query.message, user_settings[uid]))
        await query.message.edit("⏳ **Añadido a la cola.**")
    elif query.data.startswith("set_"):
        # Lógica de actualización de checks ✅
        await query.message.edit_reply_markup(get_main_menu(uid))

app.run()
