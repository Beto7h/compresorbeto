import os, time, asyncio, psutil, shutil, subprocess, re, sys, yt_dlp, aria2p
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from config import Config

# --- 📂 CONFIGURACIÓN DE RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- 🛰️ INICIALIZACIÓN DEL CLIENTE ---
app = Client(
    "CompresorElite", 
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN, 
    session_string=Config.SESSION_STRING
)

# --- 🚀 INICIALIZACIÓN DE ARIA2P ---
aria2 = aria2p.API(aria2p.Client(host="http://localhost", port=6800, secret=""))

# --- 🌍 VARIABLES GLOBALES ---
processing_queue = asyncio.Queue()
user_settings = {} 
active_processes = {} 
cancel_flags = set()
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

# --- 📊 LOGGER PARA YT-DLP ---
class YTLProgressLogger:
    def __init__(self, msg, uid, loop):
        self.msg = msg
        self.uid = uid
        self.loop = loop

    def debug(self, msg):
        if msg.startswith('[download]'):
            self.parse_progress(msg)

    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

    def parse_progress(self, msg):
        percent_match = re.search(r'(\d+\.\d+)%', msg)
        if percent_match:
            percent = float(percent_match.group(1))
            asyncio.run_coroutine_threadsafe(self.update_ytl_ui(percent, msg), self.loop)

    async def update_ytl_ui(self, percent, raw_msg):
        if self.uid in cancel_flags: return
        now = time.time()
        if (now - last_update_time.get(self.uid, 0)) < 12: return
        last_update_time[self.uid] = now

        bar = '█' * int(12 * percent // 100) + '░' * (12 - int(12 * percent // 100))
        speed = "Calculando..."
        eta = "..."
        if "at" in raw_msg: speed = raw_msg.split("at")[1].split("ETA")[0].strip()
        if "ETA" in raw_msg: eta = raw_msg.split("ETA")[1].strip()

        tmp = (f"📥 **DESCARGA YTL**\n« {bar} »  **{percent:.1f}%**\n\n"
               f"🚀 **VEL:** `{speed}` | ⏳ **ETA:** `{eta}`\n\n"
               f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
        try: await self.msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 CANCELAR", callback_data=f"abort_{self.uid}")]]))
        except: pass

# --- 🛠️ UTILIDADES ---
def system_startup_cleanup():
    for f in os.listdir(BASE_DIR):
        if any(f.startswith(prefix) for prefix in ["in_", "out_", "thumb_"]):
            try: os.remove(os.path.join(BASE_DIR, f))
            except: pass

def get_sys_stats_raw():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    _, _, free = shutil.disk_usage(BASE_DIR)
    return f"⚙️ **CPU:** `{cpu}%` | 🧠 **RAM:** `{ram}%` | 💽 **Disco:** `{free // (1024**3)}GB`"

def cleanup(uid):
    """Borrado inmediato de archivos relacionados al usuario"""
    for f in os.listdir(BASE_DIR):
        if str(uid) in f:
            try: os.remove(os.path.join(BASE_DIR, f))
            except: pass

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file]
        return float(subprocess.check_output(cmd).decode("utf-8").strip())
    except: return 0

def generate_thumbnail(video_path, uid):
    thumb_path = os.path.join(BASE_DIR, f"thumb_{uid}.jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, "-vframes", "1", "-q:v", "2", thumb_path], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return thumb_path if os.path.exists(thumb_path) else None
    except: return None

# --- 📊 BARRA DE PROGRESO UNIVERSAL ---
async def progress_bar(current, total, msg, uid, type_label):
    if uid in cancel_flags: raise Exception("USER_ABORTED")
    now = time.time()
    if (now - last_update_time.get(uid, 0)) < 12: return
    last_update_time[uid] = now
    percentage = (current / total) * 100
    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
    tmp = (f"📂 **{type_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
           f"📊 **DATOS:** `{current // (1024**2)}MB` / `{total // (1024**2)}MB`\n"
           f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
    try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 CANCELAR", callback_data=f"abort_{uid}")]]))
    except: pass

# --- 📊 MONITOR ARIA2 ---
async def aria2_monitor(gid, msg, uid):
    last_update_time[uid] = 0
    while True:
        try:
            download = aria2.get_download(gid)
            if download.is_complete: return True
            if download.is_removed: return False
            if uid in cancel_flags:
                aria2.remove([download], force=True, files=True)
                return False
            now = time.time()
            if (now - last_update_time.get(uid, 0)) > 12:
                last_update_time[uid] = now
                percentage = download.progress
                bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                tmp = (f"📥 **LEECH (ARIA2)**\n« {bar} »  **{percentage:.1f}%**\n\n"
                       f"📊 **DATOS:** `{download.completed_length_string()}` / `{download.total_length_string()}`\n"
                       f"🚀 **VEL:** `{download.download_speed_string()}` | ⏳ **ETA:** `{download.eta_string()}`\n\n"
                       f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 CANCELAR", callback_data=f"abort_{uid}")]]))
                except: pass
            await asyncio.sleep(1)
        except: break
    return False

# --- 📥 LÓGICA DE LEECH ---
async def download_link(url, custom_name, msg, uid):
    cancel_flags.discard(uid)
    try:
        download = aria2.add_uris([url])
        gid = download.gid
        success = await aria2_monitor(gid, msg, uid)
        if success:
            await asyncio.sleep(2)
            download = aria2.get_download(gid)
            file_basename = os.path.basename(download.files[0].path)
            filename = os.path.join(BASE_DIR, file_basename)
            ext = os.path.splitext(filename)[1] or ".mp4"
            # Renombrado limpio
            final_name = f"{custom_name}{ext}" if custom_name else file_basename
            new_path = os.path.join(BASE_DIR, f"in_{uid}_{final_name}")
            os.rename(filename, new_path)
            await prepare_for_menu(new_path, msg, uid)
        else:
            cleanup(uid)
            await msg.edit("🛑 **Proceso Cancelado y archivos borrados.**")
    except Exception as e:
        cleanup(uid)
        await msg.edit(f"❌ **Error:** `{str(e)}`" if "USER_ABORTED" not in str(e) else "🛑 **Cancelado y Limpiado.**")

# --- 📥 LÓGICA DE YTL ---
async def download_ytl(url, custom_name, msg, uid):
    cancel_flags.discard(uid)
    loop = asyncio.get_event_loop()
    try:
        # Template temporal para evitar conflictos
        output_template = os.path.join(BASE_DIR, f"in_{uid}_temp.%(ext)s")
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'logger': YTLProgressLogger(msg, uid, loop),
        }
        await msg.edit(f"⏳ **YTL:** Iniciando descarga...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            temp_filename = ydl.prepare_filename(info)
        
        if os.path.exists(temp_filename):
            ext = os.path.splitext(temp_filename)[1] or ".mp4"
            final_name = f"{custom_name}{ext}" if custom_name else os.path.basename(temp_filename).replace(f"in_{uid}_temp", "yt_video")
            final_path = os.path.join(BASE_DIR, f"in_{uid}_{final_name}")
            os.rename(temp_filename, final_path)
            await prepare_for_menu(final_path, msg, uid)
        else: raise Exception("No se generó el archivo.")
    except Exception as e:
        cleanup(uid)
        await msg.edit(f"❌ **Error YTL:** `{str(e)}`" if "USER_ABORTED" not in str(e) else "🛑 **Cancelado y Limpiado.**")

# --- 🛠️ UTILIDAD PARA LANZAR MENÚ TRAS DESCARGA ---
async def prepare_for_menu(file_path, msg, uid):
    class FakeMessage:
        def __init__(self, p, n, msg_obj):
            self.video = type('obj', (object,), {'file_name': n})
            self.document = None; self.chat = msg_obj.chat; self.from_user = msg_obj.from_user
            self.file_path = p
        async def download(self, **kwargs): return self.file_path
    
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    filename = os.path.basename(file_path).replace(f"in_{uid}_", "")
    user_settings[uid]['orig_msg'] = FakeMessage(file_path, filename, msg)
    await msg.edit(f"✅ **Descarga Finalizada**\n\n📄 `{filename}`", reply_markup=get_main_menu(uid))

# --- 📊 MONITOR FFMPEG ---
async def ffmpeg_monitor(uid, msg, cmd, duration, settings, mode_label):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    active_processes[uid] = proc
    start_time, last_update = time.time(), 0
    while True:
        line = await proc.stdout.readline()
        if not line: break
        text = line.decode("utf-8")
        if uid in cancel_flags:
            try: proc.terminate()
            except: pass
            raise Exception("USER_ABORTED")
        if "out_time_ms=" in text:
            try:
                current_time_sec = int(text.split("=")[1]) / 1000000
                now = time.time()
                if duration > 0 and (now - last_update) > 12:
                    percentage = min((current_time_sec / duration) * 100, 100)
                    speed = current_time_sec / (now - start_time) if (now - start_time) > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime((duration - current_time_sec) / speed)) if speed > 0 else "..."
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    tmp = (f"⚙️ **{mode_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
                           f"⚡ **PRESET:** `{settings['v_label']}` | 🚀 **V-ETA:** `{speed:.2f}x`\n"
                           f"⏳ **RESTANTE:** `{eta}`\n\n🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                    try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]]))
                    except: pass
                    last_update = now
            except: pass
    await proc.wait()

# --- ⚙️ PROCESAMIENTO ---
async def process_logic(uid, msg, settings, mode):
    orig_msg = settings['orig_msg']
    raw_name = getattr(orig_msg.video, 'file_name', "video.mp4")
    ext_orig = os.path.splitext(raw_name)[1] or ".mp4"
    extension = ext_orig if settings.get('keep_format', True) else ".mp4"
    
    input_path = getattr(orig_msg, 'file_path', os.path.join(BASE_DIR, f"in_{uid}_{raw_name}"))
    output_path = os.path.join(BASE_DIR, f"out_{uid}_{raw_name.replace(ext_orig, extension)}")

    try:
        if not os.path.exists(input_path):
            input_path = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, uid, "DESCARGANDO"))
        
        duration = get_duration(input_path)
        if mode == "audio_only":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-c:a", str(settings['audio_codec']), "-b:a", "192k", "-progress", "pipe:1", output_path]
            label = "EXTRAER AUDIO"
        elif mode == "smart":
            v_bitrate = int((1900 * 1024 * 1024 * 8) / duration) - 128000 if duration > 0 else 2500000
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "libx265", "-b:v", str(v_bitrate), "-preset", "slower", "-c:a", "copy", "-progress", "pipe:1", output_path]
            label = "💎 SMART x265"
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"scale=-2:{settings['res']}", "-c:v", "libx264", "-crf", str(settings['crf']), "-preset", str(settings['preset']), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", output_path]
            label = "COMPRIMIENDO"

        await ffmpeg_monitor(uid, msg, cmd, duration, settings, label)

        if os.path.exists(output_path):
            await app.send_video(
                chat_id=uid, video=output_path, duration=int(get_duration(output_path)), 
                thumb=generate_thumbnail(output_path, uid), file_name=raw_name, 
                supports_streaming=True, caption=f"✅ **Listo:** `{raw_name}`",
                progress=progress_bar, progress_args=(msg, uid, "SUBIENDO")
            )
        try: await msg.delete()
        except: pass
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{e}`" if "USER_ABORTED" not in str(e) else "🛑 **Cancelado y archivos borrados.**")
    finally:
        active_processes.pop(uid, None)
        cleanup(uid)

# --- MENÚS ---
def get_config_summary(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return (f"📝 **CONFIGURACIÓN ACTUAL:**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **Calidad:** `{s['q_label']}` | 📏 **Res:** `{s['res']}p`\n"
            f"⚡ **Preset:** `{s['v_label']}` | 🎵 **Audio:** `{s['a_label']}`\n━━━━━━━━━━━━━━━━━━━━")

def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    keep_v = "✅ " if s.get('keep_format', True) else ""
    force_v = "✅ " if not s.get('keep_format', True) else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞️ AJUSTES AVANZADOS", callback_data="menu_settings")],
        [InlineKeyboardButton("💎 MODO SMART (<2GB)", callback_data="run_smart")],
        [InlineKeyboardButton("🚀 INICIAR COMPRESIÓN", callback_data="run_comp")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='MP3' else ''}MP3", callback_data="set_aud_libmp3lame_MP3"),
         InlineKeyboardButton(f"{'✅ ' if s.get('a_label')=='AAC' else ''}AAC", callback_data="set_aud_aac_AAC")],
        [InlineKeyboardButton(f"{keep_v}ORIGINAL", callback_data="mode_keep"),
         InlineKeyboardButton(f"{force_v}MP4", callback_data="mode_mp4")],
        [InlineKeyboardButton("⚡ SOLO EXTRAER AUDIO", callback_data="run_audio_only")]
    ])

def get_settings_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("── CALIDAD ──", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Baja' else ''}Baja", callback_data="set_q_30"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Estándar' else ''}Estándar", callback_data="set_q_24"),
         InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Súper' else ''}Súper", callback_data="set_q_18")],
        [InlineKeyboardButton("── RESOLUCIÓN ──", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('res')=='480' else ''}480p", callback_data="set_r_480"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='720' else ''}720p", callback_data="set_r_720"),
         InlineKeyboardButton(f"{'✅ ' if s.get('res')=='1080' else ''}1080p", callback_data="set_r_1080")],
        [InlineKeyboardButton("── VELOCIDAD ──", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Lento' else ''}Lento", callback_data="set_v_slower_Lento"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Medio' else ''}Medio", callback_data="set_v_medium_Medio"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Ultra' else ''}Ultra", callback_data="set_v_ultrafast_Ultra")],
        [InlineKeyboardButton("⬅️ VOLVER AL INICIO", callback_data="menu_main")]
    ])

# --- MANEJADORES ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    await message.reply(f"✨ **Compresor Élite Activo**\n\n{get_sys_stats_raw()}")

@app.on_message(filters.command("leech") & filters.private)
async def leech_handler(client, message):
    uid = message.from_user.id
    text = message.text.replace("/leech", "").strip()
    if not text: return await message.reply("⚠️ `/leech [url] -n [nombre]`")
    url = text.split(" -n ")[0].strip()
    name = text.split(" -n ")[1].strip() if " -n " in text else None
    s_msg = await message.reply("⏳ **Aria2:** Iniciando...")
    await download_link(url, name, s_msg, uid)

@app.on_message(filters.command("ytl") & filters.private)
async def ytl_handler(client, message):
    uid = message.from_user.id
    text = message.text.replace("/ytl", "").strip()
    if not text: return await message.reply("⚠️ `/ytl [url] -n [nombre]`")
    url = text.split(" -n ")[0].strip()
    name = text.split(" -n ")[1].strip() if " -n " in text else None
    s_msg = await message.reply("⏳ **YTL:** Preparando...")
    await download_ytl(url, name, s_msg, uid)

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply(f"🎬 **Recibido**\n\n{get_config_summary(uid)}", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    await query.answer()
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    
    changed = False
    if data.startswith("set_q_"):
        val = data.split("_")[2]
        user_settings[uid]['crf'] = val
        user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[val]; changed = True
    elif data.startswith("set_r_"): user_settings[uid]['res'] = data.split("_")[2]; changed = True
    elif data.startswith("set_v_"):
        parts = data.split("_"); user_settings[uid]['preset'], user_settings[uid]['v_label'] = parts[2], parts[3]; changed = True
    elif data.startswith("set_aud_"):
        parts = data.split("_"); user_settings[uid]['audio_codec'], user_settings[uid]['a_label'] = parts[2], parts[3]; changed = True
    elif data == "mode_keep": user_settings[uid]['keep_format'] = True; changed = True
    elif data == "mode_mp4": user_settings[uid]['keep_format'] = False; changed = True
    elif data == "menu_settings": await query.message.edit(get_config_summary(uid), reply_markup=get_settings_menu(uid))
    elif data == "menu_main": await query.message.edit(get_config_summary(uid), reply_markup=get_main_menu(uid))
    elif data == "run_smart":
        cancel_flags.discard(uid); await processing_queue.put((uid, query.message, user_settings[uid].copy(), "smart"))
        await query.message.edit("⏳ **En cola: Smart x265...**")
    elif data == "run_comp":
        cancel_flags.discard(uid); await processing_queue.put((uid, query.message, user_settings[uid].copy(), "comp"))
        await query.message.edit("⏳ **En cola de compresión...**")
    elif data == "run_audio_only":
        cancel_flags.discard(uid); await processing_queue.put((uid, query.message, user_settings[uid].copy(), "audio_only"))
        await query.message.edit("⏳ **En cola de audio...**")
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        if uid in active_processes:
            try: active_processes[uid].terminate()
            except: pass
        cleanup(uid) # LIMPIEZA INMEDIATA
        await query.message.edit("🛑 **Proceso abortado y archivos borrados de inmediato.**")

    if changed:
        try:
            is_in_settings = query.message.reply_markup.inline_keyboard[0][0].text == "── CALIDAD ──"
            markup = get_settings_menu(uid) if is_in_settings else get_main_menu(uid)
            await query.message.edit(get_config_summary(uid), reply_markup=markup)
        except: pass

async def worker():
    while True:
        uid, msg, settings, mode = await processing_queue.get()
        try: await process_logic(uid, msg, settings, mode)
        except: pass
        processing_queue.task_done()

async def main_startup():
    system_startup_cleanup()
    await app.start()
    asyncio.create_task(worker())
    print("🚀 BOT INICIADO")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
