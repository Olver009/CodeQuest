let updateBannerShown = false;
let updateInfo = null;
let updateVersion = null;

async function checkForUpdatesAndShowBanner() {
    if (typeof pywebview === 'undefined') return;
    try {
        const info = await pywebview.api.check_updates();
        if (info && info.update_available) {
            updateInfo = info;
            updateVersion = info.version;
            showUpdateBanner(info.version);
        }
    } catch (e) {
        console.log("Update check failed:", e);
    }
}

function showUpdateBanner(version) {
    if (updateBannerShown) return;
    updateBannerShown = true;

    const banner = document.createElement('div');
    banner.id = 'update-banner';
    banner.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 20px;">🚀</span>
            <div>
                <strong>Доступно обновление ${version}</strong>
                <div style="font-size: 12px; opacity: 0.8;">Новая версия CodeQuest уже здесь</div>
            </div>
        </div>
        <div style="display: flex; gap: 8px;">
            <button id="update-download-btn" style="
                background: #22c55e; color: white; border: none; padding: 6px 16px;
                border-radius: 6px; cursor: pointer; font-weight: bold; font-family: inherit;
            ">Обновить</button>
            <button id="update-close-btn" style="
                background: transparent; color: white; border: 1px solid rgba(255,255,255,0.3);
                padding: 6px 12px; border-radius: 6px; cursor: pointer; font-family: inherit;
            ">Позже</button>
        </div>
    `;

    // Стили для плашки
    Object.assign(banner.style, {
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        background: '#2d2d2d',
        border: '1px solid #3f4245',
        borderRadius: '10px',
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        zIndex: '10000',
        boxShadow: '0 8px 30px rgba(0,0,0,0.6)',
        color: '#e5e7eb',
        fontFamily: 'inherit',
        animation: 'slideIn 0.3s ease'
    });

    // Анимация появления
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(banner);

    // Обработчики
    document.getElementById('update-download-btn').addEventListener('click', async () => {
        const btn = document.getElementById('update-download-btn');
        btn.textContent = 'Скачивание...';
        btn.disabled = true;
        btn.style.opacity = '0.7';

        // Достаём ссылку на установщик из release assets
        // info.url — это html_url релиза, нужно заменить на прямую ссылку
        // Проще: в check_updates возвращать ссылку на asset, но пока используем html_url и просим пользователя скачать
        // Для авто-обновления нужна прямая ссылка на .exe. Добавим её в check_updates.

        const targetUrl = updateInfo.runtime_exists ? updateInfo.core_url : updateInfo.full_url;
        if (!targetUrl) {
            alert('Не найден установщик в релизе');
            btn.textContent = 'Обновить';
            btn.disabled = false;
            btn.style.opacity = '1';
            return;
        }
        const res = await pywebview.api.download_and_install_update(targetUrl);        if (res.error) {
            alert('Ошибка обновления: ' + res.error);
            btn.textContent = 'Обновить';
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    });

    document.getElementById('update-close-btn').addEventListener('click', () => {
        banner.remove();
        updateBannerShown = false; // Разрешаем показать снова при следующем запуске
    });
}