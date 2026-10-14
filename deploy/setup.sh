#!/bin/bash
# Установка сервиса записи на чистый сервер Ubuntu (24.04 / 26.04).
# Запуск одной командой из консоли сервера (под root):
#   curl -fsSL https://raw.githubusercontent.com/SK-strategy/zapis-konsultacii/main/deploy/setup.sh | bash -s -- губенко.онлайн
# Можно без домена (тогда сайт будет по IP, без HTTPS):  ... | bash
# Повторный запуск безопасен: обновит код и настройки, данные не трогает.
set -euo pipefail

DOMAIN_IN="${1:-}"
REPO="https://github.com/SK-strategy/zapis-konsultacii.git"
APP=/opt/zapis
DATA=/var/lib/zapis
ENVF=/etc/zapis.env

say() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Запустите под root (sudo -i)"; exit 1; }

say "1/7 Ставлю системные пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3-venv python3-pip nginx certbot python3-certbot-nginx sqlite3 ufw >/dev/null

DOMAIN=""
if [ -n "$DOMAIN_IN" ]; then
  DOMAIN=$(python3 -c "import sys;print(sys.argv[1].strip().lower().encode('idna').decode())" "$DOMAIN_IN")
  echo "Домен: $DOMAIN_IN ($DOMAIN)"
fi

say "2/7 Код из GitHub"
id zapis >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin zapis
if [ -d "$APP/.git" ]; then git -C "$APP" fetch -q origin && git -C "$APP" reset -q --hard origin/main
else rm -rf "$APP"; git clone -q "$REPO" "$APP"; fi
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/server/requirements.txt"
mkdir -p "$DATA/backups"
chown -R zapis:zapis "$DATA"
git config --global --add safe.directory "$APP" || true

say "3/7 Кабинеты"
SECURE=1; [ -z "$DOMAIN" ] && SECURE=0
if [ ! -f "$ENVF" ]; then
  umask 077
  printf 'DATA_DIR=%s\nCOOKIE_SECURE=%s\n' "$DATA" "$SECURE" > "$ENVF"
  chown root:zapis "$ENVF"; chmod 640 "$ENVF"
elif [ -n "$DOMAIN" ]; then
  sed -i 's/^COOKIE_SECURE=.*/COOKIE_SECURE=1/' "$ENVF"
fi
manage() { (cd "$APP/server" && sudo -u zapis env DATA_DIR="$DATA" MANAGE_PASSWORD="${PW:-}" "$APP/venv/bin/python" manage.py "$@"); }
ask_pw() {  # пароль вводится скрыто и нигде не сохраняется в открытом виде
  while :; do
    read -r -s -p "  пароль для «$1» (логин $2, от 8 символов): " PW </dev/tty; echo
    [ ${#PW} -ge 8 ] && break; echo "  слишком короткий, ещё раз"
  done
}
if [ -z "$(manage list-users 2>/dev/null)" ]; then
  echo "Создаю кабинеты. Логины: admin, natalya, roman."
  ask_pw "Кабинет админа" admin;     manage ensure-user admin "Админ" admin
  ask_pw "Менеджер Наталья" natalya; manage ensure-user natalya "Наталья" manager
  ask_pw "Менеджер Роман" roman;     manage ensure-user roman "Роман" manager
  PW=""
else
  echo "Кабинеты уже есть:"; manage list-users
fi

say "4/7 Служба приложения"
cat > /etc/systemd/system/zapis.service <<EOF
[Unit]
Description=Запись на консультацию
After=network.target

[Service]
User=zapis
Group=zapis
EnvironmentFile=$ENVF
WorkingDirectory=$APP/server
ExecStart=$APP/venv/bin/gunicorn --chdir $APP/server --bind 127.0.0.1:8000 --workers 2 --preload --access-logfile - app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# автообновление из GitHub каждые 5 минут
cat > /usr/local/bin/zapis-update <<EOF
#!/bin/bash
set -e
cd $APP
git fetch -q origin main
if [ "\$(git rev-parse HEAD)" != "\$(git rev-parse origin/main)" ]; then
  git reset -q --hard origin/main
  $APP/venv/bin/pip install -q -r server/requirements.txt
  systemctl restart zapis
  echo "обновлено до \$(git rev-parse --short HEAD)"
fi
EOF
chmod +x /usr/local/bin/zapis-update
cat > /etc/systemd/system/zapis-update.service <<EOF
[Unit]
Description=Обновление сервиса записи из GitHub
[Service]
Type=oneshot
ExecStart=/usr/local/bin/zapis-update
EOF
cat > /etc/systemd/system/zapis-update.timer <<EOF
[Unit]
Description=Проверка обновлений каждые 5 минут
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF

# ежедневная копия базы, храним 30 дней
cat > /etc/cron.daily/zapis-backup <<EOF
#!/bin/bash
[ -f $DATA/zapis.sqlite3 ] || exit 0
sqlite3 $DATA/zapis.sqlite3 ".backup '$DATA/backups/zapis-\$(date +%F).sqlite3'"
find $DATA/backups -name 'zapis-*.sqlite3' -mtime +30 -delete
EOF
chmod +x /etc/cron.daily/zapis-backup

systemctl daemon-reload
systemctl enable -q --now zapis zapis-update.timer
systemctl restart zapis

say "5/7 Веб-сервер nginx"
NAMES="${DOMAIN:-_}"
[ -n "$DOMAIN" ] && NAMES="$DOMAIN www.$DOMAIN"
cat > /etc/nginx/sites-available/zapis <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $NAMES;
    client_max_body_size 1m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/zapis /etc/nginx/sites-enabled/zapis
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && systemctl reload nginx

say "6/7 Брандмауэр"
ufw allow OpenSSH >/dev/null; ufw allow 'Nginx Full' >/dev/null; ufw --force enable >/dev/null

say "7/7 HTTPS"
if [ -n "$DOMAIN" ]; then
  IP=$(curl -fsS4 https://ifconfig.me || true)
  DNS=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')
  if [ -n "$IP" ] && [ "$IP" = "$DNS" ]; then
    certbot --nginx -n --agree-tos --register-unsafely-without-email --redirect -d "$DOMAIN" $( [ "$(getent ahostsv4 "www.$DOMAIN" | awk 'NR==1{print $1}')" = "$IP" ] && echo "-d www.$DOMAIN" ) \
      && echo "HTTPS включён."
  else
    echo "Домен $DOMAIN_IN пока указывает на «${DNS:-никуда}», а сервер — $IP."
    echo "Пропишите в DNS A-запись на $IP, подождите 15–60 минут и запустите эту же команду ещё раз."
  fi
fi

sleep 2
if curl -fsS -o /dev/null http://127.0.0.1:8000/api/funnel; then say "Готово! Сервис работает."
else echo "Сервис не отвечает. Журнал: journalctl -u zapis -n 50"; fi
[ -n "$DOMAIN" ] && echo "Адрес: https://$DOMAIN_IN   Админка: https://$DOMAIN_IN/admin"
[ -z "$DOMAIN" ] && echo "Адрес: http://$(curl -fsS4 https://ifconfig.me 2>/dev/null)/"
