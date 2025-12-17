// static/js/cookies.js

// Функции для работы с cookies модальным окном

// Закрытие модального окна
function closeCookieModal() {
    const modal = document.getElementById('cookieModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active', 'closing');
            document.body.classList.remove('cookie-modal-open');
        }, 300);
    }
}

// Открытие модального окна (если нужно программно)
function openCookieModal() {
    const modal = document.getElementById('cookieModal');
    if (modal) {
        modal.classList.add('active');
        document.body.classList.add('cookie-modal-open');
    }
}

// Принять все cookies
async function acceptAllCookies() {
    try {
        const response = await fetch('/api/accept_cookies', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        if (data.status === 'accepted') {
            showSuccessMessage('Все cookies приняты');
            closeCookieModal();
        } else {
            showErrorMessage('Не удалось сохранить настройки');
        }
    } catch (error) {
        console.error('Ошибка при принятии cookies:', error);
        showErrorMessage('Произошла ошибка. Пожалуйста, попробуйте еще раз.');
    }
}

// Принять выбранные cookies
async function acceptSelectedCookies() {
    const functionalToggle = document.getElementById('functionalToggle');
    const sessionToggle = document.getElementById('sessionToggle');
    
    // Получаем состояние toggle'ов
    const functionalEnabled = functionalToggle ? functionalToggle.checked : false;
    const sessionEnabled = sessionToggle ? sessionToggle.checked : false;
    
    // Проверяем, что хотя бы один выбран (кроме обязательных)
    if (functionalEnabled || sessionEnabled) {
        try {
            const response = await fetch('/api/accept_selected_cookies', {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    functional: functionalEnabled,
                    session: sessionEnabled
                })
            });
            
            const data = await response.json();
            if (data.status === 'accepted') {
                showSuccessMessage('Выбранные cookies приняты');
                closeCookieModal();
            } else {
                showErrorMessage('Не удалось сохранить настройки');
            }
        } catch (error) {
            console.error('Ошибка при принятии cookies:', error);
            showErrorMessage('Произошла ошибка. Пожалуйста, попробуйте еще раз.');
        }
    } else {
        // Если ничего не выбрано, предлагаем отклонить все
        if (confirm('Вы не выбрали ни одного типа cookies. Отклонить все cookies?')) {
            rejectAllCookies();
        }
    }
}

// Отклонить все cookies
async function rejectAllCookies() {
    try {
        const response = await fetch('/api/reject_cookies', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
            }
        });
        
        const data = await response.json();
        if (data.status === 'rejected') {
            showInfoMessage('Все cookies (кроме обязательных) отклонены');
            closeCookieModal();
            
            // Если пользователь на странице входа, показываем сообщение
            const loginForm = document.getElementById('loginForm');
            if (loginForm) {
                setTimeout(() => {
                    alert('Для входа в систему необходимо разрешить сессионные cookies');
                }, 500);
            }
        } else {
            showErrorMessage('Не удалось сохранить настройки');
        }
    } catch (error) {
        console.error('Ошибка при отклонении cookies:', error);
        showErrorMessage('Произошла ошибка. Пожалуйста, попробуйте еще раз.');
    }
}

// Проверить статус cookies
async function checkCookieStatus() {
    try {
        const response = await fetch('/api/cookie_status');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Ошибка проверки статуса cookies:', error);
        return null;
    }
}

// Вспомогательные функции для уведомлений
function showSuccessMessage(message) {
    showNotification(message, 'success');
}

function showErrorMessage(message) {
    showNotification(message, 'error');
}

function showInfoMessage(message) {
    showNotification(message, 'info');
}

function showNotification(message, type) {
    // Создаем временное уведомление
    const notification = document.createElement('div');
    notification.className = `cookie-notification cookie-notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            ${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Анимация появления
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // Автоматическое скрытие через 3 секунды
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Инициализация обработчиков событий для модального окна
function initCookieModal() {
    const modal = document.getElementById('cookieModal');
    
    if (!modal) return;
    
    const backdrop = modal.querySelector('.cookie-modal-backdrop');
    
    // Закрытие по клику на backdrop
    if (backdrop) {
        backdrop.addEventListener('click', closeCookieModal);
    }
    
    // Закрытие по Escape
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && modal && modal.classList.contains('active')) {
            closeCookieModal();
        }
    });
    
    // Предотвращаем закрытие при клике внутри контента
    const dialog = modal.querySelector('.cookie-modal-dialog');
    if (dialog) {
        dialog.addEventListener('click', function(event) {
            event.stopPropagation();
        });
    }
    
    // Блокируем скролл страницы при открытом модальном окне
    if (modal.classList.contains('active')) {
        document.body.classList.add('cookie-modal-open');
    }
    
    // Проверяем статус cookies при загрузке
    setTimeout(async () => {
        const status = await checkCookieStatus();
        if (status && status.cookies_accepted) {
            // Если cookies уже приняты, скрываем баннер
            modal.classList.remove('active');
            document.body.classList.remove('cookie-modal-open');
            
            // Обновляем состояние toggle'ов
            const functionalToggle = document.getElementById('functionalToggle');
            const sessionToggle = document.getElementById('sessionToggle');
            
            if (functionalToggle) {
                functionalToggle.checked = status.functional;
                functionalToggle.disabled = status.all_accepted;
            }
            
            if (sessionToggle) {
                sessionToggle.checked = status.session;
                sessionToggle.disabled = status.all_accepted;
            }
        }
    }, 100);
    
    // Экспортируем функции в глобальную область видимости
    window.closeCookieModal = closeCookieModal;
    window.openCookieModal = openCookieModal;
    window.acceptAllCookies = acceptAllCookies;
    window.acceptSelectedCookies = acceptSelectedCookies;
    window.rejectAllCookies = rejectAllCookies;
    window.checkCookieStatus = checkCookieStatus;
}

// Инициализируем при загрузке DOM
document.addEventListener('DOMContentLoaded', initCookieModal);