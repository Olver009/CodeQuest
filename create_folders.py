import os
import shutil

def create_all_lang_folders():
    base_dir = "lessons"
    target_langs = ["java", "cpp", "c", "javascript", "html", "css", "prog"]
    locales = ["ru", "en", "es", "de", "fr"]

    for lang in target_langs:
        for loc in locales:
            dir_path = os.path.join(base_dir, lang, loc)
            os.makedirs(dir_path, exist_ok=True)

            # 1. Копируем карту пути из python (чтобы визуал был одинаковый)
            src_roadmap = os.path.join(base_dir, "python", loc, "roadmap.json")
            dst_roadmap = os.path.join(dir_path, "roadmap.json")
            if os.path.exists(src_roadmap):
                shutil.copyfile(src_roadmap, dst_roadmap)
            else:
                with open(dst_roadmap, "w", encoding="utf-8") as f: f.write("[]")

            # 2. Создаем пустую базу уроков, если нет
            db_path = os.path.join(dir_path, f"{lang}_db.json")
            if not os.path.exists(db_path):
                with open(db_path, "w", encoding="utf-8") as f:
                    f.write('{"lessons": {}}')

            # 3. Создаем пустые контрольные, если нет
            trophy_path = os.path.join(dir_path, "trophies.json")
            if not os.path.exists(trophy_path):
                with open(trophy_path, "w", encoding="utf-8") as f:
                    f.write("{}")

            print(f"✅ Создана структура для {lang} ({loc})")

if __name__ == "__main__":
    create_all_lang_folders()