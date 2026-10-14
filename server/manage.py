"""Управление кабинетами (запускать на сервере из папки server).

  python manage.py list-users                                  — список кабинетов
  python manage.py add-user ЛОГИН "Имя" [manager|admin]          — добавить (пароль спросит)
  python manage.py set-password ЛОГИН                          — сменить пароль
  python manage.py hide ЛОГИН / show ЛОГИН                      — убрать менеджера из записи с сайта / вернуть
  python manage.py disable ЛОГИН                               — закрыть доступ (записи сохраняются)

Роли: manager — свой кабинет, к нему записываются клиенты с сайта;
      admin   — видит всех, своё расписание клиентам не показывается.
"""
import os, sys, getpass, sqlite3
from werkzeug.security import generate_password_hash
import app as service

def conn(): return sqlite3.connect(service.DB_PATH)

def ask_password():
    if os.environ.get("MANAGE_PASSWORD"):  # для скрипта установки
        return os.environ["MANAGE_PASSWORD"]
    p1 = getpass.getpass("Пароль (от 8 символов): ")
    if len(p1) < 8: sys.exit("Пароль короче 8 символов.")
    if getpass.getpass("Повторите пароль: ") != p1: sys.exit("Пароли не совпадают.")
    return p1

def main(a):
    c = conn()
    if a[:1] == ["list-users"]:
        for r in c.execute("SELECT login, name, role, public, active FROM users ORDER BY role='admin', id"):
            flags = ("" if r[4] else " [доступ закрыт]") + ("" if r[3] or r[2] == "admin" else " [скрыт с сайта]")
            print(f"{r[0]:16} {r[1]:20} {service.ROLES.get(r[2], r[2])}{flags}")
    elif len(a) >= 3 and a[0] in ("add-user", "ensure-user"):
        role = a[3] if len(a) > 3 and a[3] in service.ROLES else "manager"
        if c.execute("SELECT 1 FROM users WHERE login=?", (a[1],)).fetchone():
            if a[0] == "ensure-user": print("Уже есть:", a[1]); return
            sys.exit("Такой логин уже есть.")
        c.execute("INSERT INTO users(login,name,pw_hash,role,public) VALUES(?,?,?,?,?)",
                  (a[1], a[2], generate_password_hash(ask_password()), role, 1 if role == "manager" else 0))
        c.commit(); print(f"Готово: {a[2]} ({service.ROLES[role]}), логин {a[1]}")
    elif len(a) == 2 and a[0] == "set-password":
        n = c.execute("UPDATE users SET pw_hash=? WHERE login=?", (generate_password_hash(ask_password()), a[1])).rowcount
        c.commit(); print("Готово." if n else "Логин не найден.")
    elif len(a) == 2 and a[0] in ("hide", "show"):
        n = c.execute("UPDATE users SET public=? WHERE login=? AND role='manager'", (1 if a[0] == "show" else 0, a[1])).rowcount
        c.commit(); print("Готово." if n else "Менеджер не найден.")
    elif len(a) == 2 and a[0] == "disable":
        n = c.execute("UPDATE users SET active=0 WHERE login=?", (a[1],)).rowcount
        c.commit(); print("Доступ закрыт." if n else "Логин не найден.")
    else:
        print(__doc__)

if __name__ == "__main__":
    main(sys.argv[1:])
