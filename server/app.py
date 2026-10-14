"""
Сервис записи на консультации «Gubenko Group» (версия 2).

Публичная часть:  /            — анкета и запись (ссылка из автоответа)
                  /?b=<токен>  — страница заявки клиента: время, менеджер, календарь, перенос, отмена
                  /ics/<токен> — файл события для календаря
Кабинеты:         /admin       — админ видит всех, менеджеры — своё расписание

Хранилище — SQLite в папке DATA_DIR. Настройки — переменные окружения (см. README.md).
"""
import os, re, json, random, sqlite3, secrets, time, datetime as dt
from functools import wraps
from urllib.parse import quote
from flask import Flask, g, request, jsonify, session, redirect, send_from_directory, Response, abort
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- настройки ----------
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "zapis.sqlite3")
HOURS = [int(h) for h in os.environ.get("HOURS", "6,7,8,9,10,11,12").split(",")]   # начало консультаций, МСК
WORKDAYS = [int(d) for d in os.environ.get("WORKDAYS", "0,1,2,3,4").split(",")]    # 0=пн … 6=вс
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "14"))
LEAD_MINUTES = int(os.environ.get("LEAD_MINUTES", "60"))
SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "60"))
MSK = dt.timezone(dt.timedelta(hours=3), "MSK")
with open(os.path.join(os.path.dirname(__file__), "funnel.json"), encoding="utf-8") as _f:
    FUNNEL = json.load(_f)
EVENT_TITLE = os.environ.get("EVENT_TITLE", "Консультация «%s»" % FUNNEL["brand"])
QUESTIONS = {q["id"]: q for q in FUNNEL["questions"]}
MESSENGERS = {m["id"]: m for m in FUNNEL["messengers"]}
SOURCES, SERVICES = FUNNEL["sources"], FUNNEL["services"]
SITE_SOURCE = SOURCES[0]
UTM_MAP = {k.lower(): v for k, v in FUNNEL.get("utm_sources", {}).items() if not k.startswith("_")}
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

def clean_utm(u):
    """UTM-метки из адреса, с которым человек пришёл (сохраняются в браузере до записи)."""
    if not isinstance(u, dict): return {}
    out = {}
    for k in UTM_KEYS:
        v = re.sub(r"[\x00-\x1f<>]", "", str(u.get(k) or "")).strip()[:100]
        if v: out[k] = v
    return out

def resolve_source(utm_source):
    """utm_source → источник: из таблицы соответствий, иначе сама метка (появится в аналитике отдельной строкой)."""
    v = (utm_source or "").strip()
    if not v: return SITE_SOURCE
    return UTM_MAP.get(v.lower()) or v[:40]

# события воронки (по одному на посетителя): порядок = шаги схемы
FUNNEL_EVENTS = ("open", "start", "q_debt", "q_property", "q_work", "offer", "branch_slot", "branch_request",
                 "slot_pick", "booked", "requested")
CLIENT_STATUSES = {"request": "Заявка", "booked": "Записан", "came": "Пришёл", "noshow": "Не пришёл",
                   "nc": "Нецелевой", "bought": "Купил", "cancelled": "Отменил"}
CONFIRM = {"": "—", "yes": "Да", "no": "Нет", "resched": "Перезапись"}
ATTEND = {"": "—", "came": "Пришёл", "noshow": "Не пришёл", "nc": "Пришёл, нецелевой"}
ROLES = {"admin": "Админ", "manager": "Менеджер"}

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False  # порядок вариантов (подтверждение, явка, статусы) как в коде

def _secret():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    p = os.path.join(DATA_DIR, ".secret_key")
    try:  # атомарно: при нескольких воркерах ключ создаёт только один
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(p) as f:
        return f.read().strip()

app.config.update(
    SECRET_KEY=_secret(), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    PERMANENT_SESSION_LIFETIME=dt.timedelta(days=14),
)
STATIC = os.path.join(os.path.dirname(__file__), "static")

# ---------- база ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'manager', public INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS clients(
  id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL, name TEXT NOT NULL, city TEXT DEFAULT '',
  status TEXT DEFAULT 'booked', notes TEXT DEFAULT '', quiz TEXT DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'slot',            -- slot | request
  slot TEXT, date TEXT, hour INTEGER, manager_id INTEGER REFERENCES users(id),
  client_id INTEGER NOT NULL REFERENCES clients(id),
  status TEXT NOT NULL DEFAULT 'booked',                                  -- booked | pending | cancelled
  origin TEXT NOT NULL DEFAULT 'site',                                    -- site | manager
  lead_source TEXT DEFAULT '', service TEXT DEFAULT '', utm TEXT DEFAULT '',
  confirm TEXT DEFAULT '', attend TEXT DEFAULT '', meeting_link TEXT DEFAULT '', note TEXT DEFAULT '',
  city TEXT DEFAULT '', tz TEXT DEFAULT '', messenger TEXT DEFAULT '', contact TEXT DEFAULT '',
  consent_ver TEXT DEFAULT '', consent_at TEXT DEFAULT '', quiz TEXT DEFAULT '',
  token TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id), updated_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS bookings_slot_manager ON bookings(slot, manager_id) WHERE status='booked';
CREATE INDEX IF NOT EXISTS bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS bookings_client ON bookings(client_id);
CREATE TABLE IF NOT EXISTS blocked(
  slot TEXT NOT NULL, manager_id INTEGER NOT NULL, date TEXT NOT NULL, hour INTEGER NOT NULL,
  reason TEXT DEFAULT '', by INTEGER, PRIMARY KEY(slot, manager_id));
CREATE TABLE IF NOT EXISTS day_notes(date TEXT PRIMARY KEY, text TEXT NOT NULL, by INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events(
  sid TEXT NOT NULL, event TEXT NOT NULL, day TEXT NOT NULL, created_at TEXT NOT NULL, src TEXT DEFAULT '', PRIMARY KEY(sid, event));
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

def parse_users(spec):
    """ADMIN_USERS="login:пароль:Имя:роль;…", роль admin|manager (по умолчанию manager).
    Менеджеры видны клиентам при записи; admin — нет (его расписание только для себя)."""
    out = []
    for item in filter(None, (spec or "").split(";")):
        p = [x.strip() for x in item.split(":")]
        if len(p) < 3 or not p[0] or not p[1]: continue
        role = p[3] if len(p) > 3 and p[3] in ROLES else "manager"
        out.append((p[0], p[1], p[2] or p[0], role))
    return out

def init_db():
    c = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in c.execute("PRAGMA table_info(bookings)")}
    if cols and "manager_id" not in cols:  # база первой версии: откладываем в сторону, данные тестовые
        for t in ("bookings", "clients", "blocked", "users", "events"):
            c.execute(f"ALTER TABLE {t} RENAME TO {t}_v1")
        for ix in ("bookings_one_per_slot", "bookings_date", "bookings_client"):
            c.execute(f"DROP INDEX IF EXISTS {ix}")
    c.executescript(SCHEMA)
    for t, col in (("bookings", "utm"), ("events", "src")):  # добавлено после запуска v2
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({t})")}:
            c.execute(f"ALTER TABLE {t} ADD COLUMN {col} TEXT DEFAULT ''")
    for login, pw, name, role in parse_users(os.environ.get("ADMIN_USERS", "")):
        if not c.execute("SELECT 1 FROM users WHERE login=?", (login,)).fetchone():
            c.execute("INSERT INTO users(login,name,pw_hash,role,public) VALUES(?,?,?,?,?)",
                      (login, name, generate_password_hash(pw), role, 1 if role == "manager" else 0))
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
    """Почему на это время нельзя записаться в принципе (None — можно)."""
    try:
        day = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return "Неверная дата."
    if not isinstance(hour, int) or hour not in HOURS or day.weekday() not in WORKDAYS:
        return "В это время консультаций нет."
    if for_client:
        if (day - today_msk()).days >= DAYS_AHEAD:
            return "Запись на эту дату ещё не открыта."
        if slot_start(date, hour) - now_utc() < dt.timedelta(minutes=LEAD_MINUTES):
            return "Это время уже прошло или до него меньше часа."
    return None

def public_managers(c):
    return [r["id"] for r in c.execute("SELECT id FROM users WHERE role='manager' AND public=1 AND active=1 ORDER BY id")]

def manager_busy(c, slot, manager_id, exclude_booking=None):
    if c.execute("SELECT 1 FROM blocked WHERE slot=? AND manager_id=?", (slot, manager_id)).fetchone(): return True
    return bool(c.execute("SELECT 1 FROM bookings WHERE slot=? AND manager_id=? AND status='booked' AND id IS NOT ?",
                          (slot, manager_id, exclude_booking)).fetchone())

def pick_manager(c, date, hour, exclude_booking=None, prefer=None):
    """Свободный менеджер на это время: сначала prefer, иначе тот, у кого в этот день меньше записей."""
    slot = slot_id(date, hour)
    free = [m for m in public_managers(c) if not manager_busy(c, slot, m, exclude_booking)]
    if not free: return None
    if prefer in free: return prefer
    load = {m: c.execute("SELECT COUNT(*) FROM bookings WHERE manager_id=? AND date=? AND status='booked'", (m, date)).fetchone()[0] for m in free}
    low = min(load.values())
    return random.choice([m for m in free if load[m] == low])

# ---------- проверка данных ----------
def norm_phone(raw):
    """Только российские мобильные: +7 9XX…, 8 9XX… или 9XX… (10 цифр). Возвращает +79XXXXXXXXX или None."""
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] in "78": d = d[1:]
    if len(d) != 10 or d[0] != "9": return None
    if len(set(d)) <= 2: return None
    return "+7" + d

PHONE_ERROR = "Проверьте номер: нужен российский мобильный, например +7 912 345-67-89."

def clean_quiz(raw):
    """Проверяет ответы анкеты (одиночный и множественный выбор, взаимоисключения). Возвращает словарь для CRM."""
    if not isinstance(raw, dict): return None
    a, parts = {}, []
    for qid, q in QUESTIONS.items():
        opts = {o["id"]: o for o in q["options"]}
        v = raw.get(qid)
        if q["type"] == "single":
            if v not in opts: return None
            a[qid] = v; parts.append(opts[v]["short"])
        else:
            if not isinstance(v, list) or not v or any(x not in opts for x in v): return None
            v = [o["id"] for o in q["options"] if o["id"] in v]  # порядок как в анкете, без повторов
            for x in v:
                if set(opts[x].get("excludes", [])) & set(v): return None
            a[qid] = v; parts.append(", ".join(opts[x]["short"] for x in v))
    return {"answers": a, "summary": " · ".join(parts)}

def clean_contact(b):
    """Мессенджер и контакт для связи. Для WhatsApp/MAX контакт — телефон, для Telegram — ник (если указан)."""
    m = b.get("messenger")
    if m not in MESSENGERS: return None, None, "Выберите мессенджер для связи."
    contact = ""
    if MESSENGERS[m]["contact"] == "telegram":
        nick = (b.get("contact") or "").strip().lstrip("@")
        nick = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", nick).strip("/")
        if nick and not re.fullmatch(r"[A-Za-z0-9_]{4,32}", nick):
            return None, None, "Ник в Telegram — латиница, цифры и _ (от 4 символов). Можно оставить пустым."
        contact = "@" + nick if nick else ""
    return m, contact, None

def contact_display(r):
    m = MESSENGERS.get(r["messenger"])
    if not m: return "", ""
    return m["label"], (r["contact"] or fmt_phone(r["phone"]))

def fmt_phone(p):
    d = re.sub(r"\D", "", p or "")
    return f"+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:]}" if len(d) == 11 else (p or "")

TZ_RE = re.compile(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}")

# ---------- клиенты и записи ----------
def upsert_client(c, name, phone, city="", status=None):
    row = c.execute("SELECT * FROM clients WHERE phone=?", (phone,)).fetchone()
    t = iso_now()
    if row:
        c.execute("UPDATE clients SET name=?, city=COALESCE(NULLIF(?,''),city), updated_at=? WHERE id=?", (name, city, t, row["id"]))
        if status: c.execute("UPDATE clients SET status=? WHERE id=?", (status, row["id"]))
        return row["id"]
    return c.execute("INSERT INTO clients(phone,name,city,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (phone, name, city, status or "booked", t, t)).lastrowid

def after_cancel(c, client_id):
    """Если у клиента не осталось активных записей и заявок — статус «Отменил» (кроме уже купивших и пришедших)."""
    left = c.execute("SELECT 1 FROM bookings WHERE client_id=? AND status IN ('booked','pending')", (client_id,)).fetchone()
    if not left:
        c.execute("UPDATE clients SET status='cancelled', updated_at=? WHERE id=? AND status IN ('booked','request')", (iso_now(), client_id))

def insert_booking(c, f):
    cols = list(f.keys())
    c.execute(f"INSERT INTO bookings({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [f[k] for k in cols])

def new_token(): return secrets.token_urlsafe(12)

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

def me():
    """Текущий пользователь кабинета (или None)."""
    uid = session.get("uid")
    if not uid: return None
    if "me" not in g:
        g.me = db().execute("SELECT id,login,name,role,public FROM users WHERE id=? AND active=1", (uid,)).fetchone()
    return g.me

def is_admin(): return bool(me()) and me()["role"] == "admin"

def login_required(api=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not me():
                session.clear()
                return (jsonify(error="Войдите в кабинет заново."), 401) if api else redirect("/admin/login")
            if api and request.method != "GET" and (request.headers.get("X-Requested-With") != "fetch" or not same_origin()):
                return jsonify(error="Запрос отклонён."), 403
            return fn(*a, **kw)
        return wrapper
    return deco

@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/admin") or request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    if request.path.startswith("/admin") or request.path.startswith("/api/admin"):
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

SHORT_LINKS = {k.lower(): v for k, v in FUNNEL.get("short_links", {}).items() if not k.startswith("_")}

@app.get("/<code>")
@app.get("/<code>/<campaign>")
def short_link(code, campaign=""):
    """Короткая ссылка на своём домене: /ig → /?utm_source=instagram, /ig/oktyabr → + utm_campaign=oktyabr."""
    src = SHORT_LINKS.get(code.lower())
    if not src: abort(404)
    q = "utm_source=" + quote(src) + "&utm_medium=short"
    camp = re.sub(r"[^\w-]", "", campaign)[:60]
    if camp: q += "&utm_campaign=" + quote(camp)
    return redirect("/?" + q, 302)

@app.get("/api/funnel")
def api_funnel():
    return jsonify(FUNNEL)

@app.post("/api/track")
def api_track():
    b = body()
    sid, ev = str(b.get("sid") or "")[:40], b.get("event")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", sid) or ev not in FUNNEL_EVENTS or rate_limited("track:" + client_ip(), 3000, 3600):
        return jsonify(ok=False), 400
    src = resolve_source(clean_utm(b.get("utm")).get("utm_source"))
    db().execute("INSERT OR IGNORE INTO events(sid,event,day,created_at,src) VALUES(?,?,?,?,?)", (sid, ev, today_msk().isoformat(), iso_now(), src))
    db().commit()
    return jsonify(ok=True)

@app.get("/api/slots")
def api_slots():
    """Свободные часы для клиентов: час свободен, если свободен хотя бы один менеджер."""
    c = db()
    mgrs = public_managers(c)
    start, end = today_msk(), today_msk() + dt.timedelta(days=DAYS_AHEAD)
    taken = {}
    for r in c.execute("SELECT slot, manager_id FROM bookings WHERE status='booked' AND date>=? AND date<? "
                       "UNION SELECT slot, manager_id FROM blocked WHERE date>=? AND date<?",
                       (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())):
        taken.setdefault(r["slot"], set()).add(r["manager_id"])
    days, lead = [], now_utc() + dt.timedelta(minutes=LEAD_MINUTES)
    for i in range(DAYS_AHEAD):
        day = start + dt.timedelta(days=i)
        if day.weekday() not in WORKDAYS: continue
        ds = day.isoformat()
        days.append({"date": ds, "slots": [{"hour": h, "start": slot_start(ds, h).isoformat(),
                     "free": bool(set(mgrs) - taken.get(slot_id(ds, h), set())) and slot_start(ds, h) > lead} for h in HOURS]})
    return jsonify(days=days, slot_minutes=SLOT_MINUTES)

def client_fields(b):
    """Общие поля формы записи и заявки. Возвращает (данные, ошибка)."""
    if b.get("website"): return None, "Запрос отклонён."
    name = (b.get("name") or "").strip()[:80]
    city = (b.get("city") or "").strip()[:80]
    phone = norm_phone(b.get("phone"))
    tz = (b.get("tz") or "").strip()[:40]
    if not name: return None, "Укажите, как к вам обращаться."
    if not city: return None, "Укажите ваш город."
    if not phone: return None, PHONE_ERROR
    m, contact, err = clean_contact(b)
    if err: return None, err
    if not b.get("consent"): return None, "Отметьте согласие на обработку персональных данных — без него записать не получится."
    quiz = clean_quiz(b.get("quiz")) if b.get("quiz") else None
    utm = clean_utm(b.get("utm"))
    return {"name": name, "city": city, "phone": phone, "tz": tz if TZ_RE.fullmatch(tz or "x") else "",
            "messenger": m, "contact": contact, "quiz": quiz,
            "lead_source": resolve_source(utm.get("utm_source")), "utm": json.dumps(utm, ensure_ascii=False) if utm else ""}, None

@app.post("/api/book")
def api_book():
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("book:" + client_ip(), 40, 3600):
        return jsonify(error="Слишком много попыток. Попробуйте через час или выберите «Подобрать время с менеджером»."), 429
    b = body()
    f, err = client_fields(b)
    if err: return jsonify(error=err), 400
    date, hour = b.get("date"), b.get("hour")
    problem = slot_problem(date, hour)
    if problem: return jsonify(error=problem), 409
    c = db()
    c.execute("BEGIN IMMEDIATE")
    try:
        mgr = pick_manager(c, date, hour)
        if not mgr:
            c.rollback()
            return jsonify(error="Это время только что заняли. Выберите другое — введённые данные сохранятся."), 409
        cid = upsert_client(c, f["name"], f["phone"], f["city"], "booked")
        q = json.dumps(f["quiz"], ensure_ascii=False) if f["quiz"] else ""
        if q: c.execute("UPDATE clients SET quiz=? WHERE id=?", (q, cid))
        token = new_token()
        insert_booking(c, {"kind": "slot", "slot": slot_id(date, hour), "date": date, "hour": hour, "manager_id": mgr,
                           "client_id": cid, "status": "booked", "origin": "site", "lead_source": f["lead_source"], "utm": f["utm"],
                           "city": f["city"], "tz": f["tz"], "messenger": f["messenger"], "contact": f["contact"],
                           "consent_ver": FUNNEL["consent_version"], "consent_at": iso_now(), "quiz": q,
                           "token": token, "created_at": iso_now(), "updated_at": iso_now()})
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback()
        return jsonify(error="Это время только что заняли. Выберите другое — введённые данные сохранятся."), 409
    return jsonify(ok=True, **booking_public(token))

@app.post("/api/request")
def api_request():
    """Ветка «Подобрать время с менеджером»: заявка без времени, статус «ожидает согласования»."""
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("book:" + client_ip(), 40, 3600):
        return jsonify(error="Слишком много попыток. Попробуйте через час."), 429
    f, err = client_fields(body())
    if err: return jsonify(error=err), 400
    c = db()
    cid = upsert_client(c, f["name"], f["phone"], f["city"])
    row = c.execute("SELECT status FROM clients WHERE id=?", (cid,)).fetchone()
    if row["status"] not in ("booked", "came", "bought"): c.execute("UPDATE clients SET status='request' WHERE id=?", (cid,))
    q = json.dumps(f["quiz"], ensure_ascii=False) if f["quiz"] else ""
    if q: c.execute("UPDATE clients SET quiz=? WHERE id=?", (q, cid))
    token = new_token()
    insert_booking(c, {"kind": "request", "client_id": cid, "status": "pending", "origin": "site", "lead_source": f["lead_source"], "utm": f["utm"],
                       "city": f["city"], "tz": f["tz"], "messenger": f["messenger"], "contact": f["contact"],
                       "consent_ver": FUNNEL["consent_version"], "consent_at": iso_now(), "quiz": q,
                       "token": token, "created_at": iso_now(), "updated_at": iso_now()})
    c.commit()
    return jsonify(ok=True, **booking_public(token))

def booking_by_token(token):
    return db().execute("SELECT b.*, c.name, c.phone, u.name AS manager_name FROM bookings b JOIN clients c ON c.id=b.client_id "
                        "LEFT JOIN users u ON u.id=b.manager_id WHERE b.token=?", (token,)).fetchone()

def booking_public(token):
    """Данные для страницы заявки клиента (по секретной ссылке)."""
    r = booking_by_token(token)
    m_label, contact = contact_display(r)
    out = {"token": token, "kind": r["kind"], "status": r["status"], "name": r["name"].split()[0] if r["name"] else "",
           "manager": r["manager_name"] or "", "messenger": m_label, "contact": contact, "tz": r["tz"],
           "meeting_link": r["meeting_link"] or "", "duration": FUNNEL["duration"]}
    if r["date"] and r["hour"] is not None and r["status"] == "booked":
        start = slot_start(r["date"], r["hour"])
        end = start + dt.timedelta(minutes=SLOT_MINUTES)
        f = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        details = "Время по Москве: " + start.strftime("%d.%m %H:%M") + (". Ссылка: " + r["meeting_link"] if r["meeting_link"] else "")
        out.update(date=r["date"], hour=r["hour"], start=start.isoformat(), ics=f"/ics/{token}.ics",
                   gcal="https://calendar.google.com/calendar/render?action=TEMPLATE"
                        f"&text={quote(EVENT_TITLE)}&dates={f(start)}/{f(end)}&details={quote(details)}")
    return out

@app.get("/api/booking/<token>")
def api_booking(token):
    r = booking_by_token(token)
    if not r: return jsonify(error="Запись не найдена."), 404
    return jsonify(ok=True, **booking_public(token))

@app.post("/api/booking/<token>/cancel")
def api_booking_cancel(token):
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    c = db()
    r = booking_by_token(token)
    if not r or r["status"] == "cancelled": return jsonify(error="Запись не найдена или уже отменена."), 404
    c.execute("UPDATE bookings SET status='cancelled', note=trim(note || ' [отменил клиент]'), updated_at=? WHERE id=?", (iso_now(), r["id"]))
    after_cancel(c, r["client_id"])
    c.commit()
    return jsonify(ok=True, **booking_public(token))

@app.post("/api/booking/<token>/move")
def api_booking_move(token):
    """Перенос самим клиентом: на свободное время, по возможности к тому же менеджеру."""
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("move:" + client_ip(), 60, 3600): return jsonify(error="Слишком много попыток."), 429
    b = body()
    date, hour = b.get("date"), b.get("hour")
    problem = slot_problem(date, hour)
    if problem: return jsonify(error=problem), 409
    c = db()
    r = booking_by_token(token)
    if not r or r["status"] == "cancelled": return jsonify(error="Запись не найдена или отменена."), 404
    c.execute("BEGIN IMMEDIATE")
    try:
        mgr = pick_manager(c, date, hour, exclude_booking=r["id"], prefer=r["manager_id"])
        if not mgr:
            c.rollback(); return jsonify(error="Это время уже занято. Выберите другое."), 409
        c.execute("UPDATE bookings SET kind='slot', status='booked', slot=?, date=?, hour=?, manager_id=?, confirm='', updated_at=? WHERE id=?",
                  (slot_id(date, hour), date, hour, mgr, iso_now(), r["id"]))
        c.execute("UPDATE clients SET status='booked', updated_at=? WHERE id=?", (iso_now(), r["client_id"]))
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback(); return jsonify(error="Это время уже занято. Выберите другое."), 409
    return jsonify(ok=True, **booking_public(token))

@app.get("/ics/<token>.ics")
def ics(token):
    r = booking_by_token(token)
    if not r or r["status"] != "booked" or not r["date"]: abort(404)
    start = slot_start(r["date"], r["hour"])
    end = start + dt.timedelta(minutes=SLOT_MINUTES)
    f = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    desc = "Время по Москве: " + start.strftime("%d.%m.%Y %H:%M") + "\nЗапись: " + request.host_url + "?b=" + token
    if r["meeting_link"]: desc += "\nСсылка на встречу: " + r["meeting_link"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gubenko-zapis//RU", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "BEGIN:VEVENT", f"UID:{token}@gubenko-zapis", f"DTSTAMP:{f(now_utc())}",
             f"DTSTART:{f(start)}", f"DTEND:{f(end)}", f"SUMMARY:{esc(EVENT_TITLE)}", f"DESCRIPTION:{esc(desc)}",
             "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", f"DESCRIPTION:{esc(EVENT_TITLE + ' через час')}", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return Response("\r\n".join(lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": 'inline; filename="konsultaciya.ics"'})

# ---------- вход в кабинет ----------
@app.get("/admin/login")
def page_login():
    if me(): return redirect("/admin")
    return send_from_directory(STATIC, "login.html")

@app.post("/admin/login")
def do_login():
    if not same_origin(): return jsonify(error="Запрос отклонён."), 403
    if rate_limited("login:" + client_ip(), 10, 900):
        return jsonify(error="Слишком много попыток входа. Подождите 15 минут."), 429
    b = body()
    u = db().execute("SELECT * FROM users WHERE login=? AND active=1", ((b.get("login") or "").strip(),)).fetchone()
    if not u or not check_password_hash(u["pw_hash"], b.get("password") or ""):
        return jsonify(error="Неверный логин или пароль."), 401
    session.clear(); session.permanent = True
    session["uid"] = u["id"]
    return jsonify(ok=True)

@app.post("/admin/logout")
def do_logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/admin")
@login_required()
def page_admin(): return send_from_directory(STATIC, "admin.html")

# ---------- API кабинета ----------
def users_list():
    return [dict(id=r["id"], name=r["name"], role=r["role"], public=r["public"])
            for r in db().execute("SELECT * FROM users WHERE active=1 ORDER BY role='admin', id")]

@app.get("/api/admin/me")
@login_required(api=True)
def api_me():
    u = me()
    return jsonify(id=u["id"], name=u["name"], role=u["role"], users=users_list(), hours=HOURS, workdays=WORKDAYS,
                   sources=SOURCES, services=SERVICES, confirm=CONFIRM, attend=ATTEND, client_statuses=CLIENT_STATUSES,
                   messengers=[{"id": m["id"], "label": m["label"]} for m in FUNNEL["messengers"]], brand=FUNNEL["brand"], logo=FUNNEL.get("logo", ""),
                   public_url=FUNNEL.get("public_url", ""), short_links=[{"code": k, "source": resolve_source(v)} for k, v in SHORT_LINKS.items()])

def can_touch(manager_id):
    """Админ работает с любым расписанием, менеджер — только со своим."""
    return is_admin() or manager_id == me()["id"]

def booking_row(r):
    return {k: r[k] for k in ("id", "kind", "slot", "date", "hour", "manager_id", "status", "origin", "lead_source", "service",
                              "confirm", "attend", "meeting_link", "note", "city", "tz", "messenger", "contact",
                              "consent_ver", "consent_at", "created_at", "token")} | {
        "manager": r["manager_name"], "created_by": r["created_by_name"],
        "utm": json.loads(r["utm"]) if r["utm"] else None,
        "quiz": json.loads(r["quiz"]) if r["quiz"] else None,
        "client": {"id": r["client_id"], "name": r["name"], "phone": r["phone"]}}

BOOKING_SQL = ("SELECT b.*, c.name, c.phone, um.name AS manager_name, uc.name AS created_by_name FROM bookings b "
               "JOIN clients c ON c.id=b.client_id LEFT JOIN users um ON um.id=b.manager_id LEFT JOIN users uc ON uc.id=b.created_by ")

@app.get("/api/admin/week")
@login_required(api=True)
def week():
    try:
        start = dt.date.fromisoformat(request.args.get("start", ""))
    except ValueError:
        return jsonify(error="Неверная дата."), 400
    end = (start + dt.timedelta(days=7)).isoformat()
    who = request.args.get("manager", "all")
    c = db()
    sql, args = BOOKING_SQL + "WHERE b.status='booked' AND b.date>=? AND b.date<? ", [start.isoformat(), end]
    bsql, bargs = "SELECT b.*, u.name AS manager_name FROM blocked b JOIN users u ON u.id=b.manager_id WHERE b.date>=? AND b.date<? ", [start.isoformat(), end]
    if not is_admin(): who = str(me()["id"])
    if who != "all":
        sql += "AND b.manager_id=? "; args.append(int(who))
        bsql += "AND b.manager_id=? "; bargs.append(int(who))
    rows = c.execute(sql + "ORDER BY b.date, b.hour, um.id", args).fetchall()
    bl = c.execute(bsql, bargs).fetchall()
    notes = {r["date"]: r["text"] for r in c.execute("SELECT * FROM day_notes WHERE date>=? AND date<?", (start.isoformat(), end))}
    pending = c.execute("SELECT COUNT(*) FROM bookings WHERE status='pending'").fetchone()[0]
    return jsonify(bookings=[booking_row(r) for r in rows], notes=notes, pending=pending, now=iso_now(),
                   blocked=[{"slot": r["slot"], "date": r["date"], "hour": r["hour"], "manager_id": r["manager_id"],
                             "manager": r["manager_name"], "reason": r["reason"]} for r in bl])

def admin_target_manager(b):
    mid = b.get("manager_id")
    if not is_admin(): return me()["id"]
    return mid if isinstance(mid, int) and db().execute("SELECT 1 FROM users WHERE id=? AND active=1", (mid,)).fetchone() else None

def opt(v, allowed):
    v = (v or "").strip()
    return v if v in allowed else ""

@app.patch("/api/admin/users/<int:uid>")
@login_required(api=True)
def admin_user_update(uid):
    """Админ включает/выключает менеджеру приём записей с сайта (отпуск, больничный)."""
    if not is_admin(): return jsonify(error="Доступно только админу."), 403
    b = body()
    if not isinstance(b.get("public"), bool): return jsonify(error="Нет значения."), 400
    n = db().execute("UPDATE users SET public=? WHERE id=? AND role='manager' AND active=1", (1 if b["public"] else 0, uid)).rowcount
    db().commit()
    if not n: return jsonify(error="Менеджер не найден."), 404
    return jsonify(ok=True, users=users_list())

@app.post("/api/admin/bookings")
@login_required(api=True)
def admin_create():
    b = body()
    name = (b.get("name") or "").strip()[:80]
    phone = norm_phone(b.get("phone"))
    if not name: return jsonify(error="Укажите имя."), 400
    if not phone: return jsonify(error=PHONE_ERROR if (b.get("phone") or "").strip() else "Укажите телефон: по нему клиент находится в CRM."), 400
    mid = admin_target_manager(b)
    if not mid: return jsonify(error="Выберите, к кому записать."), 400
    date, hour = b.get("date"), b.get("hour")
    problem = slot_problem(date, hour, for_client=False)
    if problem: return jsonify(error=problem), 409
    c = db()
    c.execute("BEGIN IMMEDIATE")
    try:
        if manager_busy(c, slot_id(date, hour), mid):
            c.rollback(); return jsonify(error="У этого специалиста время уже занято или закрыто."), 409
        city = (b.get("city") or "").strip()[:80]
        cid = upsert_client(c, name, phone, city, "booked")
        m = b.get("messenger") if b.get("messenger") in MESSENGERS else ""
        insert_booking(c, {"kind": "slot", "slot": slot_id(date, hour), "date": date, "hour": hour, "manager_id": mid,
                           "client_id": cid, "status": "booked", "origin": "manager",
                           "lead_source": opt(b.get("lead_source"), SOURCES), "service": opt(b.get("service"), SERVICES),
                           "note": (b.get("note") or "")[:1000], "city": city, "messenger": m,
                           "contact": (b.get("contact") or "").strip()[:64], "meeting_link": (b.get("meeting_link") or "").strip()[:300],
                           "token": new_token(), "created_at": iso_now(), "created_by": me()["id"], "updated_at": iso_now()})
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback(); return jsonify(error="Это время только что заняли."), 409
    return jsonify(ok=True)

@app.patch("/api/admin/bookings/<int:bid>")
@login_required(api=True)
def admin_update(bid):
    """Правка записи: поля карточки, перенос, смена специалиста, отмена."""
    b = body()
    c = db()
    r = c.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not r: return jsonify(error="Запись не найдена."), 404
    pending = r["status"] == "pending"
    if not pending and not can_touch(r["manager_id"]):
        return jsonify(error="Это запись другого специалиста."), 403
    sets, args = [], []
    def put(k, v): sets.append(f"{k}=?"); args.append(v)
    if "confirm" in b: put("confirm", opt(b["confirm"], CONFIRM))
    if "attend" in b:
        a = opt(b["attend"], ATTEND); put("attend", a)
        if a: c.execute("UPDATE clients SET status=?, updated_at=? WHERE id=?", (a, iso_now(), r["client_id"]))
    if "lead_source" in b: put("lead_source", opt(b["lead_source"], SOURCES))
    if "service" in b: put("service", opt(b["service"], SERVICES))
    if "meeting_link" in b:
        link = (b["meeting_link"] or "").strip()[:300]
        if link and not re.match(r"https?://", link): return jsonify(error="Ссылка на встречу должна начинаться с https://"), 400
        put("meeting_link", link)
    if "note" in b: put("note", (b["note"] or "")[:1000])
    if "contact" in b: put("contact", (b["contact"] or "").strip()[:64])
    if "messenger" in b: put("messenger", b["messenger"] if b["messenger"] in MESSENGERS else "")
    if b.get("status") == "cancelled": put("status", "cancelled")
    # перенос / назначение времени / смена специалиста
    if "date" in b or "hour" in b or "manager_id" in b:
        date, hour = b.get("date", r["date"]), b.get("hour", r["hour"])
        if not is_admin(): mid = me()["id"]                      # менеджер ставит только к себе
        elif "manager_id" in b: mid = admin_target_manager(b)    # админ — к любому
        else: mid = r["manager_id"]
        if not mid: return jsonify(error="Выберите специалиста."), 400
        problem = slot_problem(date, hour, for_client=False)
        if problem: return jsonify(error=problem), 409
        if manager_busy(c, slot_id(date, hour), mid, exclude_booking=bid):
            return jsonify(error="У этого специалиста время уже занято или закрыто."), 409
        put("slot", slot_id(date, hour)); put("date", date); put("hour", hour); put("manager_id", mid)
        put("kind", "slot"); put("status", "booked")
        if r["date"] and (r["date"], r["hour"]) != (date, hour): put("confirm", "")
        c.execute("UPDATE clients SET status=CASE WHEN status IN ('request','noshow') THEN 'booked' ELSE status END, updated_at=? WHERE id=?",
                  (iso_now(), r["client_id"]))
    if not sets: return jsonify(ok=True)
    put("updated_at", iso_now())
    try:
        c.execute(f"UPDATE bookings SET {', '.join(sets)} WHERE id=?", args + [bid])
        if b.get("status") == "cancelled": after_cancel(c, r["client_id"])
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback(); return jsonify(error="Это время только что заняли."), 409
    return jsonify(ok=True)

@app.get("/api/admin/requests")
@login_required(api=True)
def requests_list():
    rows = db().execute(BOOKING_SQL + "WHERE b.status='pending' ORDER BY b.created_at").fetchall()
    return jsonify(requests=[booking_row(r) for r in rows])

@app.post("/api/admin/blocked")
@login_required(api=True)
def block():
    b = body()
    date, hour = b.get("date"), b.get("hour")
    mid = admin_target_manager(b)
    if not mid: return jsonify(error="Выберите специалиста."), 400
    if slot_problem(date, hour, for_client=False): return jsonify(error="Неверное время."), 400
    c = db()
    if c.execute("SELECT 1 FROM bookings WHERE slot=? AND manager_id=? AND status='booked'", (slot_id(date, hour), mid)).fetchone():
        return jsonify(error="На это время уже есть запись."), 409
    c.execute("INSERT OR REPLACE INTO blocked(slot,manager_id,date,hour,reason,by) VALUES(?,?,?,?,?,?)",
              (slot_id(date, hour), mid, date, hour, (b.get("reason") or "")[:120], me()["id"]))
    c.commit()
    return jsonify(ok=True)

@app.delete("/api/admin/blocked/<int:mid>/<slot>")
@login_required(api=True)
def unblock(mid, slot):
    if not can_touch(mid): return jsonify(error="Это расписание другого специалиста."), 403
    db().execute("DELETE FROM blocked WHERE slot=? AND manager_id=?", (slot, mid)); db().commit()
    return jsonify(ok=True)

@app.put("/api/admin/notes/<date>")
@login_required(api=True)
def put_note(date):
    try: dt.date.fromisoformat(date)
    except ValueError: return jsonify(error="Неверная дата."), 400
    text = (body().get("text") or "").strip()[:500]
    c = db()
    if text: c.execute("INSERT OR REPLACE INTO day_notes(date,text,by,updated_at) VALUES(?,?,?,?)", (date, text, me()["id"], iso_now()))
    else: c.execute("DELETE FROM day_notes WHERE date=?", (date,))
    c.commit()
    return jsonify(ok=True)

@app.get("/api/admin/clients")
@login_required(api=True)
def clients():
    q = (request.args.get("q") or "").strip().lower()
    st = request.args.get("status") or ""
    sql = ("SELECT c.*, COUNT(b.id) FILTER (WHERE b.status='booked') AS visits, "
           "MAX(b.date || '_' || printf('%02d', b.hour)) FILTER (WHERE b.status='booked') AS last_slot, "
           "GROUP_CONCAT(DISTINCT um.name) AS managers FROM clients c LEFT JOIN bookings b ON b.client_id=c.id "
           "LEFT JOIN users um ON um.id=b.manager_id AND b.status!='cancelled' ")
    where, args = [], []
    if not is_admin():  # менеджер видит своих клиентов и заявки без времени
        where.append("c.id IN (SELECT client_id FROM bookings WHERE manager_id=? OR status='pending')"); args.append(me()["id"])
    if q:
        digits = re.sub(r"\D", "", q)
        cond = ["lower(c.name) LIKE ?", "lower(c.notes) LIKE ?", "lower(c.city) LIKE ?"]
        args += [f"%{q}%"] * 3
        if digits: cond.append("c.phone LIKE ?"); args.append(f"%{digits}%")
        where.append("(" + " OR ".join(cond) + ")")
    if st in CLIENT_STATUSES: where.append("c.status=?"); args.append(st)
    if where: sql += "WHERE " + " AND ".join(where) + " "
    sql += "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT 500"
    rows = db().execute(sql, args).fetchall()
    return jsonify(clients=[{"id": r["id"], "name": r["name"], "phone": r["phone"], "city": r["city"], "status": r["status"],
                             "notes": r["notes"], "visits": r["visits"], "last_slot": r["last_slot"], "managers": r["managers"] or "",
                             "quiz": json.loads(r["quiz"]) if r["quiz"] else None, "created_at": r["created_at"]} for r in rows])

@app.get("/api/admin/clients/<int:cid>")
@login_required(api=True)
def client(cid):
    c = db()
    r = c.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if not r: return jsonify(error="Клиент не найден."), 404
    hist = c.execute(BOOKING_SQL + "WHERE b.client_id=? ORDER BY b.date IS NULL DESC, b.date DESC, b.hour DESC", (cid,)).fetchall()
    if not is_admin() and not any(h["manager_id"] == me()["id"] or h["status"] == "pending" for h in hist):
        return jsonify(error="Это клиент другого специалиста."), 403
    cl = dict(r); cl["quiz"] = json.loads(r["quiz"]) if r["quiz"] else None
    return jsonify(client=cl, bookings=[booking_row(h) for h in hist])

@app.patch("/api/admin/clients/<int:cid>")
@login_required(api=True)
def client_update(cid):
    b = body()
    c = db()
    if not c.execute("SELECT 1 FROM clients WHERE id=?", (cid,)).fetchone(): return jsonify(error="Клиент не найден."), 404
    fields, args = [], []
    if "name" in b and (b["name"] or "").strip(): fields.append("name=?"); args.append(b["name"].strip()[:80])
    if "city" in b: fields.append("city=?"); args.append((b["city"] or "").strip()[:80])
    if "notes" in b: fields.append("notes=?"); args.append((b["notes"] or "")[:4000])
    if "status" in b:
        if b["status"] not in CLIENT_STATUSES: return jsonify(error="Неизвестный статус."), 400
        fields.append("status=?"); args.append(b["status"])
    if "phone" in b:
        p = norm_phone(b["phone"])
        if not p: return jsonify(error=PHONE_ERROR), 400
        fields.append("phone=?"); args.append(p)
    if not fields: return jsonify(ok=True)
    fields.append("updated_at=?"); args.append(iso_now())
    try:
        c.execute(f"UPDATE clients SET {', '.join(fields)} WHERE id=?", args + [cid]); c.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Клиент с таким телефоном уже есть."), 409
    return jsonify(ok=True)

@app.get("/api/admin/stats")
@login_required(api=True)
def stats():
    days = max(1, min(int(request.args.get("days", "7") or 7), 365))
    since = (today_msk() - dt.timedelta(days=days - 1)).isoformat()
    c = db()
    src = (request.args.get("src") or "").strip()
    ev = {e: c.execute("SELECT COUNT(*) FROM events WHERE event=? AND day>=?" + (" AND src=?" if src else ""),
                       (e, since) + ((src,) if src else ())).fetchone()[0] for e in FUNNEL_EVENTS}
    srcs = [r[0] for r in c.execute("SELECT src FROM events WHERE day>=? AND src!='' GROUP BY src ORDER BY COUNT(*) DESC", (since,))]
    today = today_msk().isoformat()
    # менеджер видит свои результаты; админ — общие или по выбранному менеджеру
    mid = me()["id"] if not is_admin() else (int(request.args["manager"]) if (request.args.get("manager") or "").isdigit() else None)
    mf, ma = (" AND manager_id=?", (mid,)) if mid else ("", ())

    def results(extra="", args=()):
        r = c.execute("SELECT COUNT(*) AS booked,"
                      " SUM(attend='came') AS came, SUM(attend='noshow') AS noshow, SUM(attend='nc') AS nc,"
                      " SUM(date<? AND attend='') AS unmarked,"
                      " COUNT(DISTINCT CASE WHEN client_id IN (SELECT id FROM clients WHERE status='bought') THEN client_id END) AS bought"
                      " FROM bookings WHERE kind='slot' AND status!='cancelled' AND date>=?" + extra,
                      (today, since) + args).fetchone()
        return {k: r[k] or 0 for k in r.keys()}
    outcome = results(mf, ma)
    outcome["came"] += outcome["nc"]  # «пришли» = все, кто был на встрече
    by_source = [dict(r) for r in c.execute("SELECT lead_source AS name, COUNT(*) AS n FROM bookings WHERE status!='cancelled' AND substr(created_at,1,10)>=?" + mf +
                                            " GROUP BY lead_source ORDER BY n DESC", (since,) + ma)]
    per_manager = []
    if is_admin():
        for u in c.execute("SELECT id, name FROM users WHERE active=1 ORDER BY role='admin', id").fetchall():
            row = results(" AND manager_id=?", (u["id"],))
            if row["booked"] or u["id"] != me()["id"]:
                per_manager.append({"id": u["id"], "name": u["name"], **row})
    return jsonify(days=days, src=src, srcs=srcs, events=ev, outcome=outcome, by_source=by_source,
                   manager=mid, per_manager=per_manager)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
