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
def get_sys_stats():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    total, used, free = shutil.disk_usage(".")
    return f"🖥️ **CPU:** {cpu}% | 🧠 **RAM:** {ram}% | 💽 **Libre:** {free // (2**30)}GB"

def cleanup(uid):
    shutil.rmtree(Config.DOWNLOAD_PATH, ignore_errors=True)
    os.makedirs(Config.DOWNLOAD_PATH, exist_ok=True)
    for f in os.listdir("."):
        if "_comprimido_" in f or f.endswith((".zip", ".rar", ".7z", ".mp4", ".mkv")):
            try: os.remove(f)
            except: pass

# --- 🎮 MENÚS (Definido arriba para evitar NameError) ---
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

# --- 📊 BARRA DE PROGRESO CON ABORTO ---
async def progress_bar(current, total, status_msg, start_time, action):
    uid = status_msg.chat.id
    if uid in cancel_flags:
        cancel_flags.remove(uid)
        raise Exception("USER_ABORTED")
        
    now = time.time()
    diff = now - start_time
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        _, _, free = shutil.disk_usage(".")
        disk_gb = free // (1024**3)
        bar_len = 12
        filled = int(bar_len * current // total)
        bar = '█' * filled + '░' * (bar_len - filled)
        
        tmp = (f"📥 **{action}**\n« {bar} »  **{percentage:.1f}%**\n\n"
               f"📊 **DATOS:** `{current / (1024**2):.1f}` / `{total / (1024**2):.1f}` MB\n"
               f"🚀 **VEL:** `{speed / (1024**2):.2f}` MB/s\n\n"
               f"🧪 **SISTEMA**\n┝ ⚙️ CPU: `{cpu}%`  RAM: `{ram}%` \n┕ 💽 DISCO: `{disk_gb} GB` ")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORTAR PROCESO", callback_data=f"abort_{uid}")]])
        try: await status_msg.edit(tmp, reply_markup=kb)
        except: pass

async def split_video(input_file):
    size_mb = os.path.getsize(input_file) / (1024 * 1024)
    if size_mb <= 1950: return [input_file]
    base = os.path.splitext(input_file)[0]
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file]).decode("utf-8").strip()
    half_time = float(probe) / 2
    parts = []
    for i in range(2):
        out = f"{base}_p{i+1}.mp4"
        ss = "0" if i == 0 else str(half_time)
        cmd = ["ffmpeg", "-y", "-ss", ss, "-t", str(half_time), "-i", input_file, "-c", "copy", out]
        subprocess.run(cmd)
        parts.append(out)
    return parts

# --- ⚙️ LÓGICA DE PROCESAMIENTO ---
async def process_logic(uid, msg, settings):
    orig_msg = settings['orig_msg']
    input_path = os.path.join(Config.DOWNLOAD_PATH, f"input_{uid}")
    start_t = time.time()
    try:
        # Descarga
        if orig_msg.video or orig_msg.document:
            path = await orig_msg.download(file_name=input_path, progress=progress_bar, progress_args=(msg, start_t, "DESCARGANDO"))
        else:
            await msg.edit("🌐 **Aria2 descargando link...**")
            subprocess.run(["aria2c", "-x", "16", "-s", "16", "-o", f"input_{uid}", orig_msg.text, "-d", Config.DOWNLOAD_PATH])
            path = input_path

        # Compresión
        name_base = orig_msg.video.file_name if (orig_msg.video and orig_msg.video.file_name) else "video_pro"
        clean_name = re.sub(r'[^\w\s-]', '', os.path.splitext(name_base)[0]).strip().replace(' ', '_')
        output_name = f"{clean_name}_comprimido_.mp4"
        
        await msg.edit(f"⚙️ **COMPRIMIENDO...**\n💎 Calidad: `{settings['q_label']}`\n⚡ Modo: `{settings['v_label']}`")
        
        proc = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-crf", str(settings['crf']), "-preset", settings['preset'], "-c:a", "aac", "-b:a", "128k", output_name)
        active_processes[uid] = proc 
        await proc.wait()

        # Envío
        final_files = await split_video(output_name)
        for f in final_files:
            await app.send_video(chat_id=uid, video=f, progress=progress_bar, progress_args=(msg, time.time(), "SUBIENDO"), caption=f"✅ **¡COMPLETADO!**\n📦 `{f}`")
            
    except Exception as e:
        if "USER_ABORTED" in str(e): await msg.edit("❌ **Proceso abortado y disco limpio.**")
        else: await msg.edit(f"❌ **Error:** `{e}`")
    finally:
        active_processes.pop(uid, None)
        cleanup(uid)

async def worker():
    global is_processing
    while True:
        uid, msg, settings = await processing_queue.get()
        is_processing = True
        await process_logic(uid, msg, settings)
        is_processing = False
        processing_queue.task_done()

# --- 💬 MANEJADORES ---
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    uid = message.from_user.id
    if uid not in user_settings: user_settings[uid] = DEFAULT_SETTINGS.copy()
    await message.reply(f"👋 **¡Hola!**\n{get_sys_stats()}", reply_markup=get_main_menu(uid))

@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    await message.reply(f"📊 **ESTADO DEL VPS**\n{get_sys_stats()}")

@app.on_message(filters.command("update"))
async def update_cmd(client, message):
    msg = await message.reply("🔄 **Actualizando desde GitHub...**")
    try:
        subprocess.check_output(["git", "pull"])
        await msg.edit("✅ **Código actualizado. Reiniciando bot...**")
        os.execl(sys.executable, sys.executable, *sys.argv)
    except Exception as e:
        await msg.edit(f"❌ **Error en update:** `{e}`")

@app.on_message((filters.video | filters.document | filters.regex(r"https?://")) & filters.private)
async def handle_input(client, message):
    uid = message.from_user.id
    user_settings[uid] = DEFAULT_SETTINGS.copy()
    user_settings[uid]['orig_msg'] = message
    await message.reply("🎬 **Video detectado.** Configura:", reply_markup=get_main_menu(uid))

@app.on_callback_query()
async def cb_handler(client, query):
    uid, data = query.from_user.id, query.data
    if data == "run":
        await processing_queue.put((uid, query.message, user_settings[uid]))
        await query.message.edit("⏳ **En cola...**")
    elif data.startswith("abort_"):
        cancel_flags.add(uid)
        proc = active_processes.get(uid)
        if proc: 
            try: proc.terminate()
            except: pass
        await query.answer("🛑 Abortando...", show_alert=True)
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

# --- 🚀 AUTO CONFIGURACIÓN ---
async def main_startup():
    await app.start()
    await app.set_bot_commands([
        BotCommand("start", "🚀 Iniciar"),
        BotCommand("stats", "📊 Ver VPS"),
        BotCommand("update", "🔄 Actualizar de GitHub")
    ])
    print("✅ Bot encendido y corregido!")
    asyncio.create_task(worker())
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main_startup())
