# -*- mode: python ; coding: utf-8 -*-
# Код: https://pyinstaller.org/
#
# Сборка: python -m PyInstaller CodeQuest.spec
# Результат: dist/CodeQuest/CodeQuest.exe (onedir, портативный Python внутри)

import configparser
import os

# Версия берётся из version.ini — тот же файл читает installer.iss,
# чтобы номер приложения и номер установщика не разъезжались.
_cfg = configparser.ConfigParser()
_cfg.read('version.ini', encoding='utf-8')
_v = _cfg['Version']
VERSION = '{}.{}.{}'.format(_v.get('major', '1'), _v.get('minor', '0'), _v.get('patch', '0'))

# PyInstaller не умеет задавать метаданные exe параметром, только текстовым описанием,
# поэтому файл ресурсов генерируется прямо здесь.
os.makedirs('build', exist_ok=True)
_version_file = os.path.join('build', 'version.txt')
with open(_version_file, 'w', encoding='utf-8-sig') as fh:
    fh.write("""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({0}, {1}, {2}, 0),
    prodvers=({0}, {1}, {2}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Olver009'),
        StringStruct('FileDescription', 'CodeQuest — офлайн-платформа для изучения программирования'),
        StringStruct('FileVersion', '{3}'),
        StringStruct('InternalName', 'CodeQuest'),
        StringStruct('LegalCopyright', 'MIT License (c) 2026 Olver009'),
        StringStruct('OriginalFilename', 'CodeQuest.exe'),
        StringStruct('ProductName', 'CodeQuest'),
        StringStruct('ProductVersion', '{3}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""".format(_v.get('major', '1'), _v.get('minor', '0'), _v.get('patch', '0'), VERSION))

# web/ кладём в бандл целиком, кроме web/books/ — там PDF чужой книги,
# которую мы не имеем права распространять.
EXCLUDE_TOP_DIRS = {'books'}


def collect(src_dir, dest_dir):
    pairs = []
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if not (root.replace('\\', '/') == src_dir and d in EXCLUDE_TOP_DIRS)]
        for name in files:
            src = os.path.join(root, name)
            rel = os.path.relpath(src, src_dir).replace('\\', '/')
            pairs.append((src, os.path.join(dest_dir, os.path.dirname(rel)).replace('\\', '/')))
    return pairs


# PyInstaller собирает из pywinpty только DLL и .pyd, но сам агент консоли не подхватывает,
# и в собранном exe PtyProcess.spawn() роняет python.exe ученика с 0xc0000142 (ConPTY не
# стартует). Берём агентов прямо из пакета: OpenConsole.exe — бэкенд ConPTY (по умолчанию,
# Windows 10 1809+), winpty-agent.exe — legacy-бэкенд для старых систем.
import winpty as _winpty

_winpty_dir = os.path.dirname(os.path.abspath(_winpty.__file__))
winpty_agents = [
    (os.path.join(_winpty_dir, name), 'winpty')
    for name in ('OpenConsole.exe', 'winpty-agent.exe')
    if os.path.exists(os.path.join(_winpty_dir, name))
]

# Без агентов ConPTY в datas запуск кода ученика падает с 0xc0000142:
# в бандл попадают только DLL, а OpenConsole.exe — нет.
datas = collect('web', 'web') + [('lessons', 'lessons'), ('runtime', 'runtime'), ('version.ini', '.')] + winpty_agents

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CodeQuest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_version_file,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CodeQuest',
)
