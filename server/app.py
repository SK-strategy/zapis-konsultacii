"""
Сервис записи на консультации.

Публичная часть:  /          — страница записи для клиентов (ссылка из бота)
                  /ics/<id>  — файл события для календаря телефона
Админка:          /admin     — расписание и мини-CRM, вход по логину и паролю

Хранилище — SQLite-файл в папке DATA_DIR (по умолчанию ./data).
Настройки — переменные окружения, см. README.md.
"""
import os, re, sqlite3, secrets, time, datetime as dt
from functools import wraps
from urllib.parse import quote
from flask import Flask, g, request, jsonify, session, redirect, send_from_directory, Response, abort
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- настройки ----------
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "zapis.sqlite3")
HOURS = [int(h) for h in os.environ.get("HOURS", "6,7,8,9,10,11,12").split(",")]  # начало консультаций, МСК
WORKDAYS = [int(d) for d in os.environ.get("WORKDAYS", "0,1,2,3,4").split(",")]  # 0=пн … 6=вс
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "14"))
LEAD_MINUTES = int(os.environ.get("LEAD_MINUTES", "60"))
SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "60"))
EVENT_TITLE = os.environ.get("EVENT_TITLE", "Консультация")
MSK = dt.timezone(dt.timedelta(hours=3), "MSK")
STATUSES = {"booked": "Записан", "came": "Пришёл", "noshow": "Не пришёл", "bought": "Купил", "cancelled": "Отменён"}

app = Flask(__name__, static_folder=None)

def _secret():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    p = os.path.join(DATA_DIR, ".secret_key")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
    return open(p).read().strip()

app.config.update(
    SECRET_KEY=_secret(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    PERMANENT_SESSION_LIFETIME=dt.timedelta(days=14),
)
STATIC = os.path.join(os.path.dirname(__file__), "static")

# ---------- база ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS clients(
  id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL, name TEXT NOT NULL, telegram TEXT DEFAULT '',
  status TEXT DEFAULT 'booked', notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY, slot TEXT NOT NULL, date TEXT NOT NULL, hour INTEGER NOT NULL,
  client_id INTEGER NOT NULL REFERENCES clients(id), note TEXT DEFAULT '', source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'booked', token TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id));
CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_per_slot ON bookings(slot) WHERE status != 'cancelled';
CREATE INDEX IF NOT EXISTS bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS bookings_client ON bookings(client_id);
CREATE TABLE IF NOT EXISTS blocked(
  slot TEXT PRIMARY KEY, date TEXT NOT NULL, hour INTEGER NOT NULL, reason TEXT DEFAULT '', by INTEGER);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def _close(_):
    c = g.pop("db", None)
    if c: c.close()

def init_db():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    # первичные пользователи из окружения: ADMIN_USERS="login:пароль:Имя;login2:пароль2:Имя2"
    for item in filter(None, os.environ.get("ADMIN_USERS", "").split(";")):
        parts = item.split(":", 2)
        if len(parts) == 3 and not c.execute("SELECT 1 FROM users WHERE login=?", (parts[0],)).fetchone():
            c.execute("INSERT INTO users(login,name,pw_hash) VALUES(?,?,?)",
                      (parts[0].strip(), parts[2].strip(), generate_password_hash(parts[1])))
    c.commit(); c.close()

init_db()

# ---------- время и слоты ----------
def now_utc(): return dt.datetime.now(dt.timezone.utc)
def iso_now(): return now_utc().isoformat(timespec="seconds")
def slot_id(date, hour): return f"{date}_{hour:02d}"
def slot_start(date, hour):
    y, m, d = map(int, date.split("-"))
    return dt.datetime(y, m, d, hour, tzinfo=MSK)
def today_msk(): return now_utc().astimezone(MSK).date()

def slot_problem(date, hour, for_client=True):
    """Почему на этот слот нельзя записаться (None — можно)."""
    try:
        day = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return "Неверная дата."
    if hour not in HOURS or day.weekday() not in WORKDAYS:
        return "В это время консультаций нет."
    if for_client:
        if (day - today_msk()).days >= DAYS_AHEAD:
            return "Запись на эту дату ещё не открыта."
        if slot_start(date, hour) - now_utc() < dt.timedelta(minutes=LEAD_MINUTES):
            return "Это время уже прошло или до него меньше часа."
    if db().execute("SELECT 1 FROM blocked WHERE slot=?", (slot_id(date, hour),)).fetchone():
        return "Это время закрыто."
    return None

# ---------- клиенты ----------
def norm_phone(raw):
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] == "8": d = "7" + d[1:]
    if len(d) == 10: d = "7" + d
    if not (10 <= len(d) <= 15): return None
    return "+" + d

def norm_tg(raw):
    raw = (raw or "").strip()
    raw = re.sub(r"^(https?://)?t\.me/", "", raw)
    if raw and not raw.startswith("@") and re.fullmatch(r"[A-Za-z0-9_]{4,32}", raw): raw = "@" + raw
    return raw[:64]

def upsert_client(name, phone, telegram):
    c = db()
    row = c.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
    t = iso_now()
    if row:
        c.execute("UPDATE clients SET name=?, telegram=COALESCE(NULLIF(?,''),telegram), updated_at=? WHERE id=?",
                  (name, telegram, t, row["id"]))
        return row["id"]
    return c.execute("INSERT INTO clients(phone,name,telegram,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (phone, name, telegram, "booked", t, t)).lastrowid

def create_booking(date, hour, name, phone, telegram, note, source, user_id=None):
    c = db()
    try:
        c.execute("BEGIN IMMEDIATE")
        cid = upsert_client(name, phone, telegram)
        token = secrets.token_urlsafe(12)
        c.execute("INSERT INTO bookings(slot,date,hour,client_id,note,source,status,token,created_at,created_by)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (slot_id(date, hour), date, hour, cid, note, source, "booked", token, iso_now(), user_id))
        c.execute("UPDATE clients SET status='booked', updated_at=? WHERE id=?", (iso_now(), cid))
        c.commit()
        return token
    except sqlite3.IntegrityError:
        c.rollback()
        return None

# ---------- защита ----------
_hits = {}
def rate_limited(key, limit, per_seconds):
    t = time.time()
    arr = [x for x in _hits.get(key, []) if t - x < per_seconds]
    arr.append(t); _hits[key] = arr
    return len(arr) > limit

def client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0]).strip()

def same_origin():
    origin = request.headers.get("Origin")
    return not origin or origin.split("://", 1)[-1] == request.host

def login_required(api=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("uid"):
                return (jsonify(error="Войдите в админку заново."), 401) if api else redirect("/admin/login")
            if api and request.method != "GET" and (request.headers.get("X-Requested-With") != "fetch" or not same_origin()):
                return jsonify(error="Запрос отклонён."), 403
            return fn(*a, **kw)
        return wrapper
    return deco

@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/admin") or request.path.startswith("/api/admin"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Frame-Options"] = "DENY"
    return resp

def body():
    return request.get_json(silent=True) or {}

# ---------- публичная часть ----------
@app.get("/")
def page_book(): return send_from_directory(STATIC, "book.html")

@app.get("/privacy")
def page_privacy(): return send_from_directory(STATIC, "privacy.html")

@app.get("/static/<path:name>")
def static_files(name): return send_from_directory(STATIC, name)

@app.get("/api/slots")
def api_slots():
    c = db()
    start = today_msk()
    end = start + dt.timedelta(days=DAYS_AHEAD)
    busy = {r["slot"] for r in c.execute(
        "SELECT slot FROM bookings WHERE status!='cancelled' AND date>=? AND date<?", (start.isoformat(), end.isoformat()))}
    busy |= {r["slot"] for r in c.execute("SELECT slot FROM blocked WHERE date>=? AND date<?", (start.isoformat(), end.isoformat()))}
    days, lead = [], now_utc() + dt.timedelta(minutes=LEAD_MINUTES)
    for i in range(DAYS_AHEAD):
        day = start + dt.timedelta(days=i)
        if day.weekday() not in WORKDAYS: continue
        ds = day.isoformat()
        days.append({"date": ds, "slots": [{"hour": h, "start": slot_start(ds, h).isoformat(),
                     "free": slot_id(ds, h) not in busy and slot_start(ds, h) > lead} for h in HOURS]})
    return jsonify(days=days, slot_minutes=SLOT_MINUTES)

@app.post("/api/book")
def api_book():
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("book:" + client_ip(), 8, 3600):
        return jsonify(error="Слишком много попыток. Попробуйте через час или напишите менеджеру."), 429
    b = body()
    name = (b.get("name") or "").strip()[:80]
    phone = norm_phone(b.get("phone"))
    tg = norm_tg(b.get("telegram"))
    note = (b.get("note") or "").strip()[:500]
    date, hour = b.get("date"), b.get("hour")
    if b.get("website"):  # ловушка для ботов: поле скрыто от людей
        return jsonify(error="Запрос отклонён."), 400
    if not name: return jsonify(error="Укажите, как к вам обращаться."), 400
    if not phone: return jsonify(error="Проверьте номер телефона: нужен номер с кодом страны или из 10–11 цифр."), 400
    if not b.get("consent"): return jsonify(error="Отметьте согласие на обработку данных — без него записать не получится."), 400
    if not isinstance(hour, int): return jsonify(error="Выберите время."), 400
    problem = slot_problem(date, hour)
    if problem: return jsonify(error=problem), 409
    token = create_booking(date, hour, name, phone, tg, note, "bot")
    if not token: return jsonify(error="Это время только что заняли. Выберите другое."), 409
    return jsonify(ok=True, **event_payload(date, hour, token))

def event_payload(date, hour, token):
    start = slot_start(date, hour)
    end = start + dt.timedelta(minutes=SLOT_MINUTES)
    f = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gcal = ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(EVENT_TITLE)}&dates={f(start)}/{f(end)}"
            f"&details={quote('Время по Москве: ' + start.strftime('%d.%m %H:%M'))}")
    return {"date": date, "hour": hour, "start": start.isoformat(), "ics": f"/ics/{token}.ics", "gcal": gcal}

@app.get("/ics/<token>.ics")
def ics(token):
    r = db().execute("SELECT b.*, c.name FROM bookings b JOIN clients c ON c.id=b.client_id WHERE token=?", (token,)).fetchone()
    if not r or r["status"] == "cancelled": abort(404)
    start = slot_start(r["date"], r["hour"])
    end = start + dt.timedelta(minutes=SLOT_MINUTES)
    f = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//zapis-konsultacii//RU", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "BEGIN:VEVENT", f"UID:{token}@zapis-konsultacii", f"DTSTAMP:{f(now_utc())}",
             f"DTSTART:{f(start)}", f"DTEND:{f(end)}", f"SUMMARY:{esc(EVENT_TITLE)}",
             f"DESCRIPTION:{esc('Время по Москве: ' + start.strftime('%d.%m.%Y %H:%M'))}",
             "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", f"DESCRIPTION:{esc(EVENT_TITLE + ' через час')}", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return Response("\r\n".join(lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": 'inline; filename="konsultaciya.ics"'})

# ---------- вход в админку ----------
@app.get("/admin/login")
def page_login():
    if session.get("uid"): return redirect("/admin")
    return send_from_directory(STATIC, "login.html")

@app.post("/admin/login")
def do_login():
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("login:" + client_ip(), 10, 900):
        return jsonify(error="Слишком много попыток входа. Подождите 15 минут."), 429
    b = body()
    u = db().execute("SELECT * FROM users WHERE login=?", ((b.get("login") or "").strip(),)).fetchone()
    if not u or not check_password_hash(u["pw_hash"], b.get("password") or ""):
        return jsonify(error="Неверный логин или пароль."), 401
    session.clear(); session.permanent = True
    session["uid"] = u["id"]; session["name"] = u["name"]
    return jsonify(ok=True)

@app.post("/admin/logout")
def do_logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/admin")
@login_required()
def page_admin(): return send_from_directory(STATIC, "admin.html")

# ---------- API админки ----------
@app.get("/api/admin/me")
@login_required(api=True)
def me(): return jsonify(name=session.get("name"), hours=HOURS, workdays=WORKDAYS, statuses=STATUSES)

def booking_row(r):
    return {"id": r["id"], "slot": r["slot"], "date": r["date"], "hour": r["hour"], "status": r["status"],
            "source": r["source"], "note": r["note"], "created_at": r["created_at"], "created_by": r["created_by_name"],
            "client": {"id": r["client_id"], "name": r["name"], "phone": r["phone"], "telegram": r["telegram"]}}

BOOKING_SQL = ("SELECT b.*, c.name, c.phone, c.telegram, u.name AS created_by_name FROM bookings b "
               "JOIN clients c ON c.id=b.client_id LEFT JOIN users u ON u.id=b.created_by ")

@app.get("/api/admin/week")
@login_required(api=True)
def week():
    try:
        start = dt.date.fromisoformat(request.args.get("start", ""))
    except ValueError:
        return jsonify(error="Неверная дата."), 400
    end = (start + dt.timedelta(days=7)).isoformat()
    c = db()
    rows = c.execute(BOOKING_SQL + "WHERE b.status!='cancelled' AND b.date>=? AND b.date<?", (start.isoformat(), end)).fetchall()
    bl = c.execute("SELECT slot, reason FROM blocked WHERE date>=? AND date<?", (start.isoformat(), end)).fetchall()
    return jsonify(bookings=[booking_row(r) for r in rows], blocked={r["slot"]: r["reason"] for r in bl}, now=iso_now())

@app.post("/api/admin/bookings")
@login_required(api=True)
def admin_create():
    b = body()
    name = (b.get("name") or "").strip()[:80]
    phone = norm_phone(b.get("phone"))
    if not name: return jsonify(error="Укажите имя."), 400
    if not phone: return jsonify(error="Укажите телефон: он нужен, чтобы найти клиента в CRM."), 400
    date, hour = b.get("date"), b.get("hour")
    problem = slot_problem(date, hour if isinstance(hour, int) else -1, for_client=False)
    if problem: return jsonify(error=problem), 409
    token = create_booking(date, hour, name, phone, norm_tg(b.get("telegram")), (b.get("note") or "")[:500], "manager", session["uid"])
    if not token: return jsonify(error="Это время только что заняли."), 409
    return jsonify(ok=True, **event_payload(date, hour, token))

@app.patch("/api/admin/bookings/<int:bid>")
@login_required(api=True)
def admin_update(bid):
    st = body().get("status")
    if st not in STATUSES: return jsonify(error="Неизвестный статус."), 400
    c = db()
    r = c.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not r: return jsonify(error="Запись не найдена."), 404
    c.execute("UPDATE bookings SET status=? WHERE id=?", (st, bid))
    if st != "cancelled":
        c.execute("UPDATE clients SET status=?, updated_at=? WHERE id=?", (st, iso_now(), r["client_id"]))
    c.commit()
    return jsonify(ok=True)

@app.post("/api/admin/blocked")
@login_required(api=True)
def block():
    b = body()
    date, hour = b.get("date"), b.get("hour")
    if slot_problem(date, hour if isinstance(hour, int) else -1, for_client=False) == "Неверная дата.":
        return jsonify(error="Неверная дата."), 400
    c = db()
    if c.execute("SELECT 1 FROM bookings WHERE slot=? AND status!='cancelled'", (slot_id(date, hour),)).fetchone():
        return jsonify(error="На это время уже есть запись."), 409
    c.execute("INSERT OR REPLACE INTO blocked(slot,date,hour,reason,by) VALUES(?,?,?,?,?)",
              (slot_id(date, hour), date, hour, (b.get("reason") or "")[:120], session["uid"]))
    c.commit()
    return jsonify(ok=True)

@app.delete("/api/admin/blocked/<slot>")
@login_required(api=True)
def unblock(slot):
    db().execute("DELETE FROM blocked WHERE slot=?", (slot,)); db().commit()
    return jsonify(ok=True)

@app.get("/api/admin/clients")
@login_required(api=True)
def clients():
    q = (request.args.get("q") or "").strip().lower()
    st = request.args.get("status") or ""
    sql = ("SELECT c.*, COUNT(b.id) FILTER (WHERE b.status!='cancelled') AS visits, MAX(b.date || '_' || printf('%02d', b.hour)) "
           "FILTER (WHERE b.status!='cancelled') AS last_slot FROM clients c LEFT JOIN bookings b ON b.client_id=c.id ")
    where, args = [], []
    if q:
        digits = re.sub(r"\D", "", q)
        cond = ["lower(c.name) LIKE ?", "lower(c.telegram) LIKE ?", "lower(c.notes) LIKE ?"]
        args += [f"%{q}%"] * 3
        if digits: cond.append("c.phone LIKE ?"); args.append(f"%{digits}%")
        where.append("(" + " OR ".join(cond) + ")")
    if st in STATUSES: where.append("c.status=?"); args.append(st)
    if where: sql += "WHERE " + " AND ".join(where) + " "
    sql += "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT 500"
    rows = db().execute(sql, args).fetchall()
    return jsonify(clients=[{"id": r["id"], "name": r["name"], "phone": r["phone"], "telegram": r["telegram"],
                             "status": r["status"], "notes": r["notes"], "visits": r["visits"], "last_slot": r["last_slot"],
                             "created_at": r["created_at"]} for r in rows])

@app.get("/api/admin/clients/<int:cid>")
@login_required(api=True)
def client(cid):
    c = db()
    r = c.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if not r: return jsonify(error="Клиент не найден."), 404
    hist = c.execute(BOOKING_SQL + "WHERE b.client_id=? ORDER BY b.date DESC, b.hour DESC", (cid,)).fetchall()
    return jsonify(client=dict(r), bookings=[booking_row(h) for h in hist])

@app.patch("/api/admin/clients/<int:cid>")
@login_required(api=True)
def client_update(cid):
    b = body()
    c = db()
    if not c.execute("SELECT 1 FROM clients WHERE id=?", (cid,)).fetchone(): return jsonify(error="Клиент не найден."), 404
    fields, args = [], []
    if "name" in b and (b["name"] or "").strip(): fields.append("name=?"); args.append(b["name"].strip()[:80])
    if "telegram" in b: fields.append("telegram=?"); args.append(norm_tg(b["telegram"]))
    if "notes" in b: fields.append("notes=?"); args.append((b["notes"] or "")[:4000])
    if "status" in b:
        if b["status"] not in STATUSES or b["status"] == "cancelled": return jsonify(error="Неизвестный статус."), 400
        fields.append("status=?"); args.append(b["status"])
    if "phone" in b:
        p = norm_phone(b["phone"])
        if not p: return jsonify(error="Проверьте номер телефона."), 400
        fields.append("phone=?"); args.append(p)
    if not fields: return jsonify(ok=True)
    fields.append("updated_at=?"); args.append(iso_now())
    try:
        c.execute(f"UPDATE clients SET {', '.join(fields)} WHERE id=?", args + [cid]); c.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Клиент с таким телефоном уже есть."), 409
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
