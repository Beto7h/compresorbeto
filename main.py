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
is_processing = False
user_settings = {} 
active_processes = {} 
cancel_flags = set()

DEFAULT_SETTINGS = {
    'crf': 24, 
    'preset': 'medium', 
    'q_label': 'Estándar', 
    'v_label': 'Medio'
}

# --- 🛠️ UTILIDADES DE SISTEMA ---
def get_sys_stats_raw():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    _, _, free = shutil.disk_usage(".")
    disk_gb = free // (1024**3)
    return f"⚙️ CPU: `{cpu}%` | 🧠 RAM: `{ram}%` | 💽 Disco: `{disk_gb}GB`"

def get_eta(current, total, speed):
    if speed <= 0: return "calculando..."
    remaining_time = (total - current) / speed
    return time.strftime('%H:%M:%S', time.gmtime(remaining_time))

def cleanup(uid):
    shutil.rmtree(Config.DOWNLOAD_PATH, ignore_errors=True)
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
    for f in os.listdir("."):
        if "_comprimido_" in f or f.endswith((".zip", ".rar", ".7z", ".mp4", ".mkv")):
            try: os.remove(f)
            except: pass

def get_duration(file):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file]
        return float(subprocess.check_output(cmd).decode("utf-8").strip())
    except: return 0

# --- 🎮 MENÚS ---
def get_main_menu(uid):
    s = user_settings.get(uid, DEFAULT_SETTINGS)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 CALIDAD", callback_data="n"), InlineKeyboardButton("⚡ VELOCIDAD", callback_data="n")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Baja' else ''}Baja", callback_data="set_q_30"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Rápido' else ''}Rápido", callback_data="set_v_ultrafast")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Estándar' else ''}Estándar", callback_data="set_q_24"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Medio' else ''}Medio", callback_data="set_v_medium")],
        [InlineKeyboardButton(f"{'✅ ' if s.get('q_label')=='Súper' else ''}Súper", callback_data="set_q_18"),
         InlineKeyboardButton(f"{'✅ ' if s.get('v_label')=='Lento' else ''}Lento", callback_data="set_v_slower")],
        [InlineKeyboardButton("🚀 INICIAR COMPRESIÓN", callback_data="run")]
    ])

# --- 📊 BARRAS DE PROGRESO ---

async def progress_bar(current, total, status_msg, start_time, action):
    uid = status_msg.chat.id
    if uid in cancel_flags:
        raise Exception("USER_ABORTED")
    
    now = time.time()
    diff = now - start_time
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = get_eta(current, total, speed)
        
        bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
        
        tmp = (f"📤 **{action}**\n"
               f"« {bar} »  **{percentage:.1f}%**\n\n"
               f"📊 **DATOS:** `{current/(1024**2):.1f}` / `{total/(1024**2):.1f}` MB\n"
               f"🚀 **VEL:** `{speed/(1024**2):.2f}` MB/s | ⏳ **ETA:** `{eta}`\n\n"
               f"🧪 **SISTEMA**\n{get_sys_stats_raw()}")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR", callback_data=f"abort_{uid}")]])
        try: await status_msg.edit(tmp, reply_markup=kb)
        except: pass

async def compression_monitor(uid, msg, path, output_name, settings):
    duration = get_duration(path)
    cmd = [
        "ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-crf", str(settings['crf']), 
        "-preset", settings['preset'], "-c:a", "aac", "-b:a", "128k", "-progress", "pipe:1", output_name
    ]
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
                
                if duration > 0 and (time.time() - last_update) > 4:
                    percentage = min((current_time_sec / duration) * 100, 100)
                    elapsed = time.time() - start_time
                    speed_factor = current_time_sec / elapsed if elapsed > 0 else 0
                    remaining_video = duration - current_time_sec
                    eta_sec = remaining_video / speed_factor if speed_factor > 0 else 0
                    eta = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
                    
                    bar = '█' * int(12 * percentage // 100) + '░' * (12 - int(12 * percentage // 100))
                    curr_f = time.strftime('%H:%M:%S', time.gmtime(current_time_sec))
                    total_f = time.strftime('%H:%M:%S', time.gmtime(duration))
                    
                    tmp = (f"⚙️ **COMPRIMIENDO VIDEO**\n"
                           f"« {bar} »  **{percentage:.1f}%**\n\n"
                           f"⏳ **PROGRESO:** `{curr_f}` / `{total_f}`\n"
                           f"🚀 **VEL:** `{speed_factor:.2f}x` | ⏳ **ETA:** `{eta}`\n\n"
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
async def split_video(input_file):
    size_mb = os.path.getsize(input_file) / (1024 * 1024)
    if size_mb <= 1950: return [input_file]
    duration = get_duration(input_file)
    half = duration / 2
    parts = []
    for i in range(2):
        out = f"{os.path.splitext(input_file)[0]}_p{i+1}.mp4"
        ss = "0" if i == 0 else str(half)
        subprocess.run(["ffmpeg", "-y", "-ss", ss, "-t", str(half), "-i", input_file, "-c", "copy", out])
        parts.append(out)
    return parts

async def process_logic(uid, msg, settings):
    orig_msg = settings['orig_msg']
    input_path = os.path.join(Config.DOWNLOAD_PATH, f"input_{uid}")
    try:
        if orig_msg.video or orig_msg.document:
            path = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, time.time(), "DESCARGANDO"))
        else:
            await msg.edit(f"🌐 **Descargando link...**\n\n{get_sys_stats_raw()}")
            subprocess.run(["aria2c", "-x", "16", "-o", f"input_{uid}", orig_msg.text, "-d", Config.DOWNLOAD_PATH])
            path = input_path

        output_name = f"video_{uid}_comprimido_.mp4"
        await compression_monitor(uid, msg, path, output_name, settings)

        final_files = await split_video(output_name)
        for f in final_files:
            await app.send_video(chat_id=uid, video=f, progress=progress_bar, progress_args=(msg, time.time(), "SUBIENDO"), caption=f"✅ **¡Completado!**")
    except Exception as e:
        if "USER_ABORTED" in str(e): await msg.edit("❌ **Proceso cancelado.**")
        else: await msg.edit(f"❌ **Error:** `{e}`")
    finally:
        active_processes.pop(uid, None)
        if uid in cancel_flags: cancel_flags.remove(uid)
        cleanup(uid)

async def worker():
    while True:
        uid, msg, settings = await processing_queue.get()
        await process_logic(uid, msg, settings)
        processing_queue.task_done()

# --- 💬 MANEJADORES ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    await message.reply(f"👋 **¡Hola!**\n\n{get_sys_stats_raw()}", reply_markup=get_main_menu(uid))

@app.on_message(filters.command("update"))
async def update_cmd(client, message):
    msg = await message.reply("🔄 **Actualizando...**")
    try:
        subprocess.check_output(["git", "pull"])
        await msg.edit("✅ **Reiniciando...**")
        os.execl(sys.executable, sys.executable, *sys.argv)
    except Exception as e: await msg.edit(f"❌ **Error:** `{e}`")

@app.on_message((filters.video | filters.document | filters.regex(r"https?://")) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply(f"🎬 **Video detectado.**\n\n{get_sys_stats_raw()}", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    if data == "run":
        await processing_queue.put((uid, query.message, user_settings[uid]))
        await query.message.edit(f"⏳ **En cola...**\n\n{get_sys_stats_raw()}")
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        proc = active_processes.get(uid)
        if proc: proc.terminate()
        await query.answer("🛑 Cancelando...")
    elif data.startswith("set_"):
        if "q_" in data:
            val = data.split("_")[2]
            user_settings[uid]['crf'] = val
            user_settings[uid]['q_label'] = {"30":"Baja", "24":"Estándar", "18":"Súper"}[val]
        else:
            val = data.split("_")[2]
            user_settings[uid]['preset'] = val
            user_settings[uid]['v_label'] = {"ultrafast":"Rápido", "medium":"Medio", "slower":"Lento"}[val]
        await query.message.edit_reply_markup(get_main_menu(uid))

async def main_startup():
    await app.start()
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
