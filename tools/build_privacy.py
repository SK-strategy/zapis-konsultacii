"""Собирает server/static/privacy.html из server/policy.txt (текст политики ИП Губенко А.А.).
   Формат policy.txt: по абзацу в строке, «[*]» — жирный абзац в исходном документе, «[]» — обычный.
   Запуск: python tools/build_privacy.py"""
import html, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV = os.path.join(ROOT, "server")
rows = []
for line in open(os.path.join(SRV, "policy.txt"), encoding="utf-8"):
    m = re.match(r"\[(\*?)\] ?(.*)", line.rstrip("\n"))
    if m and m.group(2).strip():
        rows.append((m.group(1) == "*", re.sub(r"\s+", " ", m.group(2)).strip()))

def typo(s):  # типографика: короткое тире между словами, «ёлочки» вместо прямых кавычек
    s = s.replace(" - ", " — ").replace(", -", ", —")
    return re.sub(r'"([^"]*)"', r"«\1»", s)

out, lst, in_terms = [], None, False
def close():
    global lst
    if lst: out.append(f"</{lst}>"); lst = None
def item(tag, text, cls=""):
    global lst
    if lst != tag:
        close(); out.append(f"<{tag}{cls}>"); lst = tag
    out.append(f"<li>{text}</li>")

# заголовок документа — две первые жирные строки
title = typo(rows[0][1] + " " + rows[1][1])
rows = rows[2:]
# подпись — последние строки
sign_at = next(i for i, (_, t) in enumerate(rows) if t.startswith("Индивидуальный"))
body, rows = rows[:sign_at], rows[sign_at:]

i = 0
while i < len(body):
    bold, t = body[i]
    if bold and re.match(r"^\d+\. ", t):  # раздел: «1. Общие положения», продолжение — следующие жирные строки
        while i + 1 < len(body) and body[i + 1][0] and not re.match(r"^\d", body[i + 1][1]):
            i += 1; t += " " + body[i][1]
        close(); out.append(f"<h2>{html.escape(typo(t.rstrip(',')))}</h2>")
        in_terms = False
    elif bold and re.match(r"^\d+\.\d+\. ", t) and len(t) < 120:
        close(); out.append(f"<h3>{html.escape(typo(t))}</h3>")
        in_terms = t.startswith("1.5.")
    elif t.startswith("•"):
        item("ul", html.escape(typo(t.lstrip("• "))))
    elif re.match(r"^\d\)", t):
        item("ol", html.escape(typo(re.sub(r"^(\d\))\s*", r"\1 ", t))), ' class="num"')
    elif in_terms and " - " in t and not re.match(r"^\d", t):
        term, rest = t.split(" - ", 1)
        close(); out.append(f'<p class="term"><b>{html.escape(term)}</b> — {html.escape(typo(rest))}</p>')
    elif lst == "ul" and not re.match(r"^(\d|[А-ЯЁ])", t):  # продолжение предыдущего пункта списка
        out[-1] = out[-1][:-5] + " " + html.escape(typo(t)) + "</li>"
    else:
        close(); out.append(f"<p>{html.escape(typo(t))}</p>")
    i += 1
close()

page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Политика обработки персональных данных</title><link rel="stylesheet" href="/static/app.css">
<style>
body{{background:var(--bg)}}
main{{max-width:760px;margin:0 auto;padding:24px 16px 56px;line-height:1.55}}
.back{{display:inline-block;font-size:14px;margin-bottom:18px;color:var(--accent)}}
h1{{font-family:var(--f-display);font-size:clamp(20px,4.6vw,28px);line-height:1.25;margin:0 0 6px}}
.op{{color:var(--muted);font-size:14px;margin:0 0 22px}}
.lead{{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;margin:0 0 28px;font-size:15px}}
.lead p{{margin:0 0 6px}} .lead p:last-child{{margin:0}}
h2{{font-size:19px;margin:34px 0 10px;padding-top:14px;border-top:1px solid var(--line)}}
h3{{font-size:16px;margin:22px 0 8px}}
p,li{{font-size:15px;overflow-wrap:anywhere}}
p{{margin:0 0 10px}}
ul,ol{{margin:0 0 12px;padding-left:22px}} ol.num{{list-style:none;padding-left:8px}} li{{margin:0 0 4px}}
.term b{{font-weight:600}}
.sign{{margin-top:36px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted)}}
</style></head>
<body><main>
<a class="back" href="/">← Вернуться к записи</a>
<h1>{html.escape(title)}</h1>
<p class="op">Оператор: индивидуальный предприниматель Губенко Анастасия Александровна</p>
<div class="lead">
<p>Форма записи на консультацию собирает только имя, номер телефона и ответы на три вопроса теста — чтобы подтвердить запись, позвонить в выбранное время и подготовиться к разговору.</p>
<p>Отправляя форму, вы даёте согласие на обработку этих данных в соответствии с Политикой ниже.</p>
</div>
{chr(10).join(out)}
<p class="sign">Индивидуальный предприниматель Губенко А.А.</p>
</main></body></html>
"""
open(os.path.join(SRV, "static", "privacy.html"), "w", encoding="utf-8").write(page)
print("ok", len(out))
