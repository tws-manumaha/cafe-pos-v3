# Installation

## 1. Local / single machine

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Other devices on the LAN can reach it at `http://<your-ip>:8000`.

## 2. Database

```bash
# SQLite (default)
export DATABASE_URL="sqlite:///./cafe.db"

# PostgreSQL
export DATABASE_URL="postgresql+psycopg2://cafepos:password@localhost:5432/cafepos"
pip install psycopg2-binary

# Microsoft SQL Server
export DATABASE_URL="mssql+pyodbc://sa:password@localhost/cafepos?driver=ODBC+Driver+17+for+SQL+Server"
pip install pyodbc
```

Tables are created on first start.

## 3. Thermal printer

Any ESC/POS network printer:

```bash
export PRINTER_HOST=192.168.1.50
export PRINTER_PORT=9100
```

Verify from the API:

```bash
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/print/test?send=1"
```

Endpoints:
- `GET /api/print/bill/{order_no}?send=1` — receipt
- `GET /api/print/kot/{ticket_id}?send=1` — kitchen ticket
- add `width=32` for 58 mm paper (default 42 for 80 mm)

Without `PRINTER_HOST` the same endpoints return a `.escpos` file you can pipe
to a printer (`cat file.escpos > /dev/usb/lp0`).

## 4. Production on Debian/Ubuntu (Nginx + Let's Encrypt)

```bash
sudo DOMAIN=cafe.example.com EMAIL=you@example.com ./deploy/install.sh
```

Installs dependencies, creates the `cafepos` user, builds the venv, seeds the
database, installs `cafe-pos.service`, configures Nginx as a reverse proxy,
issues the certificate and enables **`certbot.timer`** for automatic renewal.

Verify renewal:

```bash
sudo certbot renew --dry-run
```

### Manual steps

```bash
sudo cp deploy/cafe-pos.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now cafe-pos

sudo cp deploy/nginx-cafe-pos.conf /etc/nginx/sites-available/cafe-pos
sudo ln -s /etc/nginx/sites-available/cafe-pos /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d cafe.example.com --agree-tos -m you@example.com --redirect
sudo systemctl enable --now certbot.timer
```

## 5. Windows / IIS

Python cannot run inside IIS natively. Run uvicorn as a Windows service
(e.g. with NSSM) on `127.0.0.1:8000`, then use **IIS + ARR + URL Rewrite** to
reverse-proxy your site to it.

## 6. Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t cafe-pos .
docker run -d -p 8000:8000 -v cafepos_data:/app/data \
  -e JWT_SECRET=$(openssl rand -hex 32) --name cafe-pos cafe-pos
```

## 7. Post-install checklist

- [ ] Change the four demo passwords
- [ ] Set a strong `JWT_SECRET`
- [ ] Set `PRINTER_HOST` and print a test slip
- [ ] Confirm HTTPS and `certbot renew --dry-run`
- [ ] Point `DATABASE_URL` at PostgreSQL/MSSQL for anything beyond one till
- [ ] Schedule nightly backups (`pg_dump`)
- [ ] Set `AGGREGATOR_TOKEN` before enabling Swiggy/Zomato intake
