import json
import webview
import sys
import os
import threading
import tempfile
import shutil
import subprocess
import re
import atexit
import tkinter as tk
from datetime import date, timedelta

try:
    import winpty
    from winpty import PtyProcess
    from winpty.enums import Backend
except ImportError as e:
    # Backend есть только в pywinpty 2.0+, поэтому нехватка именно этого имени
    # означает старую версию пакета — об этом и пишем пользователю.
    print(f"Ошибка: нужен pywinpty >= 2.0 (сейчас не хватает: {e.name}).")
    print("Установите зависимости: pip install -r requirements.txt")
    sys.exit(1)

# --- НАСТРОЙКИ ---
if getattr(sys, "frozen", False):
    APP_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

RESOURCE_ROOT = getattr(sys, "_MEIPASS", APP_ROOT)
os.chdir(APP_ROOT)

CREATE_NO_WINDOW = 0x08000000

PROGRESS_FILE = os.path.join(APP_ROOT, "progress.json")
# Режим разработчика включается без пересборки .exe: файлом dev.flag в папке
# приложения либо переменной окружения CODEQUEST_DEV=1.
DEV_FLAG_FILE = os.path.join(APP_ROOT, "dev.flag")
DEV_ENV_VAR = "CODEQUEST_DEV"

LANGUAGES = ["python", "java", "cpp", "c", "javascript", "html", "css", "prog"]
LANG_NAMES = {
    "python": "Python", "java": "Java", "cpp": "C++", "c": "C",
    "javascript": "JavaScript", "html": "HTML", "css": "CSS", "prog": "General Code",
}
DEFAULT_LANG = "python"
QUIZ_ONLY_LANGS = {"prog"}

active_pty = None
active_subprocess = None
current_temp_file = None
_totals_cache = {}
_progress_lock = threading.RLock()
# Временные файлы/папки, которые обязаны исчезнуть вместе с приложением:
# mkdtemp-каталоги компиляторов и .py-скрипт Python-PTY. Утекали при падении
# или «закрыть окно» без stop_interactive_code, поэтому реестр + atexit.
_temp_registry = []

def _register_temp(path):
    _temp_registry.append(path)
    return path

def _remove_temp(path):
    if not path:
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
    except OSError:
        pass
    if path in _temp_registry:
        _temp_registry.remove(path)

def _cleanup_temps():
    for path in list(_temp_registry):
        _remove_temp(path)

def _cleanup_stale_temp_dirs():
    # Осиротевшие после предыдущего падения папки: держим только самые
    # свежие на случай параллельного запуска, остальное сносим.
    keep = 3
    for prefix in ("cq_run_", "cq_web_"):
        try:
            tmp_root = tempfile.gettempdir()
            stale = sorted(
                (os.path.join(tmp_root, name) for name in os.listdir(tmp_root)
                 if name.startswith(prefix)),
                key=os.path.getmtime, reverse=True)
        except OSError:
            continue
        for path in stale[keep:]:
            shutil.rmtree(path, ignore_errors=True)

atexit.register(_cleanup_temps)

# --- ПУТИ К РАНТАЙМАМ ---

def get_python_path():
    candidates = []
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(base_dir, "_internal", "runtime", "python", "python.exe"))
        candidates.append(os.path.join(base_dir, "_internal", "runtime", "python.exe"))
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, "runtime", "python", "python.exe"))
            candidates.append(os.path.join(sys._MEIPASS, "runtime", "python.exe"))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(base_dir, "runtime", "python", "python.exe"))
        candidates.append(os.path.join(base_dir, "runtime", "python.exe"))
    for p in candidates:
        if os.path.exists(p):
            return p
    return sys.executable

def get_java_paths():
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal", "runtime", "java", "bin")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "java", "bin")
    javac = os.path.join(base, "javac.exe")
    java = os.path.join(base, "java.exe")
    return (javac if os.path.exists(javac) else None,
            java if os.path.exists(java) else None)

def get_gcc_paths():
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal", "runtime", "mingw64", "bin")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "mingw64", "bin")
    gcc = os.path.join(base, "gcc.exe")
    gpp = os.path.join(base, "g++.exe")
    return (gcc if os.path.exists(gcc) else None,
            gpp if os.path.exists(gpp) else None)

def get_node_path():
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.path.dirname(sys.executable), "_internal", "runtime", "nodejs")
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "nodejs")
    node = os.path.join(base, "node.exe")
    return node if os.path.exists(node) else None

def get_pty_backend():
    agent_dir = os.path.dirname(os.path.abspath(winpty.__file__))
    if os.path.exists(os.path.join(agent_dir, "OpenConsole.exe")):
        return Backend.ConPTY
    if os.path.exists(os.path.join(agent_dir, "winpty-agent.exe")):
        return Backend.WinPTY
    return None

def get_dev_mode():
    if os.path.exists(DEV_FLAG_FILE):
        return True
    return os.environ.get(DEV_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")

def get_active_lang():
    lang = load_data().get('active_lang')
    return lang if lang in LANGUAGES else DEFAULT_LANG

def set_active_lang(lang):
    if lang not in LANGUAGES:
        return {"error": f"Неизвестный язык: {lang}"}
    update_data(lambda data: data.update({'active_lang': lang}))
    return {"success": True}

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

def lessons_path(lang, ui_lang, name):
    return os.path.join(RESOURCE_ROOT, "lessons", lang, ui_lang, name)

def get_roadmap(lang=None):
    lang = lang or get_active_lang()
    ui_lang = get_current_lang()
    filename = lessons_path(lang, ui_lang, "roadmap.json")
    try:
        with open(filename, encoding="utf-8") as f:
            content = f.read()
            return json.loads(content, strict=False) # strict=False разрешает "сырые" переносы строк
    except Exception as e:
        print(f"Ошибка загрузки {filename}: {e}")
        return []

def get_lesson(lesson_id, lang=None):
    lang = lang or get_active_lang()
    ui_lang = get_current_lang()
    filename = lessons_path(lang, ui_lang, f"{lang}_db.json")
    try:
        with open(filename, encoding="utf-8") as f:
            content = f.read()
            db = json.loads(content, strict=False)
            lesson = db.get("lessons", {}).get(str(lesson_id))
            if not lesson:
                return {"error": f"Урок {lesson_id} не найден"}
            lesson["quiz_only"] = lang in QUIZ_ONLY_LANGS
            return lesson
    except Exception as e:
        return {"error": f"Ошибка БД: {e}"}

def get_trophy_test(chapter_id, lang=None):
    lang = lang or get_active_lang()
    ui_lang = get_current_lang()
    filename = lessons_path(lang, ui_lang, "trophies.json")
    try:
        with open(filename, encoding="utf-8") as f:
            content = f.read()
            db = json.loads(content, strict=False)
            trophy = db.get(str(chapter_id))
            if not trophy:
                return {"error": f"Контрольная {chapter_id} не найдена"}
            trophy["quiz_only"] = lang in QUIZ_ONLY_LANGS
            return trophy
    except Exception as e:
        return {"error": f"Ошибка файла: {e}"}

def load_data():
    with _progress_lock:
        if not os.path.exists(PROGRESS_FILE):
            return {}
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

def migrate_progress(data):
    changed = False
    for key in list(data.keys()):
        if key.startswith('status_trophy_'):
            new_key = f"{DEFAULT_LANG}_{key}"
        elif key.startswith('status_'):
            new_key = f"{DEFAULT_LANG}_{key}"
        elif key.startswith('code_trophy_'):
            new_key = f"{DEFAULT_LANG}_{key}"
        elif key.startswith('code_'):
            new_key = f"{DEFAULT_LANG}_{key}"
        elif key.startswith('quiz_'):
            new_key = f"{DEFAULT_LANG}_{key}"
        else:
            continue
        if new_key not in data:
            data[new_key] = data.pop(key)
            changed = True
    if 'achievements' in data:
        legacy = data.pop('achievements')
        if isinstance(legacy, list):
            data.setdefault(f"{DEFAULT_LANG}_achievements", legacy)
        changed = True
    if 'activity_days' not in data:
        legacy_days = _days_from_legacy_streak(data)
        if legacy_days:
            data['activity_days'] = sorted(legacy_days)
            changed = True
    for legacy_key in ('streak', 'streak_frozen', 'last_lesson_date'):
        if legacy_key in data:
            data.pop(legacy_key)
            changed = True
    return changed

def save_data(data):
    with _progress_lock:
        tmp_path = PROGRESS_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PROGRESS_FILE)
        except Exception:
            # Если запись или замена не удались, не оставляем мусор рядом с
            # progress.json — он будет виден пользователю и попадёт в экспорт.
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

def update_data(mutator):
    with _progress_lock:
        data = load_data()
        result = mutator(data)
        save_data(data)
        return result

def _parse_days(raw_days):
    days = set()
    for item in raw_days or []:
        try:
            days.add(date.fromisoformat(item))
        except (TypeError, ValueError):
            continue
    return days

def _days_from_legacy_streak(data):
    last = data.get('last_lesson_date')
    streak = data.get('streak', 0)
    if not last or not isinstance(streak, int) or streak <= 0:
        return set()
    try:
        end = date.fromisoformat(last)
    except (TypeError, ValueError):
        return set()
    return {(end - timedelta(days=i)).isoformat() for i in range(streak)}

def _activity_days(data):
    if isinstance(data.get('activity_days'), list):
        return _parse_days(data['activity_days'])
    return _parse_days(_days_from_legacy_streak(data))

def _streak_run(days, end):
    length = 0
    current = end
    while current in days:
        length += 1
        current -= timedelta(days=1)
    return length

def _mark_active_today(data):
    days = _activity_days(data)
    days.add(date.today())
    data['activity_days'] = sorted(d.isoformat() for d in days)

def save_key(key, value):
    def mutate(data):
        is_lesson_key = any(key.startswith(f"{lang}_status_") for lang in LANGUAGES)
        if value == 'done' and is_lesson_key and data.get(key) != 'done':
            _mark_active_today(data)
        data[key] = value
    update_data(mutate)
    return True

def get_streak_status():
    data = load_data()
    days = _activity_days(data)
    today = date.today()

    if not days:
        return {"streak": 0, "frozen": False}

    last = max(days)
    delta = (today - last).days

    if delta == 0:
        return {"streak": _streak_run(days, today), "frozen": False}
    if delta == 1:
        return {"streak": _streak_run(days, last), "frozen": False}
    if delta == 2:
        return {"streak": _streak_run(days, last), "frozen": True}
    return {"streak": 0, "frozen": False}

def reset_progress():
    # Через update_data, а не save_data({}): сброс обязан идти под тем же
    # _progress_lock, что и остальные записи, иначе параллельное сохранение
    # урока может перезаписать уже очищенный файл.
    def mutate(data):
        data.clear()
    update_data(mutate)
    _totals_cache.clear()
    return True

# --- СТАТИСТИКА ПО ЯЗЫКАМ ---

def _course_totals(lang):
    if lang in _totals_cache:
        return _totals_cache[lang]
    ui_lang = get_current_lang()
    lessons, trophies = 0, 0
    try:
        with open(lessons_path(lang, ui_lang, "roadmap.json"), encoding="utf-8") as f:
            for chapter in json.load(f):
                lessons += len(chapter.get("lessons", []))
                if chapter.get("trophy"):
                    trophies += 1
    except Exception:
        pass
    _totals_cache[lang] = (lessons, trophies)
    return lessons, trophies

def get_lang_stats(lang=None):
    lang = lang or get_active_lang()
    data = load_data()
    lessons_total, trophies_total = _course_totals(lang)
    lessons_done = trophies_done = 0
    trophy_prefix = f"{lang}_status_trophy_"
    lesson_prefix = f"{lang}_status_"
    for key, value in data.items():
        if value != 'done':
            continue
        if key.startswith(trophy_prefix):
            trophies_done += 1
        elif key.startswith(lesson_prefix):
            lessons_done += 1
    return {
        "lang": lang,
        "name": LANG_NAMES.get(lang, lang),
        "lessons_done": lessons_done,
        "lessons_total": lessons_total,
        "trophies_done": trophies_done,
        "trophies_total": trophies_total,
        "done": lessons_done + trophies_done,
        "total": lessons_total + trophies_total,
    }

def get_all_lang_stats():
    return [get_lang_stats(lang) for lang in LANGUAGES]

def clear_all_code():
    lang = get_active_lang()
    def mutate(data):
        keys_to_delete = [
            k for k in data.keys()
            if k.startswith(f"{lang}_code_") or k.startswith(f"{lang}_code_trophy_")
        ]
        for k in keys_to_delete:
            del data[k]
    update_data(mutate)
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
            migrate_progress(new_data)
            # Диалог и чтение файла — вне замка, а замена содержимого идёт
            # через update_data, чтобы не затоптать параллельное сохранение урока.
            def mutate(data):
                data.clear()
                data.update(new_data)
            update_data(mutate)
            _totals_cache.clear()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    return {"success": False}

# --- ВЫПОЛНЕНИЕ КОДА ---

def _js_write(text):
    # Нормализация в единственном месте: все источники вывода (PTY, PIPE,
    # сообщения об ошибках) проходят отсюда, чтобы поведение не расходилось.
    if window:
        try:
            window.evaluate_js(f'window.writeToTerminal({json.dumps(_normalize_newlines(text))})')
        except Exception:
            pass

def _js_done():
    if window:
        try:
            window.evaluate_js('window.terminalProcessEnded()')
        except Exception:
            pass

def _normalize_newlines(text):
    # xterm.js ждёт каноничных \r\n: без этого вывод съезжает "лесенкой".
    # Делаем это в одном месте, чтобы PTY-ветка (Python) и PIPE-ветки
    # (Java/C++/JS/Node) не разошлись поведениюм.
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')

# Буфер для PTY: защищает от разрыва \r\n между чанками read(1024).
# Если чанк заканчивается на одиночный \r, сохраняем его и дописываем
# в следующий — так не потеряем пару \r\n.
_pty_pending_cr = ""

def read_pty_output(proc):
    global _pty_pending_cr
    while True:
        try:
            data = proc.read(1024)
            if data:
                # Если предыдущий чанк закончился на одиночный \r,
                # дописываем его перед текущими данными, чтобы пара \r\n
                # не оказалась в разных чанках.
                if _pty_pending_cr:
                    data = _pty_pending_cr + data
                    _pty_pending_cr = ""
                # Если чанк заканчивается на одиночный \r (без \n после),
                # сохраняем для следующего чанка.
                if data.endswith('\r') and not data.endswith('\r\n'):
                    _pty_pending_cr = data[-1:]
                    data = data[:-1]
                _js_write(data)
            else:
                # При завершении flush-им остаток буфера
                if _pty_pending_cr:
                    _js_write(_pty_pending_cr)
                    _pty_pending_cr = ""
                _js_done()
                break
        except Exception:
            # При ошибке flush-им буфер
            if _pty_pending_cr:
                try:
                    _js_write(_pty_pending_cr)
                except Exception:
                    pass
                _pty_pending_cr = ""
            _js_done()
            break

def _stream_process(proc):
    global active_subprocess
    active_subprocess = proc
    try:
        # text=True включает universal newlines: \r\n и \r от процесса уже
        # превращаются в \n, так что двойная нормализация здесь не нужна.
        for line in proc.stdout:
            _js_write(line)
        proc.wait()
    except Exception as e:
        _js_write(f"Ошибка: {e}\r\n")
    finally:
        active_subprocess = None
        _js_done()

def _run_java_thread(code, tmp_dir):
    try:
        javac, java = get_java_paths()
        if not javac or not java:
            _js_write("Ошибка: Java runtime не найден в runtime/java\n")
            return

        m = re.search(r'public\s+class\s+(\w+)', code)
        class_name = m.group(1) if m else "Main"
        src = os.path.join(tmp_dir, f"{class_name}.java")

        with open(src, "w", encoding="utf-8") as f:
            f.write(code)

        # 1. Компилируем с указанием кодировки исходников
        comp = subprocess.run(
            [javac, "-encoding", "UTF-8", src],
            cwd=tmp_dir, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW
        )
        if comp.returncode != 0:
            _js_write("Ошибка компиляции Java:\n" + comp.stderr)
            return

        # 2. Запускаем JVM с принудительным UTF-8 для stdout и stderr
        proc = subprocess.Popen(
            [
                java,
                "-Dfile.encoding=UTF-8",
                "-Dstdout.encoding=UTF-8",
                "-Dstderr.encoding=UTF-8",
                "-cp", tmp_dir,
                class_name
            ],
            cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=CREATE_NO_WINDOW
        )
        _stream_process(proc)
    except Exception as e:
        _js_write(f"Ошибка: {e}\n")
    finally:
        _remove_temp(tmp_dir)

def _run_c_cpp_thread(code, tmp_dir, lang):
    try:
        gcc, gpp = get_gcc_paths()
        compiler = gpp if lang == 'cpp' else gcc
        if not compiler:
            _js_write(f"Ошибка: компилятор {lang} не найден в runtime/mingw64\n")
            return
        ext = ".cpp" if lang == "cpp" else ".c"
        src = os.path.join(tmp_dir, "main" + ext)
        exe = os.path.join(tmp_dir, "main.exe")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)

        comp = subprocess.run(
            [compiler, src, "-o", exe],
            cwd=tmp_dir, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW
        )
        if comp.returncode != 0:
            _js_write(f"Ошибка компиляции {lang}:\n" + comp.stderr)
            return

        proc = subprocess.Popen(
            [exe], cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=CREATE_NO_WINDOW
        )
        _stream_process(proc)
    except Exception as e:
        _js_write(f"Ошибка: {e}\n")
    finally:
        _remove_temp(tmp_dir)

def _run_js_thread(code, tmp_dir):
    try:
        node = get_node_path()
        if not node:
            _js_write("Ошибка: Node.js не найден в runtime/nodejs\n")
            return
        src = os.path.join(tmp_dir, "main.js")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        proc = subprocess.Popen(
            [node, src], cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', bufsize=1, creationflags=CREATE_NO_WINDOW
        )
        _stream_process(proc)
    except Exception as e:
        _js_write(f"Ошибка: {e}\n")
    finally:
        _remove_temp(tmp_dir)

def _run_web_preview_thread(code, lang):
    try:
        tmp_dir = _register_temp(tempfile.mkdtemp(prefix="cq_web_"))
        path = os.path.join(tmp_dir, "index.html")
        if lang == 'css':
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{code}</style></head><body><h1>CSS Preview</h1><p>Этот блок стилизован вашим CSS.</p></body></html>"""
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        import webbrowser
        webbrowser.open(f"file:///{path}")
        _js_write("HTML/CSS нельзя выполнить в терминале. Открыто в браузере.\n")
    except Exception as e:
        _js_write(f"Ошибка: {e}\n")
    finally:
        _js_done()

def start_interactive_code(user_code):
    global active_pty, current_temp_file
    stop_interactive_code()

    lang = get_active_lang()

    if lang == 'python':
        _remove_temp(current_temp_file)
        fd, current_temp_file = tempfile.mkstemp(suffix=".py")
        _register_temp(current_temp_file)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(user_code)
        python_exe = get_python_path()
        backend = get_pty_backend()
        if backend is None:
            return {"error": "Не найдены файлы ConPTY (OpenConsole.exe). Переустановите CodeQuest."}
        try:
            if backend == Backend.ConPTY:
                os.environ.pop("PYWINPTY_BACKEND", None)
            active_pty = PtyProcess.spawn([python_exe, current_temp_file], backend=backend)
            thread = threading.Thread(target=read_pty_output, args=(active_pty,))
            thread.daemon = True
            thread.start()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    elif lang in ('java', 'cpp', 'c', 'javascript'):
        tmp_dir = _register_temp(tempfile.mkdtemp(prefix="cq_run_"))
        if lang == 'java':
            target = _run_java_thread
            args = (user_code, tmp_dir)
        elif lang in ('c', 'cpp'):
            target = _run_c_cpp_thread
            args = (user_code, tmp_dir, lang)
        else:
            target = _run_js_thread
            args = (user_code, tmp_dir)
        thread = threading.Thread(target=target, args=args)
        thread.daemon = True
        thread.start()
        return {"success": True}

    elif lang in ('html', 'css'):
        thread = threading.Thread(target=_run_web_preview_thread, args=(user_code, lang))
        thread.daemon = True
        thread.start()
        return {"success": True}

    else:
        return {"error": f"Язык {lang} не поддерживает выполнение в терминале"}

def send_input_to_pty(text):
    global active_pty
    if active_pty:
        try:
            if text == '\r': text = '\r\n'
            active_pty.write(text)
        except: pass

def stop_interactive_code():
    global active_pty, active_subprocess
    if active_pty:
        try: active_pty.terminate()
        except: pass
        active_pty = None
    if active_subprocess:
        try: active_subprocess.terminate()
        except: pass
        active_subprocess = None

def minimize_window():
    window.minimize()

def close_window():
    window.destroy()

def move_window(x, y):
    window.move(int(x), int(y))

# --- ДОСТИЖЕНИЯ ---
LANG_ACHIEVEMENTS = {
    "python": [
        {"id": "ach_py_start",     "icon": "ach-py-start.svg",     "lessons": 1},
        {"id": "ach_py_ten",       "icon": "ach-py-ten.svg",       "lessons": 10},
        {"id": "ach_py_master",    "icon": "ach-py-master.svg",    "lessons": 45},
        {"id": "ach_py_collector", "icon": "ach-py-collector.svg", "trophies": 5},
    ],
    "java": [
        {"id": "ach_java_start",     "icon": "ach-java-start.svg",     "lessons": 1},
        {"id": "ach_java_coffee",    "icon": "ach-java-coffee.svg",    "lessons": 10},
        {"id": "ach_java_oop",       "icon": "ach-java-oop.svg",       "lessons": 35},
        {"id": "ach_java_collector", "icon": "ach-java-collector.svg", "trophies": 5},
    ],
    "cpp": [
        {"id": "ach_cpp_start",   "icon": "ach-cpp-start.svg",   "lessons": 1},
        {"id": "ach_cpp_ten",     "icon": "ach-cpp-ten.svg",     "lessons": 10},
        {"id": "ach_cpp_master",  "icon": "ach-cpp-master.svg",  "lessons": 40},
    ],
    "c": [
        {"id": "ach_c_start",   "icon": "ach-c-start.svg",   "lessons": 1},
        {"id": "ach_c_ten",     "icon": "ach-c-ten.svg",     "lessons": 10},
        {"id": "ach_c_master",  "icon": "ach-c-master.svg",  "lessons": 30},
    ],
    "javascript": [
        {"id": "ach_js_start",   "icon": "ach-js-start.svg",   "lessons": 1},
        {"id": "ach_js_ten",     "icon": "ach-js-ten.svg",     "lessons": 10},
        {"id": "ach_js_master",  "icon": "ach-js-master.svg",  "lessons": 40},
    ],
    "html": [
        {"id": "ach_html_start",  "icon": "ach-html-start.svg",  "lessons": 1},
        {"id": "ach_html_ten",    "icon": "ach-html-ten.svg",    "lessons": 10},
        {"id": "ach_html_master", "icon": "ach-html-master.svg", "lessons": 40},
    ],
    "css": [
        {"id": "ach_css_start",  "icon": "ach-css-start.svg",  "lessons": 1},
        {"id": "ach_css_ten",    "icon": "ach-css-ten.svg",    "lessons": 10},
        {"id": "ach_css_master", "icon": "ach-css-master.svg", "lessons": 30},
    ],
    "prog": [
        {"id": "ach_prog_start",  "icon": "ach-prog-start.svg",  "lessons": 1},
        {"id": "ach_prog_ten",    "icon": "ach-prog-ten.svg",    "lessons": 10},
        {"id": "ach_prog_master", "icon": "ach-prog-master.svg", "lessons": 20},
    ],
}

GLOBAL_ACHIEVEMENTS = [
    {"id": "ach_streak_3",     "icon": "ach-global-fire.svg",         "streak": 3},
    {"id": "ach_streak_7",     "icon": "ach-global-fire-7.svg",       "streak": 7},
    {"id": "ach_streak_30",    "icon": "ach-global-fire-30.svg",      "streak": 30},
    {"id": "ach_first_trophy", "icon": "ach-global-trophy.svg",       "trophies": 1},
    {"id": "ach_all_trophies", "icon": "ach-global-star.svg",         "trophies": 10},
    {"id": "ach_polyglot",     "icon": "ach-global-polyglot.svg",     "langs": 2},
    {"id": "ach_polyglot_pro", "icon": "ach-global-polyglot-pro.svg", "langs": 4},
    {"id": "ach_polyglot_max", "icon": "ach-global-polyglot-max.svg", "langs": 8},
]
GLOBAL_STORAGE_KEY = "global_achievements"

def _lang_progress(data, lang):
    lessons = trophies = 0
    trophy_prefix = f"{lang}_status_trophy_"
    lesson_prefix = f"{lang}_status_"
    for key, value in data.items():
        if value != 'done':
            continue
        if key.startswith(trophy_prefix):
            trophies += 1
        elif key.startswith(lesson_prefix):
            lessons += 1
    return lessons, trophies

def get_achievement_catalog():
    lang = get_active_lang()
    return {
        "lang": lang,
        "lang_name": LANG_NAMES.get(lang, lang),
        "lang_achievements": LANG_ACHIEVEMENTS.get(lang, []),
        "global_achievements": GLOBAL_ACHIEVEMENTS,
    }

def get_unlocked_achievements(lang=None):
    data = load_data()
    lang = lang or get_active_lang()
    return {
        "lang": data.get(f"{lang}_achievements", []),
        "global": data.get(GLOBAL_STORAGE_KEY, []),
    }

def _requirement_met(ach, lessons, trophies, streak, started_langs):
    if 'lessons' in ach and lessons < ach['lessons']:
        return False
    if 'trophies' in ach and trophies < ach['trophies']:
        return False
    if 'streak' in ach and streak < ach['streak']:
        return False
    if 'langs' in ach and started_langs < ach['langs']:
        return False
    return True

def check_achievements():
    try:
        def mutate(data):
            lang = data.get('active_lang') if data.get('active_lang') in LANGUAGES else DEFAULT_LANG
            lessons, trophies = _lang_progress(data, lang)
            streak = get_streak_status()['streak']
            started_langs = sum(1 for l in LANGUAGES if sum(_lang_progress(data, l)) > 0)

            new_achievements = []

            lang_key = f"{lang}_achievements"
            lang_unlocked = data.get(lang_key, [])
            for ach in LANG_ACHIEVEMENTS.get(lang, []):
                if ach['id'] in lang_unlocked:
                    continue
                if _requirement_met(ach, lessons, trophies, streak, started_langs):
                    lang_unlocked.append(ach['id'])
                    new_achievements.append(ach['id'])
            data[lang_key] = lang_unlocked

            global_unlocked = data.get(GLOBAL_STORAGE_KEY, [])
            for ach in GLOBAL_ACHIEVEMENTS:
                if ach['id'] in global_unlocked:
                    continue
                if _requirement_met(ach, lessons, trophies, streak, started_langs):
                    global_unlocked.append(ach['id'])
                    new_achievements.append(ach['id'])
            data[GLOBAL_STORAGE_KEY] = global_unlocked

            return new_achievements

        return update_data(mutate)
    except Exception as e:
        print("Ошибка проверки ачивок:", e)
        return []

def add_time_spent(seconds):
    if seconds <= 0: return False
    def mutate(data):
        today_str = date.today().isoformat()
        if 'time_spent' not in data:
            data['time_spent'] = {}
        data['time_spent'][today_str] = data['time_spent'].get(today_str, 0) + seconds
    update_data(mutate)
    return True

def get_time_stats():
    data = load_data()
    time_spent = data.get('time_spent', {})
    today_str = date.today().isoformat()
    today_seconds = time_spent.get(today_str, 0)

    week_seconds = 0
    for i in range(7):
        day_str = (date.today() - timedelta(days=i)).isoformat()
        week_seconds += time_spent.get(day_str, 0)

    return {
        "today_minutes": today_seconds // 60,
        "week_minutes": week_seconds // 60
    }

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
    check_achievements,
    set_active_lang,
    get_achievement_catalog,
    get_unlocked_achievements,
    get_lang_stats,
    get_all_lang_stats,
    add_time_spent,
    get_time_stats
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

_initial_data = load_data()
if migrate_progress(_initial_data):
    save_data(_initial_data)
_cleanup_stale_temp_dirs()

webview.start()