
const NotificationManager = {
    container: null,
    loadingOverlay: null,

    init() {
        
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'notification-container';
            // Acessibilidade: role e aria-live
            this.container.setAttribute('role', 'status');
            this.container.setAttribute('aria-live', 'polite');
            this.container.setAttribute('aria-atomic', 'true');
            document.body.appendChild(this.container);
        }

       
        if (!this.loadingOverlay) {
            this.loadingOverlay = document.createElement('div');
            this.loadingOverlay.className = 'loading-overlay';
            this.loadingOverlay.innerHTML = '<div class="loading-spinner"></div>';
            document.body.appendChild(this.loadingOverlay);
        }
        // Keyboard close support: fecha notificação com ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const current = this.container && this.container.querySelector('.notification.show');
                if (current) this.hide(current);
            }
        });
    },

    show(message, type = 'success', duration = 5000) {
        // If an explicit flow asked us to ignore errors for a short window
        // (to avoid double notifications when a synchronous/benign error fires
        // after a successful operation), respect that signal here.
        if (type === 'error' && window.__rdo_ignore_errors_until && Date.now() < window.__rdo_ignore_errors_until) {
            // suppressed
            return;
        }
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
    notification.setAttribute('tabindex', '0');
    notification.setAttribute('role', 'alert');
        
        let icon = '';
        switch(type) {
            case 'success':
                icon = '<span class="material-icons" aria-hidden="true">check_circle</span>';
                break;
            case 'error':
                icon = '<span class="material-icons" aria-hidden="true">cancel</span>';
                break;
            case 'info':
                icon = '<span class="material-icons" aria-hidden="true">info</span>';
                break;
        }

        notification.innerHTML = `
            <div class="notification-icon">${icon}</div>
            <div class="notification-content">
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close">×</button>
        `;

        this.container.appendChild(notification);
        // Move focus para a notificação (apenas para erros) para que leitores de tela anunciem imediatamente
        if (type === 'error') {
            setTimeout(() => notification.focus(), 80);
        }
        
        
        notification.offsetHeight;
        
      
        setTimeout(() => notification.classList.add('show'), 10);

        
        const closeButton = notification.querySelector('.notification-close');
        closeButton.setAttribute('aria-label', 'Fechar notificação');
        closeButton.addEventListener('click', () => this.hide(notification));
        // Fechar com ESC quando a notificação estiver focada
        notification.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.hide(notification);
        });

        
        if (duration) {
            setTimeout(() => this.hide(notification), duration);
        }
    },

    hide(notification) {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    },

    showLoading() {
        this.loadingOverlay.classList.add('show');
    },

    hideLoading() {
        // If a full page reload is pending we must not hide the overlay,
        // otherwise the user will see the page briefly in an intermediate state.
        if (window.__rdo_pending_reload) return;
        this.loadingOverlay.classList.remove('show');
    }
};


document.addEventListener('DOMContentLoaded', () => {
    NotificationManager.init();
    // Se havia um shim em window.NotificationManager com applyReal, aplique as chamadas enfileiradas
    if (window.NotificationManager && typeof window.NotificationManager.applyReal === 'function') {
        // evita chamar sobre ele mesmo
        const shim = window.NotificationManager;
        // substitui global pelo real manager
        window.NotificationManager = NotificationManager;
        // aplica chamadas enfileiradas
        shim.applyReal(NotificationManager);
    }
});


document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!form.classList.contains('no-loading')) {
        NotificationManager.showLoading();
    }
});
// Não sobrescrever globalmente window.fetch aqui.
// O utilitário fetchJson irá chamar showLoading/hideLoading quando necessário.
