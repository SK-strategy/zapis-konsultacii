"""Собирает тестовую версию для GitHub Pages в корень репозитория:
   index.html (воронка и запись), admin.html (админка без входа), static/.
   Запуск: python tools/build_demo.py"""
import json, os, re, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
funnel = json.load(open(os.path.join(SRV, "funnel.json"), encoding="utf-8"))
os.makedirs(os.path.join(ROOT, "static"), exist_ok=True)
shutil.copy(os.path.join(SRV, "static", "app.css"), os.path.join(ROOT, "static", "app.css"))
api = open(os.path.join(ROOT, "tools", "demo-api.js"), encoding="utf-8").read()
open(os.path.join(ROOT, "static", "demo-api.js"), "w", encoding="utf-8").write(
    api.replace("/*FUNNEL_JSON*/null", json.dumps(funnel, ensure_ascii=False)))
BANNER = ('<div style="background:var(--warn-soft);color:var(--warn);font-size:13px;padding:8px 12px;border-radius:10px;'
          'max-width:1180px;margin:10px auto 0">Тестовая версия: записи хранятся только в этом браузере. {extra}</div>')
def build(src, dst, extra, admin=False):
    s = open(os.path.join(SRV, "static", src), encoding="utf-8").read()
    s = s.replace('href="/static/app.css"', 'href="static/app.css"')
    s = s.replace('<link rel="stylesheet" href="static/app.css">', '<link rel="stylesheet" href="static/app.css">\n<script src="static/demo-api.js"></script>', 1)
    s = re.sub(r"<body>", "<body>\n" + BANNER.format(extra=extra), s, count=1)
    if admin:
        s = s.replace("location.href='/admin/login'", "location.href='./'")
    open(os.path.join(ROOT, dst), "w", encoding="utf-8").write(s)
build("book.html", "index.html", 'Посмотреть, как это видят менеджеры: <a href="admin.html">админка</a>.')
build("admin.html", "admin.html", 'В рабочей версии здесь вход по логину и паролю. <a href="./">Страница для клиентов</a>.', admin=True)
print("ok")
