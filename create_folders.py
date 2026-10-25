import os

def create_empty_lang_folders():
    base_dir = os.path.join("lessons", "python")
    ru_dir = os.path.join(base_dir, "ru")

    if not os.path.exists(ru_dir):
        print(f"❌ Ошибка: Папка {ru_dir} не найдена! Убедись, что русские файлы лежат там.")
        return

    target_langs = ["en", "es", "de", "fr"]
    files_to_create = ["roadmap.json", "python_db.json", "trophies.json"]

    for lang in target_langs:
        lang_dir = os.path.join(base_dir, lang)
        os.makedirs(lang_dir, exist_ok=True)
        print(f"📁 Создана папка: {lang_dir}")

        for file in files_to_create:
            dst = os.path.join(lang_dir, file)

            # Если файл уже существует, не перезаписываем его (чтобы не удалить твой перевод)
            if not os.path.exists(dst):
                with open(dst, 'w', encoding='utf-8') as f:
                    f.write("{}") # Пишем пустой JSON, чтобы приложение не падало
                print(f"  📄 Создан пустой {file} -> {lang}")
            else:
                print(f"  ⏩ {file} уже существует -> {lang} (пропущено)")

if __name__ == "__main__":
    create_empty_lang_folders()
    print("\n✨ Готово! Теперь у тебя есть пустые файлы. Можно вставлять в них переводы.")