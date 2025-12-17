// static/js/auth.js

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', handleLoginSubmit);
        
        // Очистка ошибок при вводе
        const emailInput = document.getElementById('email');
        const passwordInput = document.getElementById('password');
        
        if (emailInput) {
            emailInput.addEventListener('input', clearEmailError);
        }
        
        if (passwordInput) {
            passwordInput.addEventListener('input', clearPasswordError);
        }
        
        // Проверяем статус cookies при загрузке
        checkCookieStatusAndWarn();
    }
});

async function checkCookieStatusAndWarn() {
    try {
        const response = await fetch('/api/cookie_status');
        const data = await response.json();
        
        if (!data.cookies_accepted || !data.session) {
            // Если cookies не приняты или сессионные cookies отключены
            const loginBtn = document.querySelector('.login-btn');
            if (loginBtn) {
                loginBtn.disabled = true;
                loginBtn.title = 'Для входа необходимо разрешить сессионные cookies';
                loginBtn.style.opacity = '0.7';
                loginBtn.style.cursor = 'not-allowed';
                
                // Добавляем предупреждение
                const warning = document.createElement('div');
                warning.className = 'cookie-warning';
                warning.innerHTML = `
                    <div class="warning-icon">⚠️</div>
                    <div class="warning-text">
                        Для входа в систему необходимо разрешить сессионные cookies.
                        <a href="javascript:void(0)" onclick="openCookieModal()" class="warning-link">
                            Настроить cookies
                        </a>
                    </div>
                `;
                
                const form = document.querySelector('.login-form');
                if (form) {
                    form.insertBefore(warning, form.querySelector('.form-options'));
                }
            }
        }
    } catch (error) {
        console.error('Ошибка проверки статуса cookies:', error);
    }
}

async function handleLoginSubmit(e) {
    e.preventDefault();
    
    // Сначала проверяем статус cookies
    try {
        const response = await fetch('/api/cookie_status');
        const data = await response.json();
        
        if (!data.cookies_accepted || !data.session) {
            alert('Для входа в систему необходимо разрешить сессионные cookies. Пожалуйста, настройте cookies в модальном окне.');
            openCookieModal();
            return;
        }
    } catch (error) {
        console.error('Ошибка проверки статуса cookies:', error);
        alert('Не удалось проверить настройки cookies. Пожалуйста, попробуйте еще раз.');
        return;
    }
    
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const remember = document.getElementById('remember').checked ? 'on' : 'off';
    const emailError = document.getElementById('emailError');
    const passwordError = document.getElementById('passwordError');
    
    // Сброс ошибок (только клиентских)
    emailError.textContent = '';
    emailError.style.display = 'none';
    passwordError.textContent = '';
    passwordError.style.display = 'none';
    
    let isValid = true;
    
    // Клиентская валидация
    if (!email) {
        emailError.textContent = 'Email обязателен для заполнения';
        emailError.style.display = 'block';
        isValid = false;
    } else if (!/\S+@\S+\.\S+/.test(email)) {
        emailError.textContent = 'Введите корректный email';
        emailError.style.display = 'block';
        isValid = false;
    }
    
    if (!password) {
        passwordError.textContent = 'Пароль обязателен для заполнения';
        passwordError.style.display = 'block';
        isValid = false;
    } else if (password.length < 6) {
        passwordError.textContent = 'Пароль должен содержать минимум 6 символов';
        passwordError.style.display = 'block';
        isValid = false;
    }
    
    if (isValid) {
        const loginBtn = document.querySelector('.login-btn');
        loginBtn.textContent = 'Вход...';
        loginBtn.disabled = true;
        
        try {
            const formData = new FormData();
            formData.append('email', email);
            formData.append('password', password);
            formData.append('remember', remember);
            
            const response = await fetch('/login', {
                method: 'POST',
                body: formData,
            });
            
            if (response.redirected) {
                // Успешный вход
                window.location.href = response.url;
            } else {
                // Ошибка - загружаем новую страницу с ошибками
                const html = await response.text();
                
                // Создаем временный div для парсинга
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;
                
                // Находим форму на новой странице
                const newForm = tempDiv.querySelector('.login-form');
                if (newForm) {
                    // Заменяем нашу форму новой формой с ошибками
                    const currentForm = document.querySelector('.login-form');
                    currentForm.innerHTML = newForm.innerHTML;
                    
                    // Перепривязываем обработчики событий
                    document.getElementById('loginForm').addEventListener('submit', handleLoginSubmit);
                    
                    // Также перепривязываем обработчики для очистки ошибок
                    const newEmailInput = document.getElementById('email');
                    const newPasswordInput = document.getElementById('password');
                    
                    if (newEmailInput) {
                        newEmailInput.addEventListener('input', clearEmailError);
                    }
                    
                    if (newPasswordInput) {
                        newPasswordInput.addEventListener('input', clearPasswordError);
                    }
                    
                    // Проверяем статус cookies снова
                    checkCookieStatusAndWarn();
                }
                
                loginBtn.textContent = 'Войти';
                loginBtn.disabled = false;
            }
        } catch (error) {
            console.error('Ошибка:', error);
            alert('Ошибка соединения с сервером');
            loginBtn.textContent = 'Войти';
            loginBtn.disabled = false;
        }
    }
}

function clearEmailError() {
    const emailError = document.getElementById('emailError');
    emailError.textContent = '';
    emailError.style.display = 'none';
}

function clearPasswordError() {
    const passwordError = document.getElementById('passwordError');
    passwordError.textContent = '';
    passwordError.style.display = 'none';
}

// Экспортируем функцию для открытия модального окна
window.openCookieModal = function() {
    const modal = document.getElementById('cookieModal');
    if (modal) {
        modal.classList.add('active');
        document.body.classList.add('cookie-modal-open');
    }
};