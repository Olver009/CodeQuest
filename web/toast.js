function showToast(message, type = 'success', subtitle = '', iconUrl = '') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    // Если передали картинку — показываем её, иначе галочку/крестик
    let iconHtml;
    if (iconUrl) {
        iconHtml = `<img src="${iconUrl}" style="width:28px; height:28px; object-fit:contain; flex-shrink:0;" onerror="this.outerHTML='<div class=\\'toast-icon\\' style=\\'color:#22c55e;\\'>✓</div>'">`;
    } else {
        const icon = type === 'error' ? '✕' : '✓';
        const iconColor = type === 'error' ? '#ef4444' : '#22c55e';
        iconHtml = `<div class="toast-icon" style="color: ${iconColor};">${icon}</div>`;
    }

    toast.innerHTML = `
        ${iconHtml}
        <div class="toast-text">
            ${message}
            ${subtitle ? `<small>${subtitle}</small>` : ''}
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Звук для достижений (триумфальная трель)
function playAchievementSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(523.25, ctx.currentTime); // C5
        osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.1); // E5
        osc.frequency.setValueAtTime(783.99, ctx.currentTime + 0.2); // G5
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.6);
    } catch(e) {}
}