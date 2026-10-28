import os, csv, io, json, hmac
from datetime import datetime, date, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .db import Base, engine, get_db
from .models import *
from .security import hash_password, verify_password, create_token, decode_token
from . import escpos

GST = float(os.getenv("GST_RATE", "0.05"))
WASTE = float(os.getenv("WASTE_RATE", "0.08"))
POINTS_PER_100 = 1          # loyalty: 1 point per ₹100 spent
POINT_VALUE = 1.0           # 1 point = ₹1
AGG_TOKEN = os.getenv("AGGREGATOR_TOKEN", "dev-agg-token")

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Cafe POS", version="2.0.0",
              description="Restaurant POS & management API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------- auth ----------------
def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if not cred:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = decode_token(cred.credentials)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    u = db.query(User).filter(User.username == payload["sub"]).first()
    if not u or not u.active:
        raise HTTPException(401, "Inactive user")
    return u

def require(*roles):
    def dep(u: User = Depends(current_user)) -> User:
        if u.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return u
    return dep

def audit(db, u, action, entity="", entity_id="", detail="", ip=""):
    db.add(AuditLog(username=(u.username if u else "system"), action=action,
                    entity=entity, entity_id=str(entity_id), detail=detail[:2000], ip=ip))

class LoginIn(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == data.username).first()
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    audit(db, u, "login", "user", u.id, ip=request.client.host if request.client else "")
    db.commit()
    return {"token": create_token(u.username, u.role), "role": u.role,
            "name": u.name or u.username, "username": u.username, "outlet_id": u.outlet_id}

@app.get("/api/auth/me")
def me(u: User = Depends(current_user)):
    return {"username": u.username, "name": u.name, "role": u.role, "outlet_id": u.outlet_id}

# ---------------- outlets & tables ----------------
class OutletIn(BaseModel):
    name: str; address: str = ""; phone: str = ""; gstin: str = ""

@app.get("/api/outlets")
def outlets(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": o.id, "name": o.name, "address": o.address, "gstin": o.gstin}
            for o in db.query(Outlet).all()]

@app.post("/api/outlets")
def add_outlet(d: OutletIn, db: Session = Depends(get_db), u: User = Depends(require("owner"))):
    o = Outlet(**d.model_dump()); db.add(o); audit(db, u, "create", "outlet", "", d.name)
    db.commit(); return {"id": o.id}

class TableIn(BaseModel):
    name: str; seats: int = 2; outlet_id: Optional[int] = None

@app.get("/api/tables")
def tables(outlet_id: Optional[int] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(TableT)
    if outlet_id: q = q.filter(TableT.outlet_id == outlet_id)
    return [{"id": t.id, "name": t.name, "seats": t.seats, "status": t.status,
             "outlet_id": t.outlet_id} for t in q.order_by(TableT.name).all()]

@app.post("/api/tables")
def add_table(d: TableIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    t = TableT(**d.model_dump()); db.add(t); db.commit(); return {"id": t.id}

class TableStatusIn(BaseModel):
    status: str

@app.put("/api/tables/{tid}")
def set_table(tid: int, d: TableStatusIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    t = db.get(TableT, tid)
    if not t: raise HTTPException(404, "Table not found")
    t.status = d.status; db.commit(); return {"ok": True}

# ---------------- menu ----------------
@app.get("/api/dishes")
def list_dishes(db: Session = Depends(get_db), u: User = Depends(current_user)):
    out = []
    for d in db.query(Dish).options(joinedload(Dish.lines).joinedload(RecipeLine.ingredient)).order_by(Dish.category, Dish.name_en):
        cost = sum(l.qty * (l.ingredient.cost_per_unit if l.ingredient else 0) for l in d.lines) * (1 + WASTE)
        exg = d.price / (1 + GST)
        out.append({"id": d.id, "name_en": d.name_en, "name_mr": d.name_mr, "category": d.category,
                    "diet": d.diet, "price": round(d.price, 2), "cost": round(cost, 2),
                    "margin": round((exg - cost) / exg, 4) if exg else 0, "active": d.active,
                    "hsn": d.hsn, "n_ingredients": len(d.lines)})
    return out

class DishIn(BaseModel):
    name_en: str; name_mr: str = ""; category: str = ""; diet: str = "Veg"
    price: float = 0; hsn: str = "9963"; active: bool = True

@app.post("/api/dishes")
def create_dish(d: DishIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = Dish(**d.model_dump()); db.add(o); audit(db, u, "create", "dish", "", d.name_en)
    db.commit(); return {"id": o.id}

@app.put("/api/dishes/{did}")
def update_dish(did: int, d: DishIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = db.get(Dish, did)
    if not o: raise HTTPException(404, "Dish not found")
    for k, v in d.model_dump().items(): setattr(o, k, v)
    audit(db, u, "update", "dish", did, d.name_en); db.commit(); return {"ok": True}

# ---------------- inventory ----------------
@app.get("/api/ingredients")
def list_ingredients(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": i.id, "code": i.code, "name_en": i.name_en, "name_mr": i.name_mr,
             "category": i.category, "unit": i.unit, "cost_per_unit": i.cost_per_unit,
             "stock_qty": i.stock_qty, "reorder_level": i.reorder_level, "shelf_days": i.shelf_days,
             "storage": i.storage,
             "status": ("Out" if i.stock_qty <= 0 else "Reorder" if i.stock_qty < i.reorder_level
                        else "Low" if i.stock_qty < i.reorder_level * 1.5 else "OK")}
            for i in db.query(Ingredient).order_by(Ingredient.category, Ingredient.name_en)]

class IngIn(BaseModel):
    cost_per_unit: Optional[float] = None
    reorder_level: Optional[float] = None
    stock_qty: Optional[float] = None

@app.put("/api/ingredients/{iid}")
def update_ingredient(iid: int, d: IngIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = db.get(Ingredient, iid)
    if not o: raise HTTPException(404, "Ingredient not found")
    for k, v in d.model_dump(exclude_none=True).items(): setattr(o, k, v)
    audit(db, u, "update", "ingredient", iid); db.commit(); return {"ok": True}

class StockIn(BaseModel):
    qty_change: float; reason: str = "purchase"

@app.post("/api/ingredients/{iid}/stock")
def move_stock(iid: int, s: StockIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    o = db.get(Ingredient, iid)
    if not o: raise HTTPException(404, "Ingredient not found")
    o.stock_qty += s.qty_change
    db.add(StockMove(ingredient_id=iid, qty_change=s.qty_change, reason=s.reason))
    audit(db, u, "stock", "ingredient", iid, f"{s.qty_change} {s.reason}")
    db.commit(); return {"ok": True, "stock_qty": o.stock_qty}

# ---------------- combos & offers ----------------
@app.get("/api/combos")
def combos(db: Session = Depends(get_db), u: User = Depends(current_user)):
    out = []
    for c in db.query(Combo).options(joinedload(Combo.items)).all():
        out.append({"id": c.id, "name": c.name, "price": c.price, "active": c.active,
                    "items": [{"dish_id": i.dish_id, "qty": i.qty} for i in c.items]})
    return out

class ComboIn(BaseModel):
    name: str; price: float; items: List[dict] = []

@app.post("/api/combos")
def add_combo(d: ComboIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    c = Combo(name=d.name, price=d.price)
    db.add(c); db.flush()
    for it in d.items:
        db.add(ComboItem(combo_id=c.id, dish_id=int(it["dish_id"]), qty=int(it.get("qty", 1))))
    audit(db, u, "create", "combo", c.id, d.name); db.commit(); return {"id": c.id}

@app.get("/api/offers")
def offers(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": o.id, "name": o.name, "code": o.code, "kind": o.kind, "value": o.value,
             "min_amount": o.min_amount, "starts": o.starts, "ends": o.ends, "active": o.active}
            for o in db.query(Offer).all()]

class OfferIn(BaseModel):
    name: str; code: str = ""; kind: str = "percent"; value: float = 0
    min_amount: float = 0; starts: str = ""; ends: str = ""; active: bool = True

@app.post("/api/offers")
def add_offer(d: OfferIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = Offer(**d.model_dump()); db.add(o); audit(db, u, "create", "offer", "", d.name)
    db.commit(); return {"id": o.id}

# ---------------- customers / loyalty ----------------
class CustIn(BaseModel):
    name: str = ""; phone: str

@app.get("/api/customers")
def customers(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": c.id, "name": c.name, "phone": c.phone, "points": c.points}
            for c in db.query(Customer).order_by(Customer.id.desc()).limit(500)]

@app.post("/api/customers")
def add_customer(d: CustIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    c = db.query(Customer).filter(Customer.phone == d.phone).first()
    if not c:
        c = Customer(name=d.name, phone=d.phone); db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "points": c.points}

# ---------------- suppliers & purchase orders ----------------
class SupIn(BaseModel):
    name: str; phone: str = ""; email: str = ""; gstin: str = ""; address: str = ""

@app.get("/api/suppliers")
def suppliers(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": s.id, "name": s.name, "phone": s.phone, "gstin": s.gstin}
            for s in db.query(Supplier).all()]

@app.post("/api/suppliers")
def add_supplier(d: SupIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    s = Supplier(**d.model_dump()); db.add(s); audit(db, u, "create", "supplier", "", d.name)
    db.commit(); return {"id": s.id}

class POIn(BaseModel):
    supplier_id: int
    lines: List[dict]     # [{ingredient_id, qty, rate}]

@app.get("/api/purchases")
def purchases(db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": p.id, "po_no": p.po_no, "supplier_id": p.supplier_id, "status": p.status,
             "total": p.total, "created_at": p.created_at.isoformat()}
            for p in db.query(PurchaseOrder).order_by(PurchaseOrder.id.desc()).limit(200)]

@app.post("/api/purchases")
def create_po(d: POIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    total = sum(float(l["qty"]) * float(l["rate"]) for l in d.lines)
    seq = (db.query(func.count(PurchaseOrder.id)).scalar() or 0) + 1
    po = PurchaseOrder(po_no=f"PO{datetime.utcnow():%Y%m%d}{seq:04d}", supplier_id=d.supplier_id,
                       total=round(total, 2), status="draft")
    db.add(po); db.flush()
    for l in d.lines:
        db.add(POLine(po_id=po.id, ingredient_id=int(l["ingredient_id"]),
                      qty=float(l["qty"]), rate=float(l["rate"])))
    audit(db, u, "create", "purchase_order", po.id, po.po_no); db.commit()
    return {"id": po.id, "po_no": po.po_no, "total": po.total}

@app.post("/api/purchases/{pid}/receive")
def receive_po(pid: int, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    po = db.get(PurchaseOrder, pid)
    if not po: raise HTTPException(404, "PO not found")
    if po.status == "received": raise HTTPException(400, "Already received")
    for l in po.lines:
        ing = db.get(Ingredient, l.ingredient_id)
        if ing:
            ing.stock_qty += l.qty
            ing.cost_per_unit = l.rate or ing.cost_per_unit   # refresh cost
            db.add(StockMove(ingredient_id=ing.id, qty_change=l.qty, reason=f"PO {po.po_no}"))
    po.status = "received"
    audit(db, u, "receive", "purchase_order", pid, po.po_no); db.commit()
    return {"ok": True}

# ---------------- kitchen (KOT) ----------------
@app.get("/api/kitchen")
def kitchen_board(db: Session = Depends(get_db), u: User = Depends(current_user)):
    tickets = db.query(KitchenTicket).filter(KitchenTicket.status != "served")\
        .order_by(KitchenTicket.created_at).limit(100).all()
    out = []
    for t in tickets:
        o = db.get(Order, t.order_id)
        out.append({"id": t.id, "ticket_no": t.ticket_no, "status": t.status,
                    "order_no": o.order_no if o else "", "created_at": t.created_at.isoformat(),
                    "items": [{"name": i.dish_name, "qty": i.qty} for i in (o.items if o else [])]})
    return out

class KOTStatus(BaseModel):
    status: str

@app.post("/api/kitchen/{kid}/status")
def kot_status(kid: int, d: KOTStatus, db: Session = Depends(get_db), u: User = Depends(current_user)):
    t = db.get(KitchenTicket, kid)
    if not t: raise HTTPException(404, "Ticket not found")
    t.status = d.status; audit(db, u, "kot", "ticket", kid, d.status); db.commit()
    return {"ok": True}

# ---------------- billing ----------------
class OrderLineIn(BaseModel):
    dish_id: Optional[int] = None
    combo_id: Optional[int] = None
    qty: int = Field(default=1, gt=0)

class PaymentIn(BaseModel):
    mode: str = "cash"
    amount: float

class OrderIn(BaseModel):
    items: List[OrderLineIn]
    discount_pct: float = 0
    discount_flat: float = 0
    offer_code: str = ""
    customer_phone: str = ""
    redeem_points: int = 0
    payments: List[PaymentIn] = []
    payment_mode: str = "cash"
    channel: str = "dine-in"
    table_id: Optional[int] = None
    outlet_id: Optional[int] = None
    client_uuid: str = ""


def _next_order_no(db) -> str:
    """Next bill number for today, safe against gaps caused by splits/voids."""
    prefix = "B" + datetime.utcnow().strftime("%Y%m%d")
    rows = db.query(Order.order_no).filter(Order.order_no.like(prefix + "%")).all()
    mx = 0
    for (no,) in rows:
        try:
            mx = max(mx, int(no[len(prefix):]))
        except Exception:
            pass
    return f"{prefix}{mx + 1:04d}"

def _dish_cost(d: Dish) -> float:
    return sum(l.qty * (l.ingredient.cost_per_unit if l.ingredient else 0) for l in d.lines) * (1 + WASTE)

@app.post("/api/orders")
def create_order(o: OrderIn, request: Request, db: Session = Depends(get_db), u: User = Depends(current_user)):
    if not o.items: raise HTTPException(400, "No items")
    if o.client_uuid:
        prior = db.query(Order).filter(Order.client_uuid == o.client_uuid).first()
        if prior:
            return {"order_no": prior.order_no, "gross": prior.gross, "discount": prior.discount,
                    "offer_discount": prior.offer_discount, "subtotal": prior.subtotal,
                    "tax": prior.tax, "total": prior.total, "cogs": prior.cogs,
                    "points_earned": prior.points_earned, "customer_points": 0,
                    "duplicate": True}
    gross = 0.0; cogs = 0.0; rows = []; drawdown = {}
    for ln in o.items:
        if ln.combo_id:
            c = db.get(Combo, ln.combo_id)
            if not c or not c.active: raise HTTPException(400, "Combo unavailable")
            line_total = c.price * ln.qty
            line_cogs = 0.0
            for ci in c.items:
                d = db.get(Dish, ci.dish_id)
                if d:
                    line_cogs += _dish_cost(d) * ci.qty * ln.qty
                    for rl in d.lines:
                        drawdown[rl.ingredient_id] = drawdown.get(rl.ingredient_id, 0) + rl.qty * ci.qty * ln.qty
            gross += line_total; cogs += line_cogs
            rows.append((None, f"Combo: {c.name}", ln.qty, c.price, line_total, line_cogs, True))
        else:
            d = db.get(Dish, ln.dish_id) if ln.dish_id else None
            if not d or not d.active: raise HTTPException(400, f"Dish {ln.dish_id} unavailable")
            line_total = d.price * ln.qty; line_cogs = _dish_cost(d) * ln.qty
            gross += line_total; cogs += line_cogs
            for rl in d.lines:
                drawdown[rl.ingredient_id] = drawdown.get(rl.ingredient_id, 0) + rl.qty * ln.qty
            rows.append((d, d.name_en, ln.qty, d.price, line_total, line_cogs, False))

    # offer
    offer_disc = 0.0
    if o.offer_code:
        of = db.query(Offer).filter(Offer.code == o.offer_code, Offer.active == True).first()
        if not of: raise HTTPException(400, "Invalid offer code")
        if gross >= of.min_amount:
            offer_disc = gross * of.value / 100 if of.kind == "percent" else of.value
    manual_disc = gross * (o.discount_pct / 100.0) + o.discount_flat

    # loyalty
    cust = None; redeem_value = 0
    if o.customer_phone:
        cust = db.query(Customer).filter(Customer.phone == o.customer_phone).first()
        if not cust:
            cust = Customer(name="", phone=o.customer_phone); db.add(cust); db.flush()
        if o.redeem_points > 0:
            use = min(o.redeem_points, cust.points)
            redeem_value = use * POINT_VALUE
            cust.points -= use

    discount = min(manual_disc + offer_disc + redeem_value, gross)
    net_incl = gross - discount
    subtotal = net_incl / (1 + GST); tax = net_incl - subtotal

    points_earned = int(net_incl // 100) * POINTS_PER_100 if cust else 0
    if cust: cust.points += points_earned

    order = Order(order_no=_next_order_no(db), user_id=u.id, cashier=u.name or u.username,
                  outlet_id=o.outlet_id or u.outlet_id, table_id=o.table_id, channel=o.channel,
                  customer_id=cust.id if cust else None,
                  gross=round(gross, 2), combo_discount=0, offer_discount=round(offer_disc, 2),
                  discount=round(discount, 2), subtotal=round(subtotal, 2), tax=round(tax, 2),
                  total=round(net_incl, 2), cogs=round(cogs, 2),
                  points_earned=points_earned, points_redeemed=(o.redeem_points if cust else 0),
                  payment_mode=(o.payments[0].mode if o.payments else o.payment_mode), status="paid",
                  client_uuid=(o.client_uuid or None))
    db.add(order); db.flush()

    for d, name, qty, price, lt, lc, is_combo in rows:
        db.add(OrderItem(order_id=order.id, dish_id=(d.id if d else None), dish_name=name, qty=qty,
                         unit_price=round(price, 2), line_total=round(lt, 2),
                         line_cogs=round(lc, 2), is_combo=is_combo))
    for iid, used in drawdown.items():
        ing = db.get(Ingredient, iid)
        if ing:
            ing.stock_qty -= used
            db.add(StockMove(ingredient_id=iid, qty_change=-used, reason=f"order {order.order_no}"))

    # split payments
    pays = o.payments or [PaymentIn(mode=o.payment_mode, amount=net_incl)]
    psum = sum(p.amount for p in pays)
    if abs(psum - net_incl) > 0.5:
        raise HTTPException(400, f"Payments ({psum:.2f}) must equal total ({net_incl:.2f})")
    for p in pays:
        db.add(Payment(order_id=order.id, mode=p.mode, amount=round(p.amount, 2)))

    # kitchen ticket
    db.add(KitchenTicket(order_id=order.id, ticket_no=order.order_no.replace("B", "K"),
                         status="pending"))

    # table occupied
    if o.table_id:
        t = db.get(TableT, o.table_id)
        if t: t.status = "occupied"

    audit(db, u, "sale", "order", order.id, f"{order.order_no} ₹{order.total}",
          request.client.host if request.client else "")
    db.commit(); db.refresh(order)
    return {"id": order.id, "order_no": order.order_no, "gross": order.gross, "discount": order.discount,
            "offer_discount": order.offer_discount, "subtotal": order.subtotal, "tax": order.tax,
            "total": order.total, "cogs": order.cogs, "points_earned": order.points_earned,
            "customer_points": (cust.points if cust else 0)}

@app.get("/api/orders")
def list_orders(d: Optional[str] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(Order).options(joinedload(Order.items)).order_by(Order.created_at.desc())
    if d: q = q.filter(func.date(Order.created_at) == d)
    return [{"id": o.id, "order_no": o.order_no, "created_at": o.created_at.isoformat(), "cashier": o.cashier,
             "channel": o.channel, "total": o.total, "tax": o.tax, "discount": o.discount,
             "cogs": o.cogs, "payment_mode": o.payment_mode, "status": o.status,
             "items": [{"id": i.id, "name": i.dish_name, "qty": i.qty, "unit_price": i.unit_price,
                        "line_total": i.line_total} for i in o.items]} for o in q.limit(200)]

@app.post("/api/orders/{a}/merge/{b}")
def merge_orders(a: int, b: int, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    oa, ob = db.get(Order, a), db.get(Order, b)
    if not oa or not ob: raise HTTPException(404, "Order not found")
    for it in ob.items:
        it.order_id = oa.id
    oa.gross += ob.gross; oa.total += ob.total; oa.cogs += ob.cogs
    ob.status = "cancelled"; ob.merged_into = oa.id
    audit(db, u, "merge", "order", oa.id, f"{ob.order_no} -> {oa.order_no}")
    db.commit(); return {"ok": True, "order_no": oa.order_no, "total": round(oa.total, 2)}

# ---------------- reports ----------------
@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), u: User = Depends(current_user)):
    today = date.today()
    orders = db.query(Order).filter(func.date(Order.created_at) == today, Order.status == "paid").all()
    rev = sum(o.subtotal for o in orders); cogs = sum(o.cogs for o in orders)
    return {"date": today.isoformat(), "orders": len(orders),
            "units": int(sum(i.qty for o in orders for i in o.items)),
            "revenue_ex_gst": round(rev, 2), "gst_collected": round(sum(o.tax for o in orders), 2),
            "collected": round(sum(o.total for o in orders), 2), "cogs": round(cogs, 2),
            "gross_profit": round(rev - cogs, 2),
            "gross_margin": round((rev - cogs) / rev, 4) if rev else 0}

@app.get("/api/reports/items")
def report_items(start: Optional[str] = None, end: Optional[str] = None,
                 db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(OrderItem.dish_name, func.sum(OrderItem.qty), func.sum(OrderItem.line_total),
                 func.sum(OrderItem.line_cogs)).join(Order).filter(Order.status == "paid").group_by(OrderItem.dish_name)
    if start: q = q.filter(func.date(Order.created_at) >= start)
    if end: q = q.filter(func.date(Order.created_at) <= end)
    rows = [{"dish": r[0], "units": int(r[1] or 0), "revenue": round(r[2] or 0, 2),
             "cogs": round(r[3] or 0, 2), "profit": round((r[2] or 0) - (r[3] or 0), 2)} for r in q.all()]
    rows.sort(key=lambda x: -x["units"])
    for i, r in enumerate(rows): r["rank"] = i + 1
    return rows

@app.get("/api/reports/daily")
def report_daily(days: int = 14, db: Session = Depends(get_db), u: User = Depends(current_user)):
    since = date.today() - timedelta(days=days - 1)
    rows = db.query(func.date(Order.created_at), func.count(Order.id), func.sum(Order.total),
                    func.sum(Order.subtotal), func.sum(Order.cogs)).filter(
                    func.date(Order.created_at) >= since, Order.status == "paid"
                    ).group_by(func.date(Order.created_at)).all()
    return [{"date": str(r[0]), "orders": int(r[1]), "collected": round(r[2] or 0, 2),
             "revenue_ex_gst": round(r[3] or 0, 2), "cogs": round(r[4] or 0, 2)} for r in rows]

def _month_orders(db, month):
    if str(engine.url).startswith("sqlite"):
        return db.query(Order).filter(func.strftime("%Y-%m", Order.created_at) == month,
                                      Order.status == "paid").all()
    return db.query(Order).filter(func.to_char(Order.created_at, "YYYY-MM") == month,
                                  Order.status == "paid").all()

@app.get("/api/reports/pnl")
def report_pnl(month: Optional[str] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    month = month or date.today().strftime("%Y-%m")
    orders = _month_orders(db, month)
    rev = sum(o.subtotal for o in orders); cogs = sum(o.cogs for o in orders)
    oh = sum(x.amount for x in db.query(Overhead).filter(Overhead.month == month).all())
    sal = sum(x.amount for x in db.query(Salary).filter(Salary.month == month).all())
    return {"month": month, "orders": len(orders), "revenue": round(rev, 2), "cogs": round(cogs, 2),
            "gross_profit": round(rev - cogs, 2), "overheads": round(oh, 2), "salaries": round(sal, 2),
            "net_profit": round(rev - cogs - oh - sal, 2),
            "net_margin": round((rev - cogs - oh - sal) / rev, 4) if rev else 0}

@app.get("/api/reports/lowstock")
def low_stock(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = db.query(Ingredient).filter(Ingredient.stock_qty < Ingredient.reorder_level * 1.5).all()
    return [{"code": i.code, "name": i.name_en, "stock": round(i.stock_qty, 1),
             "reorder": round(i.reorder_level, 1), "unit": i.unit} for i in rows]

@app.get("/api/reports/gst")
def gst_export(month: Optional[str] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """GSTR-1 style B2C summary by HSN / rate. CSV download."""
    month = month or date.today().strftime("%Y-%m")
    orders = _month_orders(db, month)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["GSTR-1 B2C Summary", month])
    w.writerow(["Order No", "Date", "HSN", "Taxable Value", "GST Rate", "CGST", "SGST", "Invoice Total"])
    total_taxable = total_tax = 0.0
    for o in orders:
        taxable = o.subtotal; tax = o.tax
        total_taxable += taxable; total_tax += tax
        w.writerow([o.order_no, o.created_at.strftime("%d-%m-%Y"), "9963",
                    f"{taxable:.2f}", "5%", f"{tax/2:.2f}", f"{tax/2:.2f}", f"{o.total:.2f}"])
    w.writerow([]); w.writerow(["TOTAL", "", "", f"{total_taxable:.2f}", "", f"{total_tax/2:.2f}",
                                f"{total_tax/2:.2f}", f"{total_taxable+total_tax:.2f}"])
    buf.seek(0)
    audit(db, u, "export", "gst", month); db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="gstr1-{month}.csv"'})

# ---------------- audit ----------------
@app.get("/api/audit")
def get_audit(limit: int = 200, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"at": r.created_at.isoformat(), "user": r.username, "action": r.action,
             "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail, "ip": r.ip}
            for r in rows]

# ---------------- aggregator intake (Swiggy / Zomato) ----------------
class AggItem(BaseModel):
    dish_name: str
    qty: int

class AggOrder(BaseModel):
    channel: str = "swiggy"
    external_id: str = ""
    items: List[AggItem]

@app.post("/api/integrations/order")
def aggregator_order(d: AggOrder, request: Request, db: Session = Depends(get_db)):
    """Webhook endpoint for Swiggy/Zomato middleware. Protect with X-AGG-TOKEN."""
    if request.headers.get("X-AGG-TOKEN", "") != AGG_TOKEN:
        raise HTTPException(401, "Bad aggregator token")
    resolved = []
    for it in d.items:
        dish = db.query(Dish).filter(Dish.name_en == it.dish_name).first()
        if dish: resolved.append(OrderLineIn(dish_id=dish.id, qty=it.qty))
    if not resolved: raise HTTPException(400, "No matching dishes")
    u = db.query(User).filter(User.role == "owner").first()
    out = create_order(OrderIn(items=resolved, channel=d.channel, payment_mode="online"),
                       request, db, u)
    audit(db, u, "aggregator", d.channel, d.external_id, out["order_no"]); db.commit()
    return out

# ---------------- overheads / salaries / users ----------------
class OHIn(BaseModel):
    name: str; type: str = "Fixed"; amount: float; month: str

@app.get("/api/overheads")
def get_oh(month: Optional[str] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(Overhead)
    if month: q = q.filter(Overhead.month == month)
    return [{"id": x.id, "name": x.name, "type": x.type, "amount": x.amount, "month": x.month} for x in q.all()]

@app.post("/api/overheads")
def add_oh(d: OHIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = Overhead(**d.model_dump()); db.add(o); db.commit(); return {"id": o.id}

@app.delete("/api/overheads/{oid}")
def del_oh(oid: int, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    o = db.get(Overhead, oid)
    if o: db.delete(o); db.commit()
    return {"ok": True}

class SalIn(BaseModel):
    name: str; role: str = ""; amount: float; month: str

@app.get("/api/salaries")
def get_sal(month: Optional[str] = None, db: Session = Depends(get_db), u: User = Depends(current_user)):
    q = db.query(Salary)
    if month: q = q.filter(Salary.month == month)
    return [{"id": x.id, "name": x.name, "role": x.role, "amount": x.amount, "month": x.month} for x in q.all()]

@app.post("/api/salaries")
def add_sal(d: SalIn, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    s = Salary(**d.model_dump()); db.add(s); db.commit(); return {"id": s.id}

@app.delete("/api/salaries/{sid}")
def del_sal(sid: int, db: Session = Depends(get_db), u: User = Depends(require("owner", "manager"))):
    s = db.get(Salary, sid)
    if s: db.delete(s); db.commit()
    return {"ok": True}

class UserIn(BaseModel):
    username: str; password: str; name: str = ""; role: str = "cashier"; outlet_id: Optional[int] = None

@app.get("/api/users")
def list_users(db: Session = Depends(get_db), u: User = Depends(require("owner"))):
    return [{"id": x.id, "username": x.username, "name": x.name, "role": x.role, "active": x.active}
            for x in db.query(User).all()]

@app.post("/api/users")
def add_user(d: UserIn, db: Session = Depends(get_db), u: User = Depends(require("owner"))):
    if db.query(User).filter(User.username == d.username).first():
        raise HTTPException(400, "Username already exists")
    x = User(username=d.username, name=d.name, role=d.role, outlet_id=d.outlet_id,
             password_hash=hash_password(d.password))
    db.add(x); audit(db, u, "create", "user", "", d.username); db.commit(); return {"id": x.id}

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0", "time": datetime.utcnow().isoformat()}

# ==================== V3: thermal printing ====================
PRINTER_HOST = os.getenv("PRINTER_HOST", "")
PRINTER_PORT = int(os.getenv("PRINTER_PORT", "9100"))

def _send_to_printer(data: bytes):
    """Send raw ESC/POS bytes to a network printer. Returns (ok, message)."""
    if not PRINTER_HOST:
        return False, "No PRINTER_HOST configured"
    import socket
    try:
        with socket.create_connection((PRINTER_HOST, PRINTER_PORT), timeout=3) as sk:
            sk.sendall(data)
        return True, f"sent {len(data)} bytes to {PRINTER_HOST}:{PRINTER_PORT}"
    except Exception as e:
        return False, str(e)

def _outlet_name(db, outlet_id):
    o = db.get(Outlet, outlet_id) if outlet_id else None
    return (o.name if o else "CAFE"), (o.address if o else ""), (o.gstin if o else "")

@app.get("/api/print/bill/{order_no}")
def print_bill(order_no: str, send: int = 0, width: int = 42,
               db: Session = Depends(get_db), u: User = Depends(current_user)):
    o = db.query(Order).options(joinedload(Order.items)).filter(Order.order_no == order_no).first()
    if not o:
        raise HTTPException(404, "Order not found")
    name, addr, gstin = _outlet_name(db, o.outlet_id)
    data = escpos.bill_receipt(o, o.items, name, addr, gstin, width=width)
    if send:
        ok, msg = _send_to_printer(data)
        audit(db, u, "print", "bill", o.id, msg)
        db.commit()
        return {"sent": ok, "message": msg, "bytes": len(data)}
    return StreamingResponse(iter([data]), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{order_no}.escpos"'})

@app.get("/api/print/kot/{ticket_id}")
def print_kot(ticket_id: int, send: int = 0, width: int = 42,
              db: Session = Depends(get_db), u: User = Depends(current_user)):
    t = db.get(KitchenTicket, ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    o = db.query(Order).options(joinedload(Order.items)).filter(Order.id == t.order_id).first()
    data = escpos.kot_ticket(t, o, o.items if o else [], width=width)
    t.printed_at = datetime.utcnow()
    if send:
        ok, msg = _send_to_printer(data)
        audit(db, u, "print", "kot", t.id, msg)
        db.commit()
        return {"sent": ok, "message": msg, "bytes": len(data)}
    db.commit()
    return StreamingResponse(iter([data]), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="kot-{ticket_id}.escpos"'})

@app.get("/api/print/test")
def print_test(send: int = 0, db: Session = Depends(get_db),
               u: User = Depends(require("owner", "manager"))):
    data = (escpos.init() + escpos.align(1) + escpos.bold(True)
            + escpos._t("CAFE POS\nTEST PRINT\n") + escpos.bold(False)
            + escpos._t("42-column check\n1234567890123456789012345678901234567890\n")
            + escpos.feed(3) + escpos.cut())
    if send:
        ok, msg = _send_to_printer(data)
        return {"sent": ok, "message": msg}
    return {"bytes": len(data),
            "printer": f"{PRINTER_HOST}:{PRINTER_PORT}" if PRINTER_HOST else "not configured"}

# ==================== V3: split bill by item ====================
class SplitIn(BaseModel):
    groups: List[List[int]]      # groups of order_item ids; group 0 stays on the original bill

def _recompute(o, disc_ratio: float):
    o.gross = round(sum(i.line_total for i in o.items), 2)
    o.cogs = round(sum(i.line_cogs for i in o.items), 2)
    o.discount = round(o.gross * disc_ratio, 2)
    net = o.gross - o.discount
    o.subtotal = round(net / (1 + GST), 2)
    o.tax = round(net - o.subtotal, 2)
    o.total = round(net, 2)

@app.post("/api/orders/{oid}/split")
def split_order(oid: int, d: SplitIn, db: Session = Depends(get_db),
                u: User = Depends(require("owner", "manager", "cashier"))):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Order not found")
    if not d.groups or len(d.groups) < 2:
        raise HTTPException(400, "Give at least two groups")
    items = {i.id: i for i in o.items}
    flat = [x for g in d.groups for x in g]
    if len(set(flat)) != len(flat):
        raise HTTPException(400, "An item appears in more than one group")
    if any(i not in items for i in flat):
        raise HTTPException(400, "Unknown item id for this order")
    orig_gross = sum(i.line_total for i in o.items)
    ratio = (o.discount / orig_gross) if orig_gross else 0.0
    keep0 = set(d.groups[0])
    new_orders = []
    for gi, group in enumerate(d.groups[1:], start=1):
        child = Order(order_no=_next_order_no(db), user_id=u.id,
                      cashier=u.name or u.username, outlet_id=o.outlet_id, table_id=o.table_id,
                      customer_id=o.customer_id, channel=o.channel, payment_mode=o.payment_mode,
                      status="open")
        db.add(child)
        db.flush()
        for iid in group:
            items[iid].order_id = child.id
        db.flush()
        db.refresh(child)
        _recompute(child, ratio)
        new_orders.append(child.order_no)
    for it in list(o.items):
        if it.id not in keep0 and it.order_id == o.id:
            db.delete(it)
    db.flush()
    db.refresh(o)
    _recompute(o, ratio)
    audit(db, u, "split", "order", oid, f"{len(d.groups)} ways -> {new_orders}")
    db.commit()
    return {"original": {"order_no": o.order_no, "total": o.total}, "new_bills": new_orders}

# ==================== V3: stock take & wastage ====================
class StockTakeIn(BaseModel):
    lines: List[dict]        # [{ingredient_id, counted_qty}]

@app.post("/api/stocktake")
def stock_take(d: StockTakeIn, db: Session = Depends(get_db),
               u: User = Depends(require("owner", "manager"))):
    results = []
    for l in d.lines:
        ing = db.get(Ingredient, int(l["ingredient_id"]))
        if not ing:
            continue
        counted = float(l["counted_qty"])
        variance = counted - ing.stock_qty
        ing.stock_qty = counted
        db.add(StockMove(ingredient_id=ing.id, qty_change=round(variance, 3), reason="stocktake"))
        results.append({"ingredient": ing.name_en, "variance": round(variance, 3)})
    audit(db, u, "stocktake", "inventory", "", f"{len(results)} lines")
    db.commit()
    return {"lines": results}

class WastageIn(BaseModel):
    ingredient_id: int
    qty: float
    reason: str = "spoilage"

@app.post("/api/wastage")
def record_wastage(d: WastageIn, db: Session = Depends(get_db),
                   u: User = Depends(current_user)):
    ing = db.get(Ingredient, d.ingredient_id)
    if not ing:
        raise HTTPException(404, "Ingredient not found")
    if d.qty <= 0:
        raise HTTPException(400, "Quantity must be positive")
    ing.stock_qty -= d.qty
    db.add(StockMove(ingredient_id=ing.id, qty_change=-d.qty, reason=f"wastage: {d.reason}"))
    audit(db, u, "wastage", "ingredient", ing.id, f"{d.qty} {d.reason}")
    db.commit()
    return {"ok": True, "stock_qty": ing.stock_qty}

# ==================== V3: offline sync ====================
class SyncIn(BaseModel):
    orders: List[dict]

@app.post("/api/sync/orders")
def sync_orders(d: SyncIn, request: Request, db: Session = Depends(get_db),
                u: User = Depends(current_user)):
    """Accept bills captured offline. Each carries a client_uuid so re-sending is safe."""
    results = []
    for od in d.orders:
        cu = od.get("client_uuid", "")
        if cu and db.query(Order).filter(Order.client_uuid == cu).first():
            results.append({"client_uuid": cu, "status": "duplicate"})
            continue
        try:
            fields = {k: v for k, v in od.items() if k in OrderIn.model_fields}
            fields["client_uuid"] = cu
            out = create_order(OrderIn(**fields), request, db, u)
            results.append({"client_uuid": cu, "status": "accepted", "order_no": out["order_no"]})
        except Exception as e:
            results.append({"client_uuid": cu, "status": "rejected", "error": str(e)[:200]})
    return {"results": results}

# ==================== V3: void & refund ====================
class VoidIn(BaseModel):
    reason: str = ""

@app.post("/api/orders/{oid}/void")
def void_order(oid: int, d: VoidIn, db: Session = Depends(get_db),
               u: User = Depends(require("owner", "manager"))):
    o = db.query(Order).options(joinedload(Order.items)).filter(Order.id == oid).first()
    if not o:
        raise HTTPException(404, "Order not found")
    if o.status == "cancelled":
        raise HTTPException(400, "Already void")
    restored = 0
    for it in o.items:
        if it.is_combo or not it.dish_id:
            continue
        dish = db.get(Dish, it.dish_id)
        if not dish:
            continue
        for rl in dish.lines:
            ing = db.get(Ingredient, rl.ingredient_id)
            if ing:
                back = rl.qty * it.qty
                ing.stock_qty += back
                db.add(StockMove(ingredient_id=ing.id, qty_change=back, reason=f"void {o.order_no}"))
                restored += 1
    if o.customer_id:
        c = db.get(Customer, o.customer_id)
        if c and o.points_earned:
            c.points = max(0, c.points - o.points_earned)
    o.status = "cancelled"
    audit(db, u, "void", "order", oid, d.reason)
    db.commit()
    return {"ok": True, "restored_ingredient_lines": restored}

class RefundIn(BaseModel):
    amount: float
    reason: str = ""

@app.post("/api/orders/{oid}/refund")
def refund_order(oid: int, d: RefundIn, db: Session = Depends(get_db),
                 u: User = Depends(require("owner", "manager"))):
    o = db.get(Order, oid)
    if not o:
        raise HTTPException(404, "Order not found")
    if d.amount <= 0 or d.amount > o.total + 0.01:
        raise HTTPException(400, "Refund must be between 0 and the bill total")
    db.add(Refund(order_id=o.id, amount=round(d.amount, 2), reason=d.reason, approved_by=u.username))
    if abs(d.amount - o.total) < 0.01:
        o.status = "refunded"
    audit(db, u, "refund", "order", oid, f"{d.amount} {d.reason}")
    db.commit()
    return {"ok": True, "refunded": d.amount, "status": o.status}

@app.get("/api/orders/{oid}/refunds")
def list_refunds(oid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    return [{"id": r.id, "amount": r.amount, "reason": r.reason, "by": r.approved_by,
             "at": r.created_at.isoformat()}
            for r in db.query(Refund).filter(Refund.order_id == oid).all()]

# ---------------- static ----------------
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
