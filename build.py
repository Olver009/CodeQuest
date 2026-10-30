"""Сборка релиза CodeQuest: приложение, установщик и архив исходников.

Запуск:  python build.py
Нужны:   pip install pyinstaller  и  Inno Setup 6 (winget install JRSoftware.InnoSetup)

Результат в release/:
    CodeQuest-<версия>-portable.zip   — портативная версия (распаковал и запустил)
    CodeQuest-Setup-<версия>.exe      — установщик
    CodeQuest-<версия>-source.zip     — исходники для GitHub/Releases
"""

import configparser
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.join(ROOT, "release")
INNO_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]

# Что попадает в архив исходников. books/ исключён: PDF чужой книги распространять нельзя.
# runtime/ (портативный Python, ~22 МБ) тоже не включаем: это чужие бинарники,
# их не клала в репозиторий. Без него код ученика запускается системным Python.
SOURCE_INCLUDE = ["main.py", "CodeQuest.spec", "installer.iss", "version.ini",
                  "requirements.txt", "start.bat", "README.md", "LICENSE", "icon.ico",
                  "build.py", "lessons", "web"]
SOURCE_EXCLUDE_TOP = {"books"}
SOURCE_EXCLUDE_DIRS = {"__pycache__", ".idea", ".vscode", "node_modules"}
SOURCE_EXCLUDE_FILES = {".gitignore"}


def read_version():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(ROOT, "version.ini"), encoding="utf-8")
    v = cfg["Version"]
    return "{}.{}.{}".format(v.get("major", "1"), v.get("minor", "0"), v.get("patch", "0"))


def run(cmd):
    print("\n>>>", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def find_iscc():
    found = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if found:
        return found
    for path in INNO_CANDIDATES:
        if os.path.exists(path):
            return path
    sys.exit("Inno Setup не найден. Установите: winget install JRSoftware.InnoSetup")


def build_app():
    run([sys.executable, "-m", "PyInstaller", "CodeQuest.spec", "--noconfirm"])
    shutil.copy(os.path.join(ROOT, "version.ini"), os.path.join(ROOT, "dist", "CodeQuest", "version.ini"))


def build_installer(version):
    iscc = find_iscc()
    run([iscc, "installer.iss", "/DAppVersion=" + version])
    run([iscc, "installer.iss", "/DAppVersion=" + version, "/DCoreOnly"])


def zip_tree(zf, base, arc_prefix, top_excludes=SOURCE_EXCLUDE_TOP):
    # base приходит абсолютным, поэтому и корень обхода приводим к пути относительно ROOT,
    # иначе проверка ниже никогда не сработает и web/books/ попадёт в архив.
    base_rel = os.path.relpath(base, ROOT).replace("\\", "/")
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SOURCE_EXCLUDE_DIRS)
        if os.path.relpath(root, ROOT).replace("\\", "/") == base_rel:
            dirs[:] = [d for d in dirs if d not in top_excludes]
        for name in sorted(files):
            if name in SOURCE_EXCLUDE_FILES:
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, ROOT).replace("\\", "/")
            zf.write(src, arc_prefix + rel)


def build_source_zip(version):
    zip_path = os.path.join(RELEASE, "CodeQuest-{}-source.zip".format(version))
    prefix = "CodeQuest/"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for entry in SOURCE_INCLUDE:
            path = os.path.join(ROOT, entry)
            if os.path.isdir(path):
                zip_tree(zf, path, prefix)
            elif os.path.exists(path):
                zf.write(path, prefix + entry)
            else:
                print("  ! пропущено (нет):", entry)
    return zip_path


def build_portable_zip(version):
    src = os.path.join(ROOT, "dist", "CodeQuest")
    if not os.path.isdir(src):
        sys.exit("Нет dist/CodeQuest — сначала соберите приложение.")
    zip_path = os.path.join(RELEASE, "CodeQuest-{}-portable.zip".format(version))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(src):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, src).replace("\\", "/")
                zf.write(full, "CodeQuest/" + rel)
    return zip_path


def main():
    version = read_version()
    print("CodeQuest", version)
    os.makedirs(RELEASE, exist_ok=True)

    build_app()
    build_installer(version)
    portable = build_portable_zip(version)
    sources = build_source_zip(version)

    print("\nГотово. Артефакты:")
    for path in sorted(os.listdir(RELEASE)):
        full = os.path.join(RELEASE, path)
        print("  {:<40} {:>7.1f} МБ".format(path, os.path.getsize(full) / 1048576))
    print("\nПроверьте portable-архив перед публикацией:", portable)
    print("Исходники:", sources)


if __name__ == "__main__":
    main()

