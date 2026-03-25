import os, time, asyncio, psutil, shutil, subprocess, re, sys
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
user_settings = {} 
active_processes = {} 
cancel_flags = set()

DEFAULT_SETTINGS = {
    'crf': 24, 
    'preset': 'medium', 
    'res': '720',
    'q_label': 'Estándar', 
    'v_label': 'Medio',
    'audio_codec': 'libmp3lame',
    'a_label': 'MP3'
}

# --- 🛠️ UTILIDADES DE SISTEMA ---
def get_sys_stats_raw():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    _, _, free = shutil.disk_usage(".")
    disk_gb = free // (1024**3)
    return f"⚙️ **CPU:** `{cpu}%` | 🧠 **RAM:** `{ram}%` | 💽 **Disco:** `{disk_gb}GB`"

def get_eta(current, total, speed):
    if speed <= 0: return "calculando..."
    remaining_time = (total - current) / speed
    return time.strftime('%H:%M:%S', time.gmtime(remaining_time))

def cleanup(uid):
    shutil.rmtree(Config.DOWNLOAD_PATH, ignore_errors=True)
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
    for f in os.listdir("."):
        if f"_{uid}" in f or "_convertido" in f or "_compres" in f:
            try: os.remove(f)
            except: pass

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file]
        return float(subprocess.check_output(cmd).decode("utf-8").strip())
    except: return 0

def generate_thumbnail(video_path, uid):
    thumb_path = f"thumb_{uid}.jpg"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, 
            "-vframes", "1", "-q:v", "2", thumb_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(thumb_path):
            return thumb_path
    except: pass
    return None

# --- 🎮 MENÚS ---
def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞️ AJUSTES DE COMPRESIÓN", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Baja' else ''}Baja", callback_data="set_q_30"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Estándar' else ''}Estándar", callback_data="set_q_24"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Súper' else ''}Súper", callback_data="set_q_18")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('res')=='480' else ''}480p", callback_data="set_r_480"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='720' else ''}720p", callback_data="set_r_720"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='1080' else ''}1080p", callback_data="set_r_1080")],
        [InlineKeyboardButton("🚀 INICIAR COMPRESIÓN", callback_data="run_comp")],
        [InlineKeyboardButton("🎵 SOLO CONVERTIR AUDIO (MANTENER VIDEO)", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='MP3' else ''}MP3", callback_data="set_aud_libmp3lame_MP3"),
         InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='AAC' else ''}AAC", callback_data="set_aud_aac_AAC")],
        [InlineKeyboardButton("⚡ CONVERTIR AUDIO A MP4", callback_data="run_audio_only")]
    ])

# --- 📊 BARRAS DE PROGRESO ---
async def progress_bar(current, total, status_msg, start_time, action):
    uid = status_msg.chat.id
    if uid in cancel_flags: raise Exception("USER_ABORTED")
    now = time.time()
    diff = now - start_time
    # Actualización estricta cada 4 segundos o al finalizar
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = get_eta(current, total, speed)
        bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
        tmp = (f"📥 **{action}**\n« {bar} »  **{percentage:.1f}%**\n\n"
               f"📊 **DATOS:** `{current/(1024**2):.1f}` / `{total/(1024**2):.1f}` MB\n"
               f"🚀 **VEL:** `{speed/(1024**2):.2f}` MB/s | ⏳ **ETA:** `{eta}`\n\n"
               f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]])
        try: await status_msg.edit(tmp, reply_markup=kb)
        except: pass

async def ffmpeg_monitor(uid, msg, cmd, duration, settings, mode_label):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    active_processes[uid] = proc
    start_time = time.time()
    last_update = 0
    
    while True:
        line = await proc.stdout.readline()
        if not line: break
        text = line.decode("utf-8")
        if "out_time_ms=" in text:
            try:
                ms = int(text.split("=")[1])
                current_time_sec = ms / 1000000
                # Ajustado a 4 segundos para evitar spam a Telegram
                if duration > 0 and (time.time() - last_update) > 4:
                    percentage = min((current_time_sec / duration) * 100, 100)
                    elapsed = time.time() - start_time
                    speed_factor = current_time_sec / elapsed if elapsed > 0 else 0
                    eta_sec = (duration - current_time_sec) / speed_factor if speed_factor > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    
                    tmp = (f"⚙️ **{mode_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
                           f"🎵 **CÓDEC:** `{settings.get('a_label')}` | 🚀 **VEL:** `{speed_factor:.2f}x`\n"
                           f"⏳ **RESTANTE:** `{eta}`\n\n"
                           f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]])
                    try: await msg.edit(tmp, reply_markup=kb)
                    except: pass
                    last_update = time.time()
            except: pass
        if uid in cancel_flags:
            proc.terminate()
            raise Exception("USER_ABORTED")
    await proc.wait()

# --- ⚙️ LÓGICA DE PROCESAMIENTO ---
async def process_logic(uid, msg, settings, mode):
    orig_msg = settings['orig_msg']
    file_name = "video"
    if orig_msg.video: file_name = os.path.splitext(orig_msg.video.file_name)[0]
    elif orig_msg.document: file_name = os.path.splitext(orig_msg.document.file_name)[0]

    input_path = os.path.join(Config.DOWNLOAD_PATH, f"in_{uid}_{int(time.time())}.mkv")
    output_path = f"{file_name}_convertido.mp4"

    try:
        await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, time.time(), "DESCARGANDO"))
        duration = get_duration(input_path)

        if mode == "audio_only":
            # Agregamos -progress pipe:1 para que el ffmpeg_monitor pueda leer el flujo
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "copy", "-c:a", settings['audio_codec'], "-b:a", "192k", "-map", "0", "-progress", "pipe:1", output_path]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "CONVIRTIENDO AUDIO")
        else:
            scale = f"scale=-2:{settings['res']}"
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", scale, "-c:v", "libx264", "-crf", str(settings['crf']), "-preset", settings['preset'], "-c:a", "libmp3lame", "-b:a", "128k", "-progress", "pipe:1", output_path]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "COMPRIMIENDO VIDEO")

        thumb = generate_thumbnail(output_path, uid)
        await app.send_video(
            chat_id=uid, video=output_path, duration=int(get_duration(output_path)), thumb=thumb,
            progress=progress_bar, progress_args=(msg, time.time(), "SUBIENDO"), 
            caption=f"✅ **Proceso Completado**\n🎬 Modo: {'Solo Audio' if mode=='audio_only' else 'Compresión'}\n🎵 Audio: {settings['a_label']}"
        )
        try: await msg.delete()
        except: pass
    except Exception as e:
        if "USER_ABORTED" in str(e):
             await msg.edit("❌ **Proceso cancelado por el usuario.**")
        else:
             await msg.edit(f"❌ **Error:** `{e}`")
    finally:
        active_processes.pop(uid, None)
        if uid in cancel_flags: cancel_flags.remove(uid)
        cleanup(uid)

async def worker():
    while True:
        uid, msg, settings, mode = await processing_queue.get()
        await process_logic(uid, msg, settings, mode)
        processing_queue.task_done()

# --- 💬 MANEJADORES ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    await message.reply(f"✨ **¡Bienvenido!** Envíame un video para empezar.\n\n{get_sys_stats_raw()}")

@app.on_message(filters.command("reiniciar") & filters.private)
async def restart_cmd(client, message):
    await message.reply("🚀 **Reiniciando sistema...**")
    await asyncio.sleep(2)
    os.execl(sys.executable, sys.executable, *sys.argv)

@app.on_message((filters.video | filters.document | filters.regex(r"https?://")) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply("🎬 **Video detectado.** Elige una opción:", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    if data == "run_comp":
        await processing_queue.put((uid, query.message, user_settings[uid], "comp"))
        await query.message.edit("⏳ En cola para compresión...")
    elif data == "run_audio_only":
        await processing_queue.put((uid, query.message, user_settings[uid], "audio_only"))
        await query.message.edit("⏳ En cola para conversión de audio...")
    elif data.startswith("set_q_"):
        val = data.split("_")[2]
        user_settings[uid]['crf'] = val
        user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[val]
        await query.message.edit_reply_markup(get_main_menu(uid))
    elif data.startswith("set_r_"):
        user_settings[uid]['res'] = data.split("_")[2]
        await query.message.edit_reply_markup(get_main_menu(uid))
    elif data.startswith("set_aud_"):
        parts = data.split("_")
        user_settings[uid]['audio_codec'] = parts[2]
        user_settings[uid]['a_label'] = parts[3]
        await query.message.edit_reply_markup(get_main_menu(uid))
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        if uid in active_processes: active_processes[uid].terminate()
        await query.answer("🛑 Cancelando...")

async def main_startup():
    await app.start()
    await app.set_bot_commands([
        BotCommand("start", "✨ Iniciar"),
        BotCommand("reiniciar", "🚀 Reiniciar")
    ])
    asyncio.create_task(worker())
    print("🔥 Bot iniciado correctamente")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
