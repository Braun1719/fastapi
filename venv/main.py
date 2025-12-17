from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from datetime import datetime, timedelta
import sqlite3
import secrets
import hashlib
import asyncio
from typing import Optional, Tuple, Dict, Any
import json
import logging
import uvicorn
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


DB_PATH = os.path.join("venv", "newdb")

def get_db():
    """Создаем новое соединение каждый раз"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_tables():
    """Создаем правильную таблицу"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Удаляем старую таблицу если есть
        cursor.execute("DROP TABLE IF EXISTS user_sessions")
        
        # Создаем правильную таблицу
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_login TEXT NOT NULL,
                email TEXT NOT NULL,
                access_token TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                remember_me BOOLEAN DEFAULT 0
            )
        """)
        
        # Создаем индекс для быстрого поиска по времени истечения
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at 
            ON user_sessions(expires_at)
        """)
        
        # Индекс для поиска по пользователю
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id 
            ON user_sessions(user_id)
        """)
        
        conn.commit()
        logger.info("Таблица сессий создана")
    except Exception as e:
        logger.error(f"Ошибка создания таблицы: {e}")
        conn.rollback()
    finally:
        conn.close()

# Инициализируем таблицы при старте
init_tables()

def hash_password(password: str) -> str:
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def can_set_session_cookies(request: Request) -> bool:
    """Проверяем, можно ли устанавливать сессионные куки"""
    cookies_accepted = request.cookies.get("cookies_accepted", "false")
    
    if cookies_accepted == "true":
        return True
    elif cookies_accepted.startswith("selected:"):
        # Разбираем выбранные типы cookies
        selected_types = cookies_accepted.split(":")[1].split(",")
        return "session" in selected_types
    return False

def create_session(user_id: int, user_login: str, email: str, request: Request, 
                  remember_me: bool = False, password: str = None) -> Tuple[Optional[str], Optional[str], int]:
    """
    Создание новой сессии
    Возвращает: (session_id, access_token, max_age)
    """
    # Проверяем, разрешены ли cookies сессии
    if not can_set_session_cookies(request):
        logger.warning(f"Попытка создания сессии при отключенных cookies для {email}")
        return None, None, 0
    
    session_id = secrets.token_urlsafe(32)
    access_token = secrets.token_urlsafe(48)
    
    # Согласованное время жизни сессии
    if remember_me:
        # Режим "Запомнить меня" - 7 дней
        session_duration = timedelta(days=7)
        max_age = 7 * 24 * 60 * 60  # 7 дней в секундах
    else:
        # Обычная сессия - 30 минут
        session_duration = timedelta(minutes=60)
        max_age = 30 * 60  # 30 минут в секундах
    
    expires_at = datetime.now() + session_duration
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")[:500]
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Сначала удаляем ВСЕ старые сессии этого пользователя
        cursor.execute(
            "DELETE FROM user_sessions WHERE user_id = ?",
            (user_id,)
        )
        
        # Создаем новую сессию
        cursor.execute(
            """INSERT INTO user_sessions 
               (session_id, user_id, user_login, email, access_token, expires_at, 
                ip_address, user_agent, remember_me) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, user_login, email, access_token, expires_at.isoformat(), 
             ip_address, user_agent, remember_me)
        )
        conn.commit()
        logger.info(f"Сессия создана для пользователя {user_login}, remember_me={remember_me}, expires_at={expires_at}")
    except Exception as e:
        logger.error(f"Ошибка создания сессии: {e}")
        conn.rollback()
        return None, None, 0
    finally:
        conn.close()
    
    return session_id, access_token, max_age

def cleanup_expired_sessions():
    """
    Немедленное удаление всех истекших сессий
    Вызывается при каждом входе и периодически
    """
    conn = get_db()
    cursor = conn.cursor()
    
    deleted_count = 0
    try:
        # Удаляем все сессии, у которых истек срок действия
        cursor.execute("""
            DELETE FROM user_sessions 
            WHERE expires_at < datetime('now')
        """)
        deleted_count = cursor.rowcount
        
        conn.commit()
        
        if deleted_count > 0:
            logger.info(f"Очистка сессий: удалено {deleted_count} истекших записей")
        
        # Логируем статистику
        cursor.execute("SELECT COUNT(*) as total FROM user_sessions")
        total_sessions = cursor.fetchone()["total"]
        
        cursor.execute("""
            SELECT COUNT(*) as expired_soon 
            FROM user_sessions 
            WHERE expires_at < datetime('now', '+1 hour')
        """)
        expiring_soon = cursor.fetchone()["expired_soon"]
        
        logger.info(f"Статистика сессий: всего={total_sessions}, скоро истекают={expiring_soon}")
        
    except Exception as e:
        logger.error(f"Ошибка при очистке сессий: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    return deleted_count

async def periodic_session_cleanup():
    """
    Фоновая задача для периодической очистки истекших сессий
    Запускается каждые 5 минут
    """
    while True:
        try:
            await asyncio.sleep(3600)  # 5 минут
            
            logger.info("Запуск периодической очистки истекших сессий...")
            deleted = cleanup_expired_sessions()
            
            if deleted > 0:
                logger.info(f"Периодическая очистка: удалено {deleted} истекших сессий")
                
        except Exception as e:
            logger.error(f"Ошибка в периодической очистке: {e}")
            await asyncio.sleep(60)  # Ждем минуту при ошибке

async def startup_cleanup():
    """Очистка при запуске приложения"""
    logger.info("Запуск очистки истекших сессий при старте...")
    deleted = cleanup_expired_sessions()
    if deleted > 0:
        logger.info(f"Очистка при старте: удалено {deleted} истекших сессий")

@app.on_event("startup")
async def startup_event():
    """Действия при запуске приложения"""
    logger.info("Запуск сервера...")
    
    # Очистка при старте
    await startup_cleanup()
    
    # Запускаем задачу очистки
    asyncio.create_task(periodic_session_cleanup())
    
    logger.info("Фоновая задача очистки сессий запущена")

def validate_session(session_id: str, access_token: str, prolong: bool = True) -> Dict[str, Any]:
    """
    Проверка валидности сессии с возможностью продления
    Возвращает словарь с результатом проверки и данными сессии
    """
    if not session_id or not access_token:
        return {"valid": False, "reason": "no_session"}
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Сначала проверяем, не истекла ли сессия
        cursor.execute(
            """SELECT user_id, user_login, email, expires_at, remember_me 
               FROM user_sessions 
               WHERE session_id = ? 
               AND access_token = ?""",
            (session_id, access_token)
        )
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Сессия {session_id} не найдена")
            return {"valid": False, "reason": "session_not_found"}
        
        expires_at_str = result["expires_at"]
        remember_me = result["remember_me"]
        
        # Проверяем не истекла ли сессия
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now() > expires_at:
            logger.info(f"Сессия {session_id} истекла в {expires_at}")
            
            # НЕМЕДЛЕННО удаляем истекшую сессию
            cursor.execute(
                "DELETE FROM user_sessions WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()
            
            # Возвращаем данные для автологина если remember_me был True
            if remember_me:
                return {
                    "valid": False,
                    "reason": "session_expired",
                    "email": result["email"],
                    "remember_me": True
                }
            
            return {"valid": False, "reason": "session_expired"}
        
        # Обновляем время последней активности
        cursor.execute(
            "UPDATE user_sessions SET last_activity = datetime('now') WHERE session_id = ?",
            (session_id,)
        )
        
        # Продлеваем сессию только если не выбрано "Запомнить меня"
        if prolong and not remember_me:
            # Продлеваем на 30 минут от текущего времени
            new_expires = datetime.now() + timedelta(minutes=30)
            cursor.execute(
                "UPDATE user_sessions SET expires_at = ? WHERE session_id = ?",
                (new_expires.isoformat(), session_id)
            )
            logger.debug(f"Сессия {session_id} продлена до {new_expires}")
        
        conn.commit()
        logger.debug(f"Сессия {session_id} валидна")
        
        return {
            "valid": True,
            "user_id": result["user_id"],
            "user_login": result["user_login"],
            "email": result["email"],
            "remember_me": remember_me,
            "expires_at": expires_at
        }
        
    except Exception as e:
        logger.error(f"Ошибка проверки сессии: {e}")
        return {"valid": False, "reason": "error"}
    finally:
        conn.close()

# ==================== СТРАНИЦА АУТЕНТИФИКАЦИИ ====================

@app.get("/", response_class=HTMLResponse)
def auth_page(
    request: Request, 
    error: str = None, 
    email_error: str = None,
    password_error: str = None,
    auto_email: str = None,
    auto_remember: bool = False
):
    # Всегда очищаем истекшие сессии при загрузке страницы входа
    cleanup_expired_sessions()
    
    cookies_accepted = request.cookies.get("cookies_accepted", "false")
    
    # Проверяем, не авторизован ли уже пользователь
    session_id = request.cookies.get("session_id")
    access_token = request.cookies.get("access_token")
    
    if session_id and access_token:
        session_status = validate_session(session_id, access_token, prolong=False)
        if session_status["valid"]:
            # Если уже авторизован - перенаправляем на главную
            return RedirectResponse(url="/main", status_code=302)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "email_error": email_error,
            "password_error": password_error,
            "email_value": auto_email or "",  # Подставляем email если есть
            "auto_remember": auto_remember,   # Ставим галочку "Запомнить меня"
            "show_cookie_banner": cookies_accepted == "false"  # Показываем если cookies не приняты
        }
    )

# ==================== ФУНКЦИЯ ВХОДА ====================

@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    remember: str = Form("off")
):
    # Очищаем истекшие сессии перед входом
    cleanup_expired_sessions()
    
    # Проверяем, приняты ли cookies
    cookies_accepted = request.cookies.get("cookies_accepted", "false")
    can_login = False
    
    if cookies_accepted == "true":
        can_login = True
    elif cookies_accepted.startswith("selected:"):
        selected_types = cookies_accepted.split(":")[1].split(",")
        if "session" in selected_types:
            can_login = True
        else:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "Для входа в систему необходимо разрешить сессионные cookies",
                    "email_value": email,
                    "auto_remember": remember == "on",
                    "show_cookie_banner": False
                }
            )
    else:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Для входа в систему необходимо принять условия использования cookies",
                "email_value": email,
                "auto_remember": remember == "on",
                "show_cookie_banner": True
            }
        )
    
    errors = {}
    
    if not email:
        errors["email_error"] = "Email обязателен для заполнения"
    elif "@" not in email:
        errors["email_error"] = "Введите корректный email"
    
    if not password:
        errors["password_error"] = "Пароль обязателен для заполнения"
    
    if errors:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                **errors,
                "email_value": email,
                "auto_remember": remember == "on",
                "show_cookie_banner": False
            }
        )
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Поиск пользователя
        cursor.execute("SELECT * FROM users_auth WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "email_error": "Пользователь с таким email не найден",
                    "email_value": email,
                    "auto_remember": remember == "on",
                    "show_cookie_banner": False
                }
            )
        
        # Проверка пароля
        hashed_password = hash_password(password)
        if user["password"] != hashed_password:
            conn.close()
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "password_error": "Неверный пароль",
                    "email_value": email,
                    "auto_remember": remember == "on",
                    "show_cookie_banner": False
                }
            )
        
        conn.close()
        
        # УСПЕШНАЯ АВТОРИЗАЦИЯ
        remember_me = remember == "on"
        
        # Создаем сессию (только если cookies разрешены)
        session_id, access_token, max_age = create_session(
            user["id"], 
            user["login"], 
            email,
            request, 
            remember_me,
            password if remember_me else None
        )
        
        if not session_id or not access_token:
            # Ошибка создания сессии или cookies не разрешены
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "error": "Не удалось создать сессию. Проверьте настройки cookies",
                    "email_value": email,
                    "auto_remember": remember_me,
                    "show_cookie_banner": False
                }
            )
        
        # Создаем ответ с куками сессии
        redirect_response = RedirectResponse(url="/main", status_code=302)
        
        # Устанавливаем сессионные куки (только если разрешено)
        redirect_response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=False
        )
        
        redirect_response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=False
        )
        
        redirect_response.set_cookie(
            key="user_login",
            value=user["login"],
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=False
        )
        
        # Также сохраняем email в cookie (для удобства)
        redirect_response.set_cookie(
            key="user_email",
            value=email,
            max_age=max_age if not remember_me else 30*24*60*60,
            httponly=False,
            samesite="lax",
            secure=False
        )
        
        # Для remember_me сохраняем специальный токен
        if remember_me:
            remember_token = secrets.token_urlsafe(32)
            redirect_response.set_cookie(
                key="remember_token",
                value=remember_token,
                max_age=30*24*60*60,  # 30 дней
                httponly=True,
                samesite="lax",
                secure=False
            )
        
        logger.info(f"Установлены куки сессии для {email}, remember_me={remember_me}")
        return redirect_response
        
    except Exception as e:
        logger.error(f"Ошибка входа: {e}")
        if 'conn' in locals():
            conn.close()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "error": "Ошибка сервера",
                "email_value": email,
                "auto_remember": remember == "on",
                "show_cookie_banner": False
            }
        )

# ==================== ЗАЩИЩЕННАЯ ГЛАВНАЯ СТРАНИЦА ====================

@app.get("/main", response_class=HTMLResponse)
def main_page(request: Request, login: str = "", machine_type: str = ""):
    # Очищаем истекшие сессии перед проверкой
    cleanup_expired_sessions()
    
    # ПРОВЕРКА СЕССИИ
    session_id = request.cookies.get("session_id")
    access_token = request.cookies.get("access_token")
    
    session_status = validate_session(session_id, access_token)
    
    if not session_status["valid"]:
        # Сессия невалидна
        if session_status["reason"] == "session_expired" and session_status.get("remember_me"):
            # Сессия истекла, но была remember_me
            email = session_status.get("email")
            response = RedirectResponse(
                url=f"/?auto_email={email}&auto_remember=true&error=Сессия+истекла.+Пожалуйста,+войдите+снова", 
                status_code=302
            )
            return response
        else:
            # Обычный сценарий - сессия истекла или не найдена
            response = RedirectResponse(
                url="/?error=Сессия+истекла.+Пожалуйста,+войдите+снова", 
                status_code=302
            )
            response.delete_cookie(key="session_id")
            response.delete_cookie(key="access_token")
            response.delete_cookie(key="user_login")
            response.delete_cookie(key="remember_token")
            return response
    
    # ПОЛЬЗОВАТЕЛЬ АВТОРИЗОВАН
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Получаем информацию о текущей сессии
        cursor.execute(
            "SELECT user_login, expires_at FROM user_sessions WHERE session_id = ?",
            (session_id,)
        )
        session_info = cursor.fetchone()
        
        if session_info:
            expires_at = datetime.fromisoformat(session_info["expires_at"])
            time_left = expires_at - datetime.now()
            logger.debug(f"Пользователь {session_info['user_login']}, время до истечения: {time_left}")
        
        # Получаем данные для таблицы
        query = "SELECT login, machine_name, machine_type FROM users WHERE 1=1"
        params = []
        
        if login:
            query += " AND login LIKE ?"
            params.append(f"%{login}%")
        
        if machine_type and machine_type != "all":
            query += " AND machine_type = ?"
            params.append(machine_type)
        
        cursor.execute(query, params)
        data = cursor.fetchall()
        
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        data = []
    finally:
        conn.close()

    # Получаем логин пользователя для отображения
    user_login = session_status.get("user_login", "Пользователь")
    
    return templates.TemplateResponse(
        "main.html",
        {
            "request": request,
            "data": data,
            "login": login,
            "machine_type": machine_type,
            "user_login": user_login  # Добавляем логин пользователя в контекст
        }
    )

# ==================== ВЫХОД ====================

@app.get("/logout")
def logout(request: Request):
    session_id = request.cookies.get("session_id")
    
    if session_id:
        conn = get_db()
        cursor = conn.cursor()
        try:
            # НЕМЕДЛЕННО удаляем сессию из БД
            cursor.execute(
                "DELETE FROM user_sessions WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()
            logger.info(f"Сессия {session_id} удалена")
        except Exception as e:
            logger.error(f"Ошибка удаления сессии: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    response = RedirectResponse(url="/")
    response.delete_cookie(key="session_id")
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="user_login")
    response.delete_cookie(key="user_email")
    response.delete_cookie(key="remember_token")
    
    return response

# ==================== API ДЛЯ COOKIES ====================

@app.post("/api/accept_cookies")
async def accept_cookies(request: Request, response: Response):
    """Принять все cookies"""
    resp = JSONResponse({"status": "accepted"})
    resp.set_cookie(
        key="cookies_accepted",
        value="true",  # Все cookies приняты
        max_age=365*24*60*60,
        httponly=True,
        samesite="lax",
        secure=False
    )
    return resp

@app.post("/api/accept_selected_cookies")
async def accept_selected_cookies(request: Request):
    """Принять выбранные cookies"""
    data = await request.json()
    functional = data.get("functional", False)
    session = data.get("session", False)
    
    selected_types = []
    if functional:
        selected_types.append("functional")
    if session:
        selected_types.append("session")
    
    if not selected_types:
        return JSONResponse({"status": "rejected", "message": "Не выбрано ни одного типа cookies"}, status_code=400)
    
    resp = JSONResponse({"status": "accepted", "selected": selected_types})
    resp.set_cookie(
        key="cookies_accepted",
        value=f"selected:{','.join(selected_types)}",
        max_age=365*24*60*60,
        httponly=True,
        samesite="lax",
        secure=False
    )
    return resp

@app.post("/api/reject_cookies")
async def reject_cookies():
    """Отклонить все cookies (кроме обязательных)"""
    resp = JSONResponse({"status": "rejected"})
    resp.set_cookie(
        key="cookies_accepted",
        value="false",
        max_age=30*24*60*60,
        httponly=True,
        samesite="lax",
        secure=False
    )
    return resp

@app.get("/api/cookie_status")
async def cookie_status(request: Request):
    cookies_accepted = request.cookies.get("cookies_accepted", "false")
    
    if cookies_accepted == "true":
        return {
            "cookies_accepted": True,
            "all_accepted": True,
            "functional": True,
            "session": True
        }
    elif cookies_accepted.startswith("selected:"):
        selected_types = cookies_accepted.split(":")[1].split(",")
        return {
            "cookies_accepted": True,
            "all_accepted": False,
            "functional": "functional" in selected_types,
            "session": "session" in selected_types
        }
    else:
        return {
            "cookies_accepted": False,
            "all_accepted": False,
            "functional": False,
            "session": False
        }

@app.post("/api/check_user")
async def check_user(request: Request):
    form_data = await request.form()
    email = form_data.get("email")
    
    if not email:
        return {"exists": False}
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM users_auth WHERE email = ?", (email,))
        user = cursor.fetchone()
        return {"exists": user is not None}
    except Exception:
        return {"exists": False}
    finally:
        conn.close()

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)