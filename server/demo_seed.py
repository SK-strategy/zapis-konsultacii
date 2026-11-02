"""Вымышленные данные для демо полной версии (/full). Пересоздаются раз в сутки, со сдвигом дат к «сегодня».
Настоящих клиентов и паролей здесь нет."""
import json, random, secrets, sqlite3, datetime as dt
from werkzeug.security import generate_password_hash

NAMES = ["Ирина Соколова", "Андрей Власов", "Мария Ковалёва", "Сергей Орлов", "Елена Тихонова", "Дмитрий Назаров", "Ольга Бирюкова",
         "Алексей Зайцев", "Татьяна Громова", "Павел Фролов", "Наталья Мартынова", "Виктор Лебедев", "Юлия Крылова", "Игорь Субботин",
         "Анна Белова", "Максим Егоров", "Светлана Прохорова", "Роман Жуков", "Галина Воронцова", "Денис Колесников", "Инна Шестакова",
         "Олег Дорофеев", "Вера Никитина", "Артём Лаптев", "Людмила Сафонова", "Кирилл Мельников"]
CITIES = ["Москва", "Казань", "Новосибирск", "Екатеринбург", "Самара", "Краснодар", "Пермь", "Уфа", "Воронеж", "Тюмень"]
SRC = [("Нельзяграм (воронка)", "instagram", 30), ("Канал ТГ / MAX", "telegram", 20), ("Реклама", "yandex", 15), ("ВК", "vk", 12),
       ("Карты (Яндекс / 2ГИС)", "2gis", 8), ("YouTube", "youtube", 8), ("Сайт", "site", 7)]
DEBT = [("lt100", "долг < 100 тыс."), ("100_500", "долг 100–500 тыс."), ("gt500", "долг > 500 тыс.")]
PROP = [("home", "единственное жильё"), ("realty", "другая недвижимость"), ("car", "авто / ценное имущество"), ("none", "имущества нет")]
WORK = [("official", "официально"), ("informal", "неофициально"), ("ip", "ИП / самозанятость"), ("none", "не работает")]
HOURS = [6, 7, 8, 9, 10, 11, 12]
MSK = dt.timezone(dt.timedelta(hours=3))
EVENTS = ("open", "start", "q_debt", "q_property", "q_work", "offer", "branch_slot", "branch_request", "slot_pick", "booked", "requested")
TABLES = ("events", "day_notes", "blocked", "bookings", "clients", "users")

def _quiz(r):
    d, p, w = r.choice(DEBT), r.choice(PROP), r.choice(WORK)
    return json.dumps({"answers": {"debt": d[0], "property": [p[0]], "work": [w[0]]},
                       "summary": f"{d[1]} · {p[1]} · {w[1]}"}, ensure_ascii=False)

def seed(c, today):
    """Заполняет пустую базу. today — дата по Москве."""
    r = random.Random(today.toordinal())
    t0 = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pw = lambda: generate_password_hash(secrets.token_hex(16))   # входа по паролю нет: только через демо-кнопки
    users = {}
    for login, name, role, pub in (("admin", "Анастасия Губенко", "admin", 0), ("natalia", "Наталья", "manager", 1), ("roman", "Роман", "manager", 1)):
        users[login] = c.execute("INSERT INTO users(login,name,pw_hash,role,public,active) VALUES(?,?,?,?,?,1)", (login, name, pw(), role, pub)).lastrowid
    mgrs = [users["natalia"], users["roman"]]
    weights = [w for _, _, w in SRC]
    clients, n = [], 0
    def mk_client(status):
        nonlocal n
        name = NAMES[n % len(NAMES)]; n += 1
        phone = f"+7999{r.randint(1000000, 9999999)}"
        cid = c.execute("INSERT INTO clients(phone,name,city,status,quiz,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (phone, name, r.choice(CITIES), status, "", t0, t0)).lastrowid
        return cid, name
    def add_booking(day, hour, mgr, status="booked", attend="", confirm="", kind="slot", client_status="booked"):
        cid, _ = mk_client(client_status)
        src, utm_src, _ = r.choices(SRC, weights)[0]
        q = _quiz(r)
        c.execute("UPDATE clients SET quiz=? WHERE id=?", (q, cid))
        d = day.isoformat()
        created = (dt.datetime.combine(day, dt.time(10), MSK) - dt.timedelta(days=r.randint(0, 3))).astimezone(dt.timezone.utc).isoformat(timespec="seconds")
        c.execute("INSERT INTO bookings(kind,slot,date,hour,manager_id,client_id,status,origin,lead_source,service,utm,confirm,attend,city,tz,messenger,quiz,"
                  "consent_ver,consent_at,token,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (kind, f"{d}_{hour:02d}" if kind == "slot" else None, d if kind == "slot" else None, hour if kind == "slot" else None,
                   mgr if kind == "slot" else None, cid, status, "site", src, "БФЛ (банкротство физлиц)",
                   json.dumps({"utm_source": utm_src}), confirm, attend, "", "Europe/Moscow", r.choice(["telegram", "whatsapp", "max"]), q,
                   "2026-10-14", created, secrets.token_urlsafe(12), created, created))
        return cid
    # прошедшие встречи за 4 недели
    for back in range(28, 0, -1):
        day = today - dt.timedelta(days=back)
        if day.weekday() > 4: continue
        for hour in r.sample(HOURS, r.randint(2, 4)):
            mgr = r.choice(mgrs)
            o = r.random()
            if o < 0.12: att, cs = "noshow", "booked"
            elif o < 0.22: att, cs = "nc", "nc"
            elif o < 0.52: att, cs = "came", "bought"
            else: att, cs = "came", "came"
            cid = add_booking(day, hour, mgr, attend=att, confirm="yes" if att != "noshow" else "no", client_status=cs)
            if r.random() < 0.08:
                add_booking(day, hour, r.choice(mgrs), status="cancelled", client_status="cancelled")
    # ближайшие две недели
    for fwd in range(0, 14):
        day = today + dt.timedelta(days=fwd)
        if day.weekday() > 4: continue
        for hour in r.sample(HOURS, r.randint(1, 3) if fwd else 2):
            if fwd == 0 and hour < dt.datetime.now(MSK).hour + 2: continue
            mgr = r.choice(mgrs)
            try: add_booking(day, hour, mgr, confirm=r.choice(["", "yes", "yes"]))
            except sqlite3.IntegrityError: pass
    # заявки «подобрать время» ждут согласования
    for _ in range(3):
        add_booking(today, 0, None, status="pending", kind="request", client_status="request")
    # отпуск у Романа в выходной-ориентир: пара заблокированных часов
    d = today + dt.timedelta(days=3)
    for h in (11, 12):
        if d.weekday() <= 4:
            c.execute("INSERT OR IGNORE INTO blocked(slot,manager_id,date,hour,reason,by) VALUES(?,?,?,?,?,?)", (f"{d.isoformat()}_{h:02d}", users["roman"], d.isoformat(), h, "обед", users["roman"]))
    c.execute("INSERT OR REPLACE INTO day_notes(date,text,by,updated_at) VALUES(?,?,?,?)", ((today + dt.timedelta(days=1)).isoformat(), "Демо-заметка к дню: подготовить шаблон договора", users["admin"], t0))
    # воронка: посетители по ступеням
    for back in range(28):
        day = (today - dt.timedelta(days=back)).isoformat()
        for _ in range(r.randint(10, 24)):
            src = r.choices(SRC, weights)[0][0]
            sid = secrets.token_hex(8)
            path = ["open"]
            if r.random() < .75: path += ["start", "q_debt"]
            if len(path) == 3 and r.random() < .85: path += ["q_property", "q_work"]
            if len(path) == 5 and r.random() < .9: path += ["offer"]
            if len(path) == 6:
                if r.random() < .8: path += ["branch_slot"] + (["slot_pick"] if r.random() < .8 else [])
                else: path += ["branch_request"]
                if "slot_pick" in path and r.random() < .75: path += ["booked"]
                elif "branch_request" in path and r.random() < .7: path += ["requested"]
            for e in path:
                c.execute("INSERT OR IGNORE INTO events(sid,event,day,created_at,src) VALUES(?,?,?,?,?)", (sid, e, day, t0, src))

def ensure(db_path, today):
    """Раз в сутки (по Москве) стирает демо-базу и заполняет заново. Безопасно при нескольких воркерах."""
    c = sqlite3.connect(db_path, timeout=20, isolation_level=None)
    try:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta(k TEXT PRIMARY KEY, v TEXT)")
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT v FROM demo_meta WHERE k='seeded'").fetchone()
        if row and row[0] == today.isoformat():
            c.execute("ROLLBACK"); return False
        c.execute("PRAGMA foreign_keys=OFF")
        for t in TABLES: c.execute(f"DELETE FROM {t}")
        seed(c, today)
        c.execute("INSERT OR REPLACE INTO demo_meta VALUES('seeded',?)", (today.isoformat(),))
        c.execute("COMMIT")
        return True
    except Exception:
        try: c.execute("ROLLBACK")
        except sqlite3.Error: pass
        raise
    finally:
        c.close()
