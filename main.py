import json
import webview
import sys
import os
import threading
import tempfile
import shutil
import tkinter as tk
from datetime import date

try:
    from winpty import PtyProcess
except ImportError:
    print("Ошибка: установите pywinpty (pip install pywinpty)")
    sys.exit(1)

# --- НАСТРОЙКИ ---
# APP_ROOT — каталог, рядом с которым лежат progress.json и портативный runtime.
# У sys._MEIPASS писать нельзя: это временная папка, которую PyInstaller удаляет при выходе.
if getattr(sys, "frozen", False):
    APP_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# RESOURCE_ROOT — где лежат web/ и lessons/: в собранном exe это временный каталог _MEIPASS.
RESOURCE_ROOT = getattr(sys, "_MEIPASS", APP_ROOT)

# Код ученика пишет test_read.txt, log.txt, tasks.json в текущую папку процесса.
# Без этой строки при запуске из Проводника/Ярлыка они могли бы уйти в C:\Windows\System32.
os.chdir(APP_ROOT)

PROGRESS_FILE = os.path.join(APP_ROOT, "progress.json")
DEV_MODE = False
ACTIVE_LANG = "python"

active_pty = None
current_temp_file = None

def get_active_lang():
    return ACTIVE_LANG

def get_python_path():
    if getattr(sys, 'frozen', False):
        # В onedir сборке PyInstaller runtime лежит внутри _internal
        base_dir = os.path.dirname(sys.executable)
        portable_path = os.path.join(base_dir, "_internal", "runtime", "python.exe")
        if os.path.exists(portable_path):
            return portable_path
        # На случай onefile сборки
        if hasattr(sys, '_MEIPASS'):
            portable_path = os.path.join(sys._MEIPASS, "runtime", "python.exe")
            if os.path.exists(portable_path):
                return portable_path
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        portable_path = os.path.join(base_dir, "runtime", "python.exe")
        if os.path.exists(portable_path):
            return portable_path

    return sys.executable

def get_dev_mode():
    return DEV_MODE

def get_current_lang():
    data = load_data()
    return data.get('settings_lang', 'ru')

# --- РАЗМЕР ЭКРАНА ---
def get_screen_size():
    root = tk.Tk()
    root.withdraw()
    return root.winfo_screenwidth(), root.winfo_screenheight()

screen_w, screen_h = get_screen_size()
is_max_state = True
saved_rect = {"x": 100, "y": 100, "w": 1200, "h": 800}

def toggle_maximize():
    global is_max_state, saved_rect
    if is_max_state:
        window.resize(saved_rect["w"], saved_rect["h"])
        window.move(saved_rect["x"], saved_rect["y"])
        is_max_state = False
    else:
        w = window.width if window.width else 1200
        h = window.height if window.height else 800
        x = window.x if window.x is not None else 100
        y = window.y if window.y is not None else 100
        saved_rect = {"x": x, "y": y, "w": w, "h": h}
        window.resize(screen_w, screen_h)
        window.move(0, 0)
        is_max_state = True

def is_maximized():
    return is_max_state

def resize_and_move(x, y, w, h):
    window.resize(int(w), int(h))
    window.move(int(x), int(y))

def get_window_rect():
    return {
        "x": window.x or 0,
        "y": window.y or 0,
        "w": window.width or 1200,
        "h": window.height or 800
    }

# --- ЗАГРУЗКА ДАННЫХ ---

def get_roadmap(lang="python"):
    ui_lang = get_current_lang()
    filename = os.path.join(RESOURCE_ROOT, "lessons", lang, ui_lang, "roadmap.json")
    try:
        with open(filename, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return []

def get_lesson(lesson_id, lang="python"):
    ui_lang = get_current_lang()
    filename = os.path.join(RESOURCE_ROOT, "lessons", lang, ui_lang, f"{lang}_db.json")
    try:
        with open(filename, encoding="utf-8") as f:
            db = json.load(f)
            lesson = db.get("lessons", {}).get(str(lesson_id))
            if not lesson:
                return {"error": f"Урок {lesson_id} не найден"}
            return lesson
    except Exception as e:
        return {"error": f"Ошибка БД: {e}"}

def get_trophy_test(chapter_id, lang="python"):
    ui_lang = get_current_lang()
    filename = os.path.join(RESOURCE_ROOT, "lessons", lang, ui_lang, "trophies.json")
    try:
        with open(filename, encoding="utf-8") as f:
            db = json.load(f)
            trophy = db.get(str(chapter_id))
            if not trophy:
                return {"error": f"Контрольная {chapter_id} не найдена"}
            return trophy
    except Exception as e:
        return {"error": f"Ошибка файла: {e}"}

def load_data():
    if not os.path.exists(PROGRESS_FILE):
        return {}
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_key(key, value):
    data = load_data()
    is_newly_completed = False
    if key.startswith('status_') and not key.startswith('status_trophy') and value == 'done':
        if data.get(key) != 'done':
            is_newly_completed = True

    data[key] = value

    if is_newly_completed:
        today_str = date.today().isoformat()
        last_date_str = data.get('last_lesson_date')
        streak = data.get('streak', 0)
        frozen = data.get('streak_frozen', False)

        if last_date_str != today_str:
            data['last_lesson_date'] = today_str
            if frozen:
                data['streak_frozen'] = False
            else:
                data['streak'] = streak + 1

    save_data(data)
    return True

def get_streak_status():
    data = load_data()
    streak = data.get('streak', 0)
    last_date_str = data.get('last_lesson_date')
    frozen = data.get('streak_frozen', False)
    today = date.today()

    if not last_date_str:
        return {"streak": 0, "frozen": False}

    last_date = date.fromisoformat(last_date_str)
    delta = (today - last_date).days

    if delta == 0:
        return {"streak": streak, "frozen": frozen}
    elif delta == 1:
        return {"streak": streak, "frozen": False}
    elif delta == 2:
        if not frozen:
            data['streak_frozen'] = True
            save_data(data)
        return {"streak": streak, "frozen": True}
    else:
        if streak > 0 or frozen:
            data['streak'] = 0
            data['streak_frozen'] = False
            save_data(data)
        return {"streak": 0, "frozen": False}

def reset_progress():
    save_data({})
    return True

def clear_all_code():
    data = load_data()
    keys_to_delete = [k for k in data.keys() if k.startswith('code_') or k.startswith('code_trophy_')]
    for k in keys_to_delete:
        del data[k]
    save_data(data)
    return True

def export_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {"error": "Нет прогресса для сохранения"}
    file_path = window.create_file_dialog(
        webview.SAVE_DIALOG, directory=APP_ROOT, save_filename="codequest_backup.json", file_types=('JSON Files (*.json)',)
    )
    if file_path:
        try:
            target_path = file_path[0] if isinstance(file_path, (tuple, list)) else file_path
            shutil.copyfile(PROGRESS_FILE, target_path)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    return {"success": False}

def import_progress():
    file_path = window.create_file_dialog(
        webview.OPEN_DIALOG, directory=APP_ROOT, file_types=('JSON Files (*.json)',)
    )
    if file_path:
        try:
            target_path = file_path[0] if isinstance(file_path, (tuple, list)) else file_path
            with open(target_path, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            if not isinstance(new_data, dict):
                return {"error": "Неверный формат файла"}
            save_data(new_data)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    return {"success": False}

def read_pty_output(proc):
    window = webview.windows[0] if webview.windows else None
    while True:
        try:
            data = proc.read(1024)
            if data:
                escaped = json.dumps(data)
                if window:
                    window.evaluate_js(f'window.writeToTerminal({escaped})')
            else:
                if window:
                    window.evaluate_js('window.terminalProcessEnded()')
                break
        except Exception:
            if window:
                window.evaluate_js('window.terminalProcessEnded()')
            break

def start_interactive_code(user_code):
    global active_pty, current_temp_file
    stop_interactive_code()

    if current_temp_file and os.path.exists(current_temp_file):
        try: os.remove(current_temp_file)
        except: pass

    fd, current_temp_file = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(user_code)

    python_exe = get_python_path()

    try:
        active_pty = PtyProcess.spawn([python_exe, current_temp_file])
        thread = threading.Thread(target=read_pty_output, args=(active_pty,))
        thread.daemon = True
        thread.start()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

def send_input_to_pty(text):
    global active_pty
    if active_pty:
        try:
            if text == '\r': text = '\r\n'
            active_pty.write(text)
        except: pass

def stop_interactive_code():
    global active_pty
    if active_pty:
        try: active_pty.terminate()
        except: pass
        active_pty = None

def minimize_window():
    window.minimize()

def close_window():
    window.destroy()

def move_window(x, y):
    window.move(int(x), int(y))

def check_achievements():
    try:
        data = load_data()
        unlocked = data.get('achievements', [])
        new_achievements = []

        done_lessons = 0
        done_trophies = 0
        for k, v in data.items():
            if k.startswith('status_') and v == 'done':
                if k.startswith('status_trophy_'):
                    done_trophies += 1
                else:
                    done_lessons += 1

        streak = data.get('streak', 0)

        conditions = {
            'ach_py_start': done_lessons >= 1,
            'ach_py_ten': done_lessons >= 10,
            'ach_py_master': done_lessons >= 50,
            'ach_first_trophy': done_trophies >= 1,
            'ach_streak_3': streak >= 3,
            'ach_py_collector': done_trophies >= 5
        }

        for ach_id, is_met in conditions.items():
            if is_met and ach_id not in unlocked:
                unlocked.append(ach_id)
                new_achievements.append(ach_id)

        if new_achievements:
            data['achievements'] = unlocked
            save_data(data)

        return new_achievements
    except Exception as e:
        print("Ошибка проверки ачивок:", e)
        return [] # Возвращаем пустой массив при ошибке

window = webview.create_window(
    "CodeQuest",
    "web/index.html",
    width=1200,
    height=800,
    background_color='#252627',
    frameless=True,
    easy_drag=False
)

window.expose(
    get_roadmap,
    get_lesson,
    get_trophy_test,
    load_data,
    save_key,
    get_streak_status,
    reset_progress,
    clear_all_code,
    export_progress,
    import_progress,
    start_interactive_code,
    send_input_to_pty,
    stop_interactive_code,
    minimize_window,
    close_window,
    move_window,
    get_window_rect,
    toggle_maximize,
    resize_and_move,
    get_dev_mode,
    is_maximized,
    get_active_lang,
    check_achievements
)

def on_window_restored():
    try:
        w = window.width
        h = window.height
        window.resize(w + 1, h)
        window.resize(w, h)
        window.evaluate_js("window.dispatchEvent(new Event('resize'))")
    except Exception:
        pass

window.events.restored += on_window_restored



webview.start()