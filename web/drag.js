let isDragging = false;
let isResizing = false;
let currentDir = '';
let startX, startY, startWinX, startWinY, startW, startH;

document.addEventListener('mousemove', async (e) => {
    if (isDragging || isResizing) return;
    const threshold = 8;
    const w = window.innerWidth;
    const h = window.innerHeight;

    let dir = '';
    if (e.clientX < threshold) dir += 'left';
    if (e.clientX > w - threshold) dir += 'right';
    if (e.clientY < threshold) dir += 'top';
    if (e.clientY > h - threshold) dir += 'bottom';

    if (dir === 'left' || dir === 'right') document.body.style.cursor = 'ew-resize';
    else if (dir === 'top' || dir === 'bottom') document.body.style.cursor = 'ns-resize';
    else if (dir === 'topleft' || dir === 'bottomright') document.body.style.cursor = 'nwse-resize';
    else if (dir === 'topright' || dir === 'bottomleft') document.body.style.cursor = 'nesw-resize';
    else document.body.style.cursor = 'default';
});

document.addEventListener('mousedown', async (e) => {
    // 1. ПРОВЕРКА НА РЕСАЙЗ (изменение размера за края)
    const threshold = 8;
    const w = window.innerWidth;
    const h = window.innerHeight;

    let dir = '';
    if (e.clientX < threshold) dir += 'left';
    if (e.clientX > w - threshold) dir += 'right';
    if (e.clientY < threshold) dir += 'top';
    if (e.clientY > h - threshold) dir += 'bottom';

    if (dir) {
        isResizing = true;
        currentDir = dir;
        startX = e.screenX; startY = e.screenY;
        if (window.pywebview) {
            const isMax = await pywebview.api.is_maximized();
            if (isMax) await pywebview.api.toggle_maximize();
            const rect = await pywebview.api.get_window_rect();
            startW = rect.w; startH = rect.h;
            startWinX = rect.x; startWinY = rect.y;
        }
        e.preventDefault();
        return;
    }

    // 2. ПРОВЕРКА НА ПЕРЕТАСКИВАНИЕ
    // Игнорируем клики по кнопкам, полям ввода, редактору кода и т.д.
    const interactive = e.target.closest('button, a, input, select, textarea, .CodeMirror, .xterm, .node, .sidebar-item, .btn, .icon-btn, .widget, .profile-card, .settings-card, .titlebar-btn, .node-container, .node-tooltip');
    if (interactive) return;

    const isLessonPage = !!document.querySelector('.lesson-topbar');
    const isTitlebar = !!e.target.closest('.titlebar');

    // Логика зон захвата:
    if (isLessonPage) {
        // На уроках, КР и книге — ТОЛЬКО за чёлку
        if (!isTitlebar) return;
    } else {
        // На остальных страницах (главная, профиль и т.д.) — за чёлку ИЛИ за верхнюю область (до 150px)
        if (!isTitlebar && e.clientY > 150) return;
    }

    isDragging = true;
    startX = e.screenX;
    startY = e.screenY;

    if (window.pywebview) {
        const isMax = await pywebview.api.is_maximized();
        if (isMax) {
            await pywebview.api.toggle_maximize();
            const newRect = await pywebview.api.get_window_rect();
            startWinX = newRect.x;
            startWinY = newRect.y;
            startX = e.screenX;
            startY = e.screenY;
        } else {
            const rect = await pywebview.api.get_window_rect();
            startWinX = rect.x;
            startWinY = rect.y;
        }
    }
    e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
    if (isResizing) {
        const dx = e.screenX - startX;
        const dy = e.screenY - startY;
        let newW = startW, newH = startH, newX = startWinX, newY = startWinY;

        if (currentDir.includes('right')) newW = startW + dx;
        if (currentDir.includes('bottom')) newH = startH + dy;
        if (currentDir.includes('left')) { newW = startW - dx; newX = startWinX + dx; }
        if (currentDir.includes('top')) { newH = startH - dy; newY = startWinY + dy; }

        if (window.pywebview) pywebview.api.resize_and_move(newX, newY, newW, newH);
    } else if (isDragging) {
        const dx = e.screenX - startX;
        const dy = e.screenY - startY;
        if (window.pywebview) pywebview.api.move_window(startWinX + dx, startWinY + dy);
    }
});

document.addEventListener('mouseup', () => {
    isDragging = false;
    isResizing = false;
    currentDir = '';
});

// --- ТАЙМЕР УЧЕБЫ ---
setInterval(() => {
    // Считаем время только если окно открыто и в фокусе
    if (document.visibilityState === 'visible' && document.hasFocus()) {
        if (window.pywebview) {
            pywebview.api.add_time_spent(10);
        }
    }
}, 10000); // Каждые 10 секунд