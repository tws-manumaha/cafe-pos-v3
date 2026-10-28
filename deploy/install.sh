#!/usr/bin/env bash
# One-shot installer for Debian/Ubuntu: Nginx + Let's Encrypt auto-renew + systemd.
# Usage:  sudo DOMAIN=cafe.example.com EMAIL=you@example.com ./deploy/install.sh
set -euo pipefail
DOMAIN="${DOMAIN:?set DOMAIN=cafe.example.com}"
EMAIL="${EMAIL:?set EMAIL=you@example.com}"
APP_DIR=/opt/cafe-pos
APP_USER=cafepos

echo "==> Installing packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx certbot python3-certbot-nginx \
    postgresql postgresql-contrib rsync curl

echo "==> Creating service user"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

echo "==> Copying application to $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --exclude '.venv' --exclude 'cafe.db' --exclude '__pycache__' ./ "$APP_DIR"/
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Python environment"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/deploy/.env.example" "$APP_DIR/.env"
  sed -i "s/CHANGE_ME_TO_A_LONG_RANDOM_STRING/$(openssl rand -hex 32)/" "$APP_DIR/.env"
  sed -i "s/CHANGE_ME_WEBHOOK_TOKEN/$(openssl rand -hex 16)/" "$APP_DIR/.env"
  echo "!!  Edit $APP_DIR/.env (set your DATABASE_URL password), then re-run."
fi
chmod 600 "$APP_DIR/.env"; chown "$APP_USER:$APP_USER" "$APP_DIR/.env"

echo "==> Database (if using local PostgreSQL)"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='cafepos'" | grep -q 1 || \
  sudo -u postgres createdb cafepos
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='cafepos'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER cafepos WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE cafepos TO cafepos;"

echo "==> Seed database"
(cd "$APP_DIR" && sudo -u "$APP_USER" env $(cat "$APP_DIR/.env" | xargs) "$APP_DIR/.venv/bin/python" -m app.seed) || true

echo "==> systemd service"
cp "$APP_DIR/deploy/cafe-pos.service" /etc/systemd/system/cafe-pos.service
systemctl daemon-reload && systemctl enable --now cafe-pos

echo "==> Nginx"
sed "s/cafe.example.com/$DOMAIN/g" "$APP_DIR/deploy/nginx-cafe-pos.conf" > /etc/nginx/sites-available/cafe-pos
ln -sf /etc/nginx/sites-available/cafe-pos /etc/nginx/sites-enabled/cafe-pos
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Let's Encrypt certificate (auto-renews via certbot.timer)"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
systemctl enable --now certbot.timer
systemctl list-timers certbot.timer --no-pager || true

echo "==> Done. Open https://$DOMAIN"
