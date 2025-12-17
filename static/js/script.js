// static/js/script.js

// Функция переключения меню
function toggleMenu() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    
    if (sidebar && mainContent) {
        sidebar.classList.toggle('open');
        mainContent.classList.toggle('sidebar-open');
    }
}

// Функция открытия/закрытия фильтра
function toggleFilter() {
    const filterContent = document.getElementById('filterContent');
    if (filterContent) {
        filterContent.classList.toggle('show');
    }
}

// Функция закрытия фильтра при клике вне области
function setupClickOutside() {
    document.addEventListener('click', function(event) {
        const filterButton = document.getElementById('filterButton');
        const filterContent = document.getElementById('filterContent');
        
        if (filterContent && filterButton) {
            if (!filterButton.contains(event.target) && !filterContent.contains(event.target)) {
                filterContent.classList.remove('show');
            }
        }
    });
}

// Функция закрытия фильтра при нажатии Escape
function setupEscapeKey() {
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            const filterContent = document.getElementById('filterContent');
            if (filterContent) {
                filterContent.classList.remove('show');
            }
        }
    });
}

// Функция закрытия меню при клике на пункт меню
function setupMenuItems() {
    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', function() {
            const sidebar = document.getElementById('sidebar');
            const mainContent = document.getElementById('mainContent');
            
            if (sidebar && mainContent) {
                sidebar.classList.remove('open');
                mainContent.classList.remove('sidebar-open');
            }
        });
    });
}

// Функция автофокуса на поле поиска
function setupAutoFocus() {
    const searchInput = document.querySelector('.search-input');
    if (searchInput && !searchInput.value) {
        searchInput.focus();
    }
}

// Функция для поиска без логина (показывает все)
function handleEmptySearch() {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.querySelector('input[name="login"]');
    
    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            // Если поле логина пустое, все равно отправляем форму
            // Сервер обработает пустой логин как "показать все"
            // Ничего не делаем - форма отправится как есть
        });
    }
}

// Функция для сброса фильтра (уже есть в HTML как ссылка)
// function clearFilter() {
//     window.location.href = window.location.pathname + '?login=' + encodeURIComponent("{{ login or '' }}");
// }

// Инициализация всех обработчиков событий
function initialize() {
    // Кнопка меню
    const menuToggle = document.getElementById('menuToggle');
    if (menuToggle) {
        menuToggle.addEventListener('click', toggleMenu);
    }
    
    // Кнопка фильтра
    const filterButton = document.getElementById('filterButton');
    if (filterButton) {
        filterButton.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleFilter();
        });
    }
    
    // Настройка остальных обработчиков
    setupClickOutside();
    setupEscapeKey();
    setupMenuItems();
    setupAutoFocus();
    handleEmptySearch();
    
    console.log('Скрипт инициализирован');
}

// Запуск инициализации после загрузки DOM
document.addEventListener('DOMContentLoaded', initialize);

// Экспорт функций для использования в консоли (опционально)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        toggleMenu,
        toggleFilter,
        initialize
    };
}