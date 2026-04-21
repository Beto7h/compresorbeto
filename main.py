import os, time, asyncio, psutil, shutil, subprocess, re, sys, yt_dlp, aria2p
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
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

# --- 🚀 INICIALIZACIÓN DE ARIA2P (RPC) ---
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

# --- 🛠️ UTILIDADES DE SISTEMA ---
def system_startup_cleanup():
    for f in os.listdir("."):
        if any(f.startswith(prefix) for prefix in ["in_", "out_", "thumb_"]):
            try: os.remove(f)
            except: pass

def get_sys_stats_raw():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    _, _, free = shutil.disk_usage(".")
    return f"⚙️ **CPU:** `{cpu}%` | 🧠 **RAM:** `{ram}%` | 💽 **Disco:** `{free // (1024**3)}GB`"

def get_eta(current, total, speed):
    if speed <= 0: return "calculando..."
    remaining_time = (total - current) / speed
    return time.strftime('%H:%M:%S', time.gmtime(remaining_time))

def cleanup(uid):
    for f in os.listdir("."):
        if any(x in f for x in [f"in_{uid}", f"out_{uid}", f"thumb_{uid}"]):
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
        subprocess.run(["ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, "-vframes", "1", "-q:v", "2", thumb_path], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return thumb_path if os.path.exists(thumb_path) else None
    except: return None

# --- 📊 BARRAS DE PROGRESO ---
async def progress_bar(current, total, status_msg, start_time, action):
    uid = status_msg.chat.id
    if uid in cancel_flags: raise Exception("USER_ABORTED")
    now = time.time()
    last_update = last_update_time.get(uid, 0)
    
    if (now - last_update) > 12 or current == total:
        last_update_time[uid] = now
        percentage = current * 100 / total
        speed = current / (now - start_time) if (now - start_time) > 0 else 0
        eta = get_eta(current, total, speed)
        bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
        
        tmp = (f"📥 **{action}**\n« {bar} »  **{percentage:.1f}%**\n\n"
               f"📊 **DATOS:** `{current/(1024**2):.1f}` / `{total/(1024**2):.1f}` MB\n"
               f"🚀 **VEL:** `{speed/(1024**2):.2f}` MB/s | ⏳ **ETA:** `{eta}`\n\n"
               f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
        try: 
            await status_msg.edit(
                tmp, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 CANCELAR", callback_data=f"abort_{uid}")]])
            )
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except: pass

# --- 📊 MONITOR ARIA2 ---
async def aria2_monitor(gid, msg, uid):
    last_update_time[uid] = 0
    while True:
        try:
            download = aria2.get_download(gid)
            if download.is_complete:
                return True
            if download.is_removed:
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
            
            if uid in cancel_flags:
                aria2.remove([download], force=True, files=True)
                return False
                
            await asyncio.sleep(1)
        except: break
    return False

# --- 📥 LÓGICA DE LEECH ---
async def download_link(url, custom_name, msg, uid):
    cancel_flags.discard(uid)
    try:
        download = aria2.add_uris([url])
        gid = download.gid
        
        # ESPERAR ACTIVAMENTE LA FINALIZACIÓN
        success = await aria2_monitor(gid, msg, uid)
        
        if success:
            await asyncio.sleep(2) # Tiempo para liberar el archivo del proceso aria2
            download = aria2.get_download(gid)
            filename = download.files[0].path
            
            # Verificar que el archivo exista realmente en disco
            if not os.path.exists(filename):
                raise Exception("El archivo fue descargado pero no se encuentra en el disco.")

            if custom_name:
                ext = os.path.splitext(filename)[1] or ".mp4"
                new_path = os.path.join(os.path.dirname(filename), f"in_{uid}_{int(time.time())}_{custom_name}{ext}")
                os.rename(filename, new_path); filename = new_path

            class FakeMessage:
                def __init__(self, p, n, msg_obj):
                    self.video = type('obj', (object,), {'file_name': n})
                    self.document = None; self.chat = msg_obj.chat; self.from_user = msg_obj.from_user
                    self.file_path = os.path.abspath(p)
                async def download(self, **kwargs): return self.file_path

            if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
            user_settings[uid]['orig_msg'] = FakeMessage(filename, os.path.basename(filename), msg)
            
            await msg.edit(f"✅ **Leech Aria2 Completado**\n\n📄 `{os.path.basename(filename)}`", reply_markup=get_main_menu(uid))
        else:
            await msg.edit("🛑 **Descarga cancelada o fallida.**")
            cleanup(uid)
            
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{str(e)}`" if "USER_ABORTED" not in str(e) else "🛑 **Cancelado.**")
        cleanup(uid)

# --- ⚙️ FFMPEG MONITOR ---
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
                if duration > 0 and (now - last_update) > 12:
                    percentage = min((current_time_sec / duration) * 100, 100)
                    speed_factor = current_time_sec / (now - start_time) if (now - start_time) > 0 else 0
                    eta_sec = (duration - current_time_sec) / speed_factor if speed_factor > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    tmp = (f"⚙️ **{mode_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
                           f"⚡ **PRESET:** `{settings['v_label']}` | 🚀 **V-ETA:** `{speed_factor:.2f}x`\n"
                           f"⏳ **RESTANTE:** `{eta}`\n\n🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                    try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]]))
                    except FloodWait as e: await asyncio.sleep(e.value)
                    except: pass
                    last_update = now
            except: pass
        if uid in cancel_flags: proc.terminate(); raise Exception("USER_ABORTED")
    await proc.wait()

# --- ⚙️ LÓGICA DE PROCESAMIENTO ---
async def process_logic(uid, msg, settings, mode):
    orig_msg = settings['orig_msg']
    raw_name = orig_msg.video.file_name if orig_msg.video else (orig_msg.document.file_name if orig_msg.document else "video.mp4")
    ext_orig = os.path.splitext(raw_name)[1] or ".mp4"
    extension = ext_orig if settings.get('keep_format', True) else ".mp4"
    
    # Rutas relativas para máxima compatibilidad
    input_path = f"in_{uid}_{int(time.time())}{ext_orig}"
    output_path = f"out_{uid}_{int(time.time())}{extension}"

    try:
        last_update_time[uid] = 0
        final_input = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, time.time(), "PREPARANDO"))
        
        if not os.path.exists(final_input):
            raise Exception("No se encontró el archivo de entrada para procesar.")

        duration = get_duration(final_input)
        if mode == "audio_only":
            cmd = ["ffmpeg", "-y", "-i", final_input, "-c:v", "copy", "-c:a", str(settings['audio_codec']), "-b:a", "192k", "-movflags", "+faststart", "-progress", "pipe:1", output_path]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "CONVIRTIENDO AUDIO")
        else:
            cmd = ["ffmpeg", "-y", "-i", final_input, "-vf", f"scale=-2:{settings['res']},format=yuv420p", "-c:v", "libx264", "-crf", str(settings['crf']), "-preset", str(settings['preset']), "-threads", "0", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", output_path]
            await ffmpeg_monitor(uid, msg, cmd, duration, settings, "COMPRIMIENDO VIDEO")

        if not os.path.exists(output_path):
            raise Exception("FFmpeg terminó pero el archivo de salida no fue creado.")

        last_update_time[uid] = 0
        await app.send_video(chat_id=uid, video=output_path, duration=int(get_duration(output_path)), thumb=generate_thumbnail(output_path, uid), file_name=raw_name, supports_streaming=True, progress=progress_bar, progress_args=(msg, time.time(), "SUBIENDO"), caption=f"✅ **Completado**\n\n📄 `{raw_name}`")
        
        try: await msg.delete()
        except: pass
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{e}`" if "USER_ABORTED" not in str(e) else "❌ **Cancelado.**")
    finally:
        active_processes.pop(uid, None); cleanup(uid)

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
    if not text: return await message.reply("⚠️ Uso: `/leech [url] -n [nombre]`")
    url = text.split(" -n ")[0].strip()
    name = text.split(" -n ")[1].strip() if " -n " in text else None
    s_msg = await message.reply("⏳ **Analizando enlace...**")
    await download_link(url, name, s_msg, uid)

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply(f"🎬 **Archivo listo**\n\n{get_config_summary(uid)}", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    await query.answer()
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    
    changed = False
    if data.startswith("set_q_"):
        val = data.split("_")[2]
        user_settings[uid]['crf'] = val
        user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[val]
        changed = True
    elif data.startswith("set_r_"): user_settings[uid]['res'] = data.split("_")[2]; changed = True
    elif data.startswith("set_v_"):
        parts = data.split("_"); user_settings[uid]['preset'], user_settings[uid]['v_label'] = parts[2], parts[3]
        changed = True
    elif data.startswith("set_aud_"):
        parts = data.split("_"); user_settings[uid]['audio_codec'], user_settings[uid]['a_label'] = parts[2], parts[3]
        changed = True
    elif data == "mode_keep": user_settings[uid]['keep_format'] = True; changed = True
    elif data == "mode_mp4": user_settings[uid]['keep_format'] = False; changed = True
    elif data == "run_comp":
        await processing_queue.put((uid, query.message, user_settings[uid].copy(), "comp"))
        await query.message.edit("⏳ **Añadido a la cola de compresión...**"); return
    elif data == "run_audio_only":
        await processing_queue.put((uid, query.message, user_settings[uid].copy(), "audio_only"))
        await query.message.edit("⏳ **Añadido a la cola de extracción...**"); return
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        if uid in active_processes: active_processes[uid].terminate()
        return

    if changed or "menu_" in data:
        text = f"🛠️ **Ajustes de Video**\n\n{get_config_summary(uid)}" if "settings" in data or "set_" in data else f"🎬 **Menú Principal**\n\n{get_config_summary(uid)}"
        markup = get_settings_menu(uid) if "settings" in data or "set_" in data else get_main_menu(uid)
        try: await query.message.edit(text, reply_markup=markup)
        except: pass

async def worker():
    while True:
        uid, msg, settings, mode = await processing_queue.get()
        await process_logic(uid, msg, settings, mode)
        processing_queue.task_done()

async def main_startup():
    system_startup_cleanup()
    await app.start(); asyncio.create_task(worker())
    print("🔥 Bot Optimizado en línea"); await asyncio.Event().wait()

if __name__ == "__main__": app.run(main_startup())
