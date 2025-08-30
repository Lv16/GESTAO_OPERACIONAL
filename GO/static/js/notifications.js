
const NotificationManager = {
    container: null,
    loadingOverlay: null,

    init() {
        
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'notification-container';
            document.body.appendChild(this.container);
        }

       
        if (!this.loadingOverlay) {
            this.loadingOverlay = document.createElement('div');
            this.loadingOverlay.className = 'loading-overlay';
            this.loadingOverlay.innerHTML = '<div class="loading-spinner"></div>';
            document.body.appendChild(this.loadingOverlay);
        }
    },

    show(message, type = 'success', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        
        let icon = '';
        switch(type) {
            case 'success':
                icon = '✓';
                break;
            case 'error':
                icon = '✕';
                break;
            case 'info':
                icon = 'ℹ';
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
        
        
        notification.offsetHeight;
        
      
        setTimeout(() => notification.classList.add('show'), 10);

        
        const closeButton = notification.querySelector('.notification-close');
        closeButton.addEventListener('click', () => this.hide(notification));

        
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
        this.loadingOverlay.classList.remove('show');
    }
};


document.addEventListener('DOMContentLoaded', () => {
    NotificationManager.init();
});


document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!form.classList.contains('no-loading')) {
        NotificationManager.showLoading();
    }
});


const originalFetch = window.fetch;
window.fetch = function() {
    NotificationManager.showLoading();
    return originalFetch.apply(this, arguments)
        .finally(() => {
            NotificationManager.hideLoading();
        });
};
