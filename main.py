import os, time, asyncio, psutil, shutil, subprocess, re, sys, yt_dlp, aria2p, shlex
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

# --- 🛠️ UTILIDADES ---
def system_startup_cleanup():
    for f in os.listdir(BASE_DIR):
        if any(f.startswith(prefix) for prefix in ["in_", "out_", "thumb_"]) or f.endswith("_extracted"):
            try:
                if os.path.isdir(os.path.join(BASE_DIR, f)): shutil.rmtree(os.path.join(BASE_DIR, f))
                else: os.remove(os.path.join(BASE_DIR, f))
            except: pass

def get_sys_stats_raw():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    _, _, free = shutil.disk_usage(BASE_DIR)
    return f"⚙️ **CPU:** `{cpu}%` | 🧠 **RAM:** `{ram}%` | 💽 **Disco:** `{free // (1024**3)}GB`"

def cleanup(uid):
    for f in os.listdir(BASE_DIR):
        if str(uid) in f and any(x in f for x in ["in_", "out_", "thumb_", "_extracted"]):
            try:
                path = os.path.join(BASE_DIR, f)
                if os.path.isdir(path): shutil.rmtree(path)
                else: os.remove(path)
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

# --- 🧠 EXTRACTOR INTELIGENTE (YT-DLP) ---
async def extract_smart_link(url):
    if url.lower().endswith(('.mp4', '.mkv', '.avi', '.zip', '.rar', '.7z')):
        return url, None
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            return info.get('url'), info.get('title')
    except: return url, None

# --- 📦 EXTRACTOR DE COMPRIMIDOS ---
async def run_extraction(file_path, password=None):
    extract_dir = file_path + "_extracted"
    os.makedirs(extract_dir, exist_ok=True)
    cmd = ["7z", "x", file_path, f"-o{extract_dir}", "-y"]
    if password: cmd.append(f"-p{password}")
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0: return None, f"Error 7z: {proc.stderr}"
        video_files = []
        for root, _, files in os.walk(extract_dir):
            for f in files:
                if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.ts')):
                    video_files.append(os.path.join(root, f))
        return video_files, extract_dir
    except Exception as e: return None, str(e)

# --- 📊 BARRA DE PROGRESO UNIVERSAL ---
async def progress_bar(current, total, msg, uid, type_label):
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
    if uid in cancel_flags: raise Exception("USER_ABORTED")

# --- 📊 MONITOR ARIA2 ---
async def aria2_monitor(gid, msg, uid):
    last_update_time[uid] = 0
    while True:
        try:
            download = aria2.get_download(gid)
            if download.is_complete: return True
            if download.is_removed: return False
            now = time.time()
            if (now - last_update_time.get(uid, 0)) > 12:
                last_update_time[uid] = now
                percentage = download.progress
                bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                tmp = (f"📥 **LEECH (ARIA2)**\n« {bar} »  **{percentage:.1f}%**\n\n"
                       f"📊 **DATOS:** `{download.completed_length_string()}` / `{download.total_length_string()}`\n"
                       f"🚀 **VEL:** `{download.download_speed_string()}`\n\n🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 CANCELAR", callback_data=f"abort_{uid}")]]))
                except: pass
            if uid in cancel_flags:
                aria2.remove([download], force=True, files=True)
                return False
            await asyncio.sleep(1)
        except: break
    return False

# --- 📥 LÓGICA DE LEECH ---
async def download_link(url, custom_name, msg, uid, extract_mode=False, password=None):
    cancel_flags.discard(uid)
    try:
        await msg.edit("🔎 **Analizando enlace inteligente...**")
        direct_url, ext_name = await extract_smart_link(url)
        
        download = aria2.add_uris([direct_url])
        success = await aria2_monitor(download.gid, msg, uid)
        
        if success:
            await asyncio.sleep(2)
            download = aria2.get_download(download.gid)
            filename = download.files[0].path
            
            if extract_mode:
                await msg.edit("📦 **Extrayendo archivos...**")
                videos, e_dir = await run_extraction(filename, password)
                if not videos:
                    await msg.edit(f"❌ No se encontraron videos en el comprimido.")
                    return cleanup(uid)
                
                # Menú de selección
                buttons = [[InlineKeyboardButton(f"🎬 {os.path.basename(v)[:20]}", callback_data=f"sel_{idx}")] for idx, v in enumerate(videos)]
                buttons.append([InlineKeyboardButton("❌ CANCELAR", callback_data=f"abort_{uid}")])
                user_settings[uid]['pending_videos'] = videos
                user_settings[uid]['extract_dir'] = e_dir
                await msg.edit("✅ **Extracción lista.** Selecciona el video:", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                # Flujo normal
                ext = os.path.splitext(filename)[1] or ".mp4"
                safe_name = re.sub(r'[\\/*?:"<>|]', "", custom_name or ext_name or f"file_{int(time.time())}")
                new_path = os.path.join(BASE_DIR, f"in_{uid}_{safe_name}{ext}")
                os.rename(filename, new_path)
                
                setup_fake_msg(uid, new_path, msg)
                await msg.edit(f"✅ **Leech Finalizado**\n\n📄 `{os.path.basename(new_path)}`", reply_markup=get_main_menu(uid))
        else:
            await msg.edit("🛑 **Operación cancelada.**")
            cleanup(uid)
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{str(e)}`")
        cleanup(uid)

def setup_fake_msg(uid, path, msg):
    class FakeMessage:
        def __init__(self, p, n, msg_obj):
            self.video = type('obj', (object,), {'file_name': n})
            self.document = None; self.chat = msg_obj.chat; self.from_user = msg_obj.from_user
            self.file_path = p
        async def download(self, **kwargs): return self.file_path
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = FakeMessage(path, os.path.basename(path), msg)

# --- 📊 MONITOR FFMPEG ---
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
                    speed = current_time_sec / (now - start_time) if (now - start_time) > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime((duration - current_time_sec) / speed)) if speed > 0 else "00:00:00"
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    tmp = (f"⚙️ **{mode_label}**\n« {bar} »  **{percentage:.1f}%**\n\n"
                           f"⚡ **PRESET:** `{settings['v_label']}` | 🚀 **V-ETA:** `{speed:.2f}x`\n"
                           f"⏳ **RESTANTE:** `{eta}`\n\n🧪 **SISTEMA**\n{get_sys_stats_raw()}")
                    try: await msg.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]]))
                    except: pass
                    last_update = now
            except: pass
        if uid in cancel_flags:
            try: proc.terminate()
            except: pass
            raise Exception("USER_ABORTED")
    await proc.wait()

# --- ⚙️ PROCESAMIENTO ---
async def process_logic(uid, msg, settings, mode):
    orig_msg = settings['orig_msg']
    raw_name = getattr(orig_msg.video, 'file_name', None) or getattr(orig_msg.document, 'file_name', None) or "video.mp4"
    ext_orig = os.path.splitext(raw_name)[1] or ".mp4"
    extension = ext_orig if settings.get('keep_format', True) else ".mp4"
    input_path = getattr(orig_msg, 'file_path', os.path.join(BASE_DIR, f"in_{uid}_{int(time.time())}{ext_orig}"))
    output_path = os.path.join(BASE_DIR, f"out_{uid}_{int(time.time())}{extension}")

    try:
        if not os.path.exists(input_path):
            input_path = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, uid, "DESCARGANDO"))
        
        duration = get_duration(input_path)
        if mode == "audio_only":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vn", "-c:a", str(settings['audio_codec']), "-b:a", "192k", "-progress", "pipe:1", output_path]
            label = "AUDIO"
        else:
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"scale=-2:{settings['res']}", "-c:v", "libx264", "-crf", str(settings['crf']), "-preset", str(settings['preset']), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", output_path]
            label = "COMPRIMIENDO"

        await ffmpeg_monitor(uid, msg, cmd, duration, settings, label)
        if os.path.exists(output_path):
            await app.send_video(chat_id=uid, video=output_path, duration=int(get_duration(output_path)), thumb=generate_thumbnail(output_path, uid), file_name=raw_name, supports_streaming=True, caption=f"✅ **Procesado**", progress=progress_bar, progress_args=(msg, uid, "SUBIENDO"))
        try: await msg.delete()
        except: pass
    except Exception as e: await msg.edit(f"❌ Error: `{e}`")
    finally: active_processes.pop(uid, None); cleanup(uid)

# --- MENÚS ---
def get_config_summary(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return (f"📝 **CONFIGURACIÓN:**\n"
            f"💎 Calidad: `{s['q_label']}` | 📏 Res: `{s['res']}p`\n"
            f"⚡ Preset: `{s['v_label']}` | 🎵 Audio: `{s['a_label']}`")

def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞️ AJUSTES", callback_data="menu_settings")],
        [InlineKeyboardButton("🚀 INICIAR", callback_data="run_comp")],
        [InlineKeyboardButton("⚡ SOLO AUDIO", callback_data="run_audio_only")]
    ])

def get_settings_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Calidad: {s['q_label']}", callback_data="n")],
        [InlineKeyboardButton("Baja", callback_data="set_q_30"), InlineKeyboardButton("Estd", callback_data="set_q_24"), InlineKeyboardButton("Súper", callback_data="set_q_18")],
        [InlineKeyboardButton(f"Res: {s['res']}p", callback_data="n")],
        [InlineKeyboardButton("480p", callback_data="set_r_480"), InlineKeyboardButton("720p", callback_data="set_r_720"), InlineKeyboardButton("1080p", callback_data="set_r_1080")],
        [InlineKeyboardButton("⬅️ VOLVER", callback_data="menu_main")]
    ])

# --- MANEJADORES ---
@app.on_message(filters.command("leech") & filters.private)
async def leech_handler(client, message):
    uid = message.from_user.id
    try: args = shlex.split(message.text)
    except: args = message.text.split()
    
    if len(args) < 2: return await message.reply("⚠️ `/leech [url] [-e pass]`")
    url = args[1]
    extract_mode = "-e" in args
    password = args[args.index("-e")+1] if extract_mode and len(args) > args.index("-e")+1 else None
    
    s_msg = await message.reply("⏳ **Iniciando...**")
    await download_link(url, None, s_msg, uid, extract_mode, password)

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply(f"🎬 **Archivo**\n\n{get_config_summary(uid)}", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    await query.answer()
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()

    if data.startswith("sel_"):
        idx = int(data.split("_")[1])
        video_path = user_settings[uid]['pending_videos'][idx]
        e_dir = user_settings[uid]['extract_dir']
        final_path = os.path.join(BASE_DIR, f"in_{uid}_ext_{os.path.basename(video_path)}")
        os.rename(video_path, final_path)
        shutil.rmtree(e_dir, ignore_errors=True)
        setup_fake_msg(uid, final_path, query.message)
        await query.message.edit(f"🎬 **Seleccionado:** `{os.path.basename(final_path)}`", reply_markup=get_main_menu(uid))
        return

    if data == "run_comp":
        await processing_queue.put((uid, query.message, user_settings[uid].copy(), "comp"))
        await query.message.edit("⏳ **En cola...**")
    elif data == "abort_":
        cancel_flags.add(uid)
        if uid in active_processes: active_processes[uid].terminate()
    elif data == "menu_settings":
        await query.message.edit(get_config_summary(uid), reply_markup=get_settings_menu(uid))
    elif data == "menu_main":
        await query.message.edit(get_config_summary(uid), reply_markup=get_main_menu(uid))
    elif data.startswith("set_"):
        # Lógica de cambio de ajustes (simplificada)
        if "_q_" in data: user_settings[uid]['crf'] = data.split("_")[2]; user_settings[uid]['q_label'] = "Cambid"
        if "_r_" in data: user_settings[uid]['res'] = data.split("_")[2]
        await query.message.edit(get_config_summary(uid), reply_markup=get_settings_menu(uid))

async def worker():
    while True:
        uid, msg, settings, mode = await processing_queue.get()
        await process_logic(uid, msg, settings, mode)
        processing_queue.task_done()

async def main_startup():
    system_startup_cleanup()
    await app.start()
    asyncio.create_task(worker())
    print("🚀 Bot Activo con Leech Inteligente y Extractor.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
