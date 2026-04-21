import os, time, asyncio, psutil, shutil, subprocess, re, sys, yt_dlp
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

# Diccionario para rastrear el tiempo de la última actualización por usuario
last_update_time = {}

DEFAULT_SETTINGS = {
    'crf': 24, 
    'preset': 'medium', 
    'res': '720',
    'q_label': 'Estándar', 
    'v_label': 'Medio',
    'audio_codec': 'aac', 
    'a_label': 'AAC',
    'keep_format': True
}

# --- 🛠️ UTILIDADES DE SISTEMA ---
def clean_file_name(name):
    """Limpia el nombre para procesos internos de FFmpeg"""
    if not name: return "video_procesado"
    name_part = os.path.splitext(name)[0]
    clean = re.sub(r'[^a-zA-Z0-9]', '_', name_part)
    return re.sub(r'_+', '_', clean).strip('_')

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
    """Limpia archivos temporales del usuario específico"""
    for f in os.listdir("."):
        if f"in_{uid}" in f or f"out_{uid}" in f or f"thumb_{uid}" in f:
            try: os.remove(f)
            except: pass

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file]
        return float(subprocess.check_output(cmd).decode("utf-8").strip())
    except: return 0

def generate_thumbnail(video_path, uid):
    thumb_path = os.path.abspath(f"thumb_{uid}.jpg")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, 
            "-vframes", "1", "-q:v", "2", thumb_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(thumb_path):
            return thumb_path
    except: pass
    return None

# --- 📥 LÓGICA DE LEECH (DESCARGA REMOTA) ---
async def download_link(url, custom_name, msg, uid):
    # Usamos la misma estructura de nombres que el resto del bot
    output_template = f"in_{uid}_{int(time.time())}_%(title)s.%(ext)s"
    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        await msg.edit(f"🔗 **Procesando enlace...**\n`{url}`")
        
        # Ejecutar descarga en un hilo separado para no bloquear el bot
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)

        # Si el usuario definió un nombre con -n
        if custom_name:
            extension = os.path.splitext(filename)[1]
            if not extension: extension = ".mp4"
            new_path = f"in_{uid}_{int(time.time())}_{custom_name}{extension}"
            os.rename(filename, new_path)
            filename = new_path

        # Clase simulada para que process_logic crea que es un mensaje de Telegram
        class FakeMessage:
            def __init__(self, path, name):
                self.video = type('obj', (object,), {'file_name': name})
                self.document = None
                self.chat = msg.chat
                self.from_user = msg.from_user
            async def download(self, **kwargs):
                return path

        # Inicializar ajustes si es usuario nuevo
        if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
        
        user_settings[uid]['orig_msg'] = FakeMessage(filename, os.path.basename(filename))
        
        await msg.edit(f"✅ **Descarga Completa**\n\n📄 `{os.path.basename(filename)}`", 
                       reply_markup=get_main_menu(uid))

    except Exception as e:
        await msg.edit(f"❌ **Error en Leech:** `{str(e)}`")

# --- 🎮 MENÚS ---
def get_config_summary(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    f_label = "Original" if s.get('keep_format', True) else "MP4"
    return (f"📝 **RESUMEN DE CONFIGURACIÓN:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **Calidad:** `{s['q_label']}` (CRF {s['crf']})\n"
            f"📏 **Resolución:** `{s['res']}p`\n"
            f"⚡ **Velocidad:** `{s['v_label']}`\n"
            f"🎵 **Audio:** `{s['a_label']}` | 📦 **Formato:** `{f_label}`\n"
            f"━━━━━━━━━━━━━━━━━━━━")

def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    keep_v = "✅ " if s.get('keep_format', True) else ""
    force_v = "✅ " if not s.get('keep_format', True) else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞️ AJUSTES DE COMPRESIÓN", callback_data="menu_settings")],
        [InlineKeyboardButton("🚀 INICIAR COMPRESIÓN", callback_data="run_comp")],
        [InlineKeyboardButton("─── OPCIONES DE AUDIO ───", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='MP3' else ''}MP3", callback_data="set_aud_libmp3lame_MP3"),
         InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='AAC' else ''}AAC", callback_data="set_aud_aac_AAC")],
        [InlineKeyboardButton(f"{keep_v}MANTENER ORIGINAL", callback_data="mode_keep"),
         InlineKeyboardButton(f"{force_v}CONVERTIR A MP4", callback_data="mode_mp4")],
        [InlineKeyboardButton("⚡ INICIAR PROCESO DE AUDIO", callback_data="run_audio_only")]
    ])

def get_settings_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 CALIDAD (CRF)", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Baja' else ''}Baja", callback_data="set_q_30"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Estándar' else ''}Estándar", callback_data="set_q_24"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Súper' else ''}Súper", callback_data="set_q_18")],
        [InlineKeyboardButton("📏 RESOLUCIÓN", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('res')=='480' else ''}480p", callback_data="set_r_480"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='720' else ''}720p", callback_data="set_r_720"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='1080' else ''}1080p", callback_data="set_r_1080")],
        [InlineKeyboardButton("⚡ VELOCIDAD DE PROCESO", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Lento' else ''}Lento", callback_data="set_v_slower_Lento"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Medio' else ''}Medio", callback_data="set_v_medium_Medio"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Ultra' else ''}Ultra", callback_data="set_v_ultrafast_Ultra")],
        [InlineKeyboardButton("⬅️ VOLVER AL INICIO", callback_data="menu_main")]
    ])

# --- 📊 BARRAS DE PROGRESO OPTIMIZADAS ---
async def progress_bar(current, total, status_msg, start_time, action):
    uid = status_msg.chat.id
    if uid in cancel_flags: raise Exception("USER_ABORTED")
    
    now = time.time()
    last_update = last_update_time.get(uid, 0)
    
    if (now - last_update) > 15 or current == total:
        last_update_time[uid] = now
        percentage = current * 100 / total
        diff = now - start_time
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
                now = time.time()
                
                if duration > 0 and (now - last_update) > 15:
                    percentage = min((current_time_sec / duration) * 100, 100)
                    elapsed = now - start_time
                    speed_factor = current_time_sec / elapsed if elapsed > 0 else 0
                    eta_sec = (duration - current_time_sec) / speed_factor if speed_factor > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    
                    tmp = (f"⚙️ **{mode_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
                           f"⚡ **PRESET:** `{settings['v_label']}` | 🚀 **V-ETA:** `{speed_factor:.2f}x`\n"
                           f"⏳ **RESTANTE:** `{eta}`\n\n"
                           f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                    
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]])
                    try: await msg.edit(tmp, reply_markup=kb)
                    except: pass
                    last_update = now
            except: pass
            
        if uid in cancel_flags:
            proc.terminate()
            raise Exception("USER_ABORTED")
            
    await proc.wait()

# --- ⚙️ LÓGICA DE PROCESAMIENTO ---
async def process_logic(uid, msg, settings, mode):
    orig_msg = settings['orig_msg']
    raw_name = orig_msg.video.file_name if orig_msg.video else (orig_msg.document.file_name if orig_msg.document else "video.mp4")
    
    extension = os.path.splitext(raw_name)[1] if settings.get('keep_format', True) else ".mp4"
    if not extension: extension = ".mp4"
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, f"in_{uid}_{int(time.time())}{os.path.splitext(raw_name)[1]}")
    output_path = os.path.join(base_dir, f"out_{uid}_{int(time.time())}{extension}")

    try:
        last_update_time[uid] = 0
        
        # El bot intentará descargar el archivo (si es de Telegram) o usará el ya existente (si es Leech)
        final_input = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, time.time(), "DESCARGANDO"))
        
        if not os.path.exists(final_input):
            raise Exception("No se pudo localizar el archivo de entrada.")

        duration = get_duration(final_input)

        if mode == "audio_only":
            cmd = [
                "ffmpeg", "-y", "-i", final_input, 
                "-c:v", "copy", 
                "-c:a", str(settings['audio_codec']), "-b:a", "192k", 
                "-movflags", "+faststart", 
                "-progress", "pipe:1", output_path
            ]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "CONVIRTIENDO AUDIO")
        else:
            scale = f"scale=-2:{settings['res']}"
            cmd = [
                "ffmpeg", "-y", "-i", final_input,
                "-vf", f"{scale},format=yuv420p",
                "-c:v", "libx264", "-crf", str(settings['crf']),
                "-preset", str(settings['preset']),
                "-threads", "0",
                "-profile:v", "high", "-level", "4.1", 
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", 
                "-progress", "pipe:1", output_path
            ]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "COMPRIMIENDO VIDEO")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("FFmpeg no generó el archivo de salida.")

        thumb = generate_thumbnail(output_path, uid)
        last_update_time[uid] = 0
        
        await app.send_video(
            chat_id=uid, 
            video=output_path, 
            duration=int(get_duration(output_path)), 
            thumb=thumb, 
            file_name=raw_name, 
            supports_streaming=True, 
            progress=progress_bar, progress_args=(msg, time.time(), "SUBIENDO"), 
            caption=f"✅ **Proceso Completado**\n\n📄 `{raw_name}`"
        )
        try: await msg.delete()
        except: pass

    except Exception as e:
        if "USER_ABORTED" in str(e): await msg.edit("❌ **Proceso cancelado.**")
        else: await msg.edit(f"❌ **Error:** `{e}`")
    finally:
        active_processes.pop(uid, None)
        if uid in cancel_flags: cancel_flags.remove(uid)
        last_update_time.pop(uid, None)
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
    await message.reply(f"✨ **¡Bienvenido!** Envíame un video o usa `/leech [enlace]`.\n\n{get_sys_stats_raw()}")

@app.on_message(filters.command("leech") & filters.private)
async def leech_handler(client, message):
    uid = message.from_user.id
    text = message.text.replace("/leech", "").strip()
    
    if not text:
        return await message.reply("⚠️ **Uso:** `/leech [url] -n [nombre]`")

    # Separar link del nombre opcional
    url = text.split(" -n ")[0].strip()
    custom_name = text.split(" -n ")[1].strip() if " -n " in text else None
    
    status_msg = await message.reply("⏳ **Iniciando descarga remota...**")
    await download_link(url, custom_name, status_msg, uid)

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply(f"🎬 **Menú de Procesamiento**\n\n{get_config_summary(uid)}", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()

    if data.startswith("set_q_"):
        val = data.split("_")[2]
        user_settings[uid]['crf'] = val
        user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[val]
    elif data.startswith("set_r_"):
        user_settings[uid]['res'] = data.split("_")[2]
    elif data.startswith("set_v_"):
        parts = data.split("_")
        user_settings[uid]['preset'], user_settings[uid]['v_label'] = parts[2], parts[3]
    elif data.startswith("set_aud_"):
        parts = data.split("_")
        user_settings[uid]['audio_codec'], user_settings[uid]['a_label'] = parts[2], parts[3]
    elif data == "mode_keep":
        user_settings[uid]['keep_format'] = True
    elif data == "mode_mp4":
        user_settings[uid]['keep_format'] = False

    if data == "run_comp":
        await processing_queue.put((uid, query.message, user_settings[uid].copy(), "comp"))
        await query.message.edit("⏳ En cola para compresión...")
    elif data == "run_audio_only":
        await processing_queue.put((uid, query.message, user_settings[uid].copy(), "audio_only"))
        await query.message.edit("⏳ En cola para audio...")
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        if uid in active_processes: active_processes[uid].terminate()
    else:
        text = f"🛠️ **Ajustes**\n\n{get_config_summary(uid)}" if "set_" in data or "settings" in data else f"🎬 **Menú**\n\n{get_config_summary(uid)}"
        markup = get_settings_menu(uid) if "set_" in data or "settings" in data else get_main_menu(uid)
        try: await query.message.edit(text, reply_markup=markup)
        except: pass

async def main_startup():
    await app.start()
    asyncio.create_task(worker())
    print("🔥 Bot iniciado")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
