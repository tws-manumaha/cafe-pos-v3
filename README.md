# Cafe POS — v3

An open-source **restaurant POS and management platform** for cafés and small
restaurants: billing, kitchen display, thermal printing, inventory, purchasing,
loyalty, offers, refunds and profit reporting.

**Python (FastAPI) + SQLAlchemy** — runs on **SQLite**, **PostgreSQL** or
**Microsoft SQL Server** by changing one environment variable. Served over
HTTPS by **Nginx with automatic Let's Encrypt renewal**.

---

## What's new in v3

| Roadmap item | Status |
|---|---|
| **Thermal printer (ESC/POS)** for bills and KOT | ✅ Raw ESC/POS built server-side, sent to a network printer on :9100 |
| **Split bill by item** | ✅ Split a bill into separate bills by choosing which items go where |
| **Purchase-order line editor** | ✅ Proper multi-line grid (ingredient, qty, rate) with running total |
| **Stock take & wastage** | ✅ Counted-quantity stock take with variance, and a wastage entry screen |
| **Full offline sync** | ✅ Offline bills carry a `client_uuid`; server sync is idempotent (no duplicates) |
| **Voids & refunds with approval** | ✅ Manager/owner only; void restores stock and reverses loyalty points |

## Features

**Front of house** — dish grid, combos, discounts, offer codes, GST split,
split payments, split bill by item, merge bills, table assignment,
dine-in / takeaway / aggregator channels, printable receipt.

**Kitchen** — a KOT is created per order; kitchen board Pending → Preparing →
Ready → Served; one-tap KOT printing.

**Printing** — ESC/POS receipts and KOTs at 42 or 32 columns, sent straight to a
network thermal printer or downloaded as a `.escpos` file.

**Inventory** — live stock, reorder levels, Out / Reorder / Low / OK,
automatic draw-down per sale, stock take with variance, wastage recording,
suppliers and purchase orders.

**Marketing** — offers (percent/flat, minimum bill, coupon codes), combos,
loyalty points (earn per ₹100, redeem against a bill).

**Reporting** — dashboard, item ranking, 14-day trend, P&L
(revenue − COGS − overheads − salaries), GSTR-1 CSV export, audit log.

**Platform** — roles (owner / manager / cashier / kitchen), JWT auth,
PBKDF2-SHA256 passwords, multi-outlet, offline-first till, Swiggy/Zomato
intake webhook.

---

## Quick start

```bash
cd cafe_pos_v3
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000>.

| User | Password | Role |
|---|---|---|
| owner | owner123 | owner |
| manager | manager123 | manager |
| cashier | cashier123 | cashier |
| kitchen | kitchen123 | kitchen |

**Change these before going live.** `./run.sh` / `run.bat` do the above in one step.

---

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./cafe.db` | Postgres / MSSQL examples in `INSTALL.md` |
| `JWT_SECRET` | dev value | **Set a long random string in production** |
| `JWT_EXPIRE_MIN` | `720` | Token lifetime |
| `GST_RATE` | `0.05` | |
| `WASTE_RATE` | `0.08` | Added to every recipe cost |
| `PRINTER_HOST` | *(empty)* | IP/hostname of the thermal printer |
| `PRINTER_PORT` | `9100` | Raw printing port |
| `AGGREGATOR_TOKEN` | dev value | Header `X-AGG-TOKEN` for Swiggy/Zomato intake |

### Thermal printer

Any ESC/POS network printer works (Epson TM-T82, TVS RP-3230, etc.):

```bash
export PRINTER_HOST=192.168.1.50
export PRINTER_PORT=9100
```

Then use **Print** on an order or KOT, or test with
`GET /api/print/test?send=1`. Without `PRINTER_HOST`, printing returns the raw
`.escpos` file instead of sending it.

> ESC/POS text is Latin-1. Bills print English item names; Devanagari needs a
> printer with a built-in font chip.

---

## Production deployment

```bash
sudo DOMAIN=cafe.example.com EMAIL=you@example.com ./deploy/install.sh
```

Installs Python/PostgreSQL/Nginx/Certbot, creates a service user, seeds the DB,
installs the systemd unit, configures the Nginx reverse proxy, obtains a
Let's Encrypt certificate and enables **`certbot.timer` for automatic renewal**.

Full manual steps, Windows/IIS and Docker: **[INSTALL.md](INSTALL.md)**.

---

## Project layout

```
app/
  db.py        engine/session — one DATABASE_URL for SQLite/Postgres/MSSQL
  models.py    SQLAlchemy models (users, dishes, orders, KOT, POs, refunds…)
  security.py  PBKDF2 password hashing + JWT
  escpos.py    ESC/POS receipt and KOT builder
  main.py      FastAPI app and all REST endpoints
  seed.py      loads data/app_data.json (from the Excel costing workbook)
static/        single-page front end + service worker (offline)
deploy/        nginx, systemd, .env example, install.sh
data/          app_data.json (409 ingredients, 99 dishes, 681 recipe lines)
```

API docs: **`/docs`** (Swagger UI).

## License

MIT — see [LICENSE](LICENSE). Roadmap: [ROADMAP.md](ROADMAP.md).
