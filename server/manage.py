"""Управление менеджерами админки.

  python manage.py add-user ЛОГИН "Имя Фамилия"     — добавить (пароль спросит)
  python manage.py set-password ЛОГИН               — сменить пароль
  python manage.py list-users                       — список
  python manage.py remove-user ЛОГИН                — удалить
"""
import sys, getpass, sqlite3
from werkzeug.security import generate_password_hash
import app as service

def conn(): return sqlite3.connect(service.DB_PATH)

def ask_password():
    p1 = getpass.getpass("Пароль (от 8 символов): ")
    if len(p1) < 8: sys.exit("Пароль короче 8 символов.")
    if getpass.getpass("Повторите пароль: ") != p1: sys.exit("Пароли не совпадают.")
    return p1

def main(a):
    if len(a) >= 3 and a[0] == "add-user":
        c = conn()
        try:
            c.execute("INSERT INTO users(login,name,pw_hash) VALUES(?,?,?)", (a[1], a[2], generate_password_hash(ask_password())))
            c.commit(); print("Готово: добавлен", a[1])
        except sqlite3.IntegrityError:
            sys.exit("Такой логин уже есть.")
    elif len(a) == 2 and a[0] == "set-password":
        c = conn(); n = c.execute("UPDATE users SET pw_hash=? WHERE login=?", (generate_password_hash(ask_password()), a[1])).rowcount
        c.commit(); print("Готово." if n else "Логин не найден.")
    elif a[:1] == ["list-users"]:
        for r in conn().execute("SELECT login, name FROM users ORDER BY id"): print(f"{r[0]:20} {r[1]}")
    elif len(a) == 2 and a[0] == "remove-user":
        c = conn(); n = c.execute("DELETE FROM users WHERE login=?", (a[1],)).rowcount; c.commit()
        print("Удалён." if n else "Логин не найден.")
    else:
        print(__doc__)

if __name__ == "__main__":
    main(sys.argv[1:])
