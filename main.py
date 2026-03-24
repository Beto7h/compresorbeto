import os, time, asyncio, psutil, shutil, subprocess, re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from config import Config

# --- 🛰️ INICIALIZACIÓN DEL CLIENTE ---
app = Client(
    "CompresorElite", 
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN, 
    session_string=Config.SESSION_STRING
)

# --- 🌍 VARIABLES GLOBALES ---
processing_queue = asyncio.Queue()
is_processing = False
user_settings = {} 
cancel_events = {}

DEFAULT_SETTINGS = {
    'crf': 24, 
    'preset': 'medium', 
    'q_label': 'Estándar', 
    'v_label': 'Medio'
}

# --- 🛠️ UTILIDADES DE SISTEMA ---
def get_sys_stats():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    total, used, free = shutil.disk_usage(".")
    return f"🖥️ **CPU:** {cpu}% | 🧠 **RAM:** {ram}% | 💽 **Libre:** {free // (2**30)}GB"

def cleanup(uid):
    """El Consejo de Oro: Limpieza total de los 60GB"""
    shutil.rmtree(Config.DOWNLOAD_PATH, ignore_errors=True)
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
    for f in os.listdir("."):
        if "_comprimido_" in f or f.endswith((".zip", ".rar", ".7z", ".mp4", ".mkv")):
            try: os.remove(f)
            except: pass

async def split_video(input_file):
    """Divide videos > 2GB sin perder calidad (Fast Cut)"""
    size_mb = os.path.getsize(input_file) / (1024 * 1024)
    if size_mb <= 1950: 
        return [input_file]
    
    base = os.path.splitext(input_file)[0]
    # Obtenemos duración para dividir en 2 partes exactas
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]).decode("utf-8").strip()
    half_time = float(probe) / 2
    
    parts = []
    for i in range(2):
        out = f"{base}_parte{i+1}.mp4"
        ss = "0" if i == 0 else str(half_time)
        cmd = ["ffmpeg", "-y", "-ss", ss, "-t", str(half_time), "-i", input_file, "-c", "copy", out]
        subprocess.run(cmd)
        parts.append(out)
    return parts

# --- 🎮 MENÚS INTERACTIVOS ---
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

# --- ⚙️ LÓGICA DE PROCESAMIENTO REAL ---
async def process_logic(uid, msg, settings):
    orig_msg = settings['orig_msg']
    input_path = os.path.join(Config.DOWNLOAD_PATH, f"input_{uid}")
    
    try:
        # 1. DESCARGA
        if orig_msg.video or orig_msg.document:
            await msg.edit("📥 **Descargando de Telegram...**")
            path = await orig_msg.download(file_name=input_path)
        else:
            await msg.edit("🌐 **Descargando Link (Aria2)...**")
            cmd_aria = ["aria2c", "-x", "16", "-s", "16", "-o", f"input_{uid}", orig_msg.text, "-d", Config.DOWNLOAD_PATH]
            subprocess.run(cmd_aria)
            path = input_path

        # 2. NOMBRE Y COMPRESIÓN
        name_base = orig_msg.video.file_name if orig_msg.video else "video_pro"
        clean_name = re.sub(r'[^\w\s-]', '', os.path.splitext(name_base)[0]).strip().replace(' ', '_')
        output_name = f"{clean_name}_comprimido_.mp4"

        await msg.edit(f"⚙️ **Comprimiendo:** `{output_name}`\n\n{get_sys_stats()}")
        
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", path, 
            "-c:v", "libx264", "-crf", str(settings['crf']), 
            "-preset", settings['preset'], "-c:a", "aac", "-b:a", "128k", 
            output_name
        ]
        
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        await proc.wait()

        # 3. SPLIT Y ENVÍO
        await msg.edit("📤 **Verificando tamaño y enviando...**")
        final_files = await split_video(output_name)

        for f in final_files:
            await app.send_video(
                chat_id=uid, video=f, 
                caption=f"✅ **Proceso Exitoso**\n📦 `{f}`\n\n{get_sys_stats()}"
            )
            
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{e}`")
    finally:
        cleanup(uid)

# --- 🕒 TRABAJADOR DE COLA ---
async def worker():
    global is_processing
    while True:
        uid, msg, settings = await processing_queue.get()
        is_processing = True
        await process_logic(uid, msg, settings)
        is_processing = False
        processing_queue.task_done()

# --- 💬 MANEJADORES DE EVENTOS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    if not is_processing: asyncio.create_task(worker())
    await message.reply(
        f"👋 **¡Hola {message.from_user.first_name}!**\nEnvíame un video o link para empezar.\n\n{get_sys_stats()}", 
        reply_markup=get_main_menu(message.from_user.id)
    )

@app.on_message((filters.video | filters.document | filters.regex(r"https?://")) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply("🎬 **Video detectado.** Configuración estándar aplicada:", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid = query.from_user.id
    data = query.data
    
    if data == "run":
        pos = processing_queue.qsize() + (1 if is_processing else 0)
        await processing_queue.put((uid, query.message, user_settings[uid]))
        await query.message.edit(f"⏳ **Añadido a la cola.**\nPosición actual: `{pos}`")
    elif data.startswith("set_q_"):
        user_settings[uid]['crf'] = data.split("_")[2]
        user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[data.split("_")[2]]
        await query.message.edit_reply_markup(get_main_menu(uid))
    elif data.startswith("set_v_"):
        user_settings[uid]['preset'] = data.split("_")[2]
        user_settings[uid]['v_label'] = {"ultrafast":"Rápido", "medium":"Medio", "slower":"Lento"}[data.split("_")[2]]
        await query.message.edit_reply_markup(get_main_menu(uid))

# --- 🚀 ARRANQUE ---
if __name__ == "__main__":
    app.run()
