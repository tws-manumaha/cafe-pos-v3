from datetime import datetime
from sqlalchemy import (Column, Integer, String, Float, Boolean, DateTime,
                        ForeignKey, Text, UniqueConstraint)
from sqlalchemy.orm import relationship
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(120), default="")
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="cashier")   # owner | manager | cashier | kitchen
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Outlet(Base):
    __tablename__ = "outlets"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    address = Column(String(255), default="")
    phone = Column(String(40), default="")
    gstin = Column(String(20), default="")
    active = Column(Boolean, default=True)

class TableT(Base):
    __tablename__ = "tables"
    id = Column(Integer, primary_key=True)
    outlet_id = Column(Integer, ForeignKey("outlets.id"), index=True)
    name = Column(String(40))
    seats = Column(Integer, default=2)
    status = Column(String(16), default="free")   # free | occupied | reserved

class Ingredient(Base):
    __tablename__ = "ingredients"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True)
    name_en = Column(String(160), nullable=False)
    name_mr = Column(String(200), default="")
    category = Column(String(60), default="")
    unit = Column(String(8), default="g")
    cost_per_unit = Column(Float, default=0)
    stock_qty = Column(Float, default=0)
    reorder_level = Column(Float, default=0)
    shelf_days = Column(Integer, default=0)
    storage = Column(String(20), default="")

class Dish(Base):
    __tablename__ = "dishes"
    id = Column(Integer, primary_key=True)
    name_en = Column(String(160), nullable=False)
    name_mr = Column(String(200), default="")
    category = Column(String(60), default="")
    diet = Column(String(12), default="Veg")
    price = Column(Float, default=0)
    hsn = Column(String(8), default="9963")
    active = Column(Boolean, default=True)
    lines = relationship("RecipeLine", back_populates="dish", cascade="all, delete-orphan")

class RecipeLine(Base):
    __tablename__ = "recipe_lines"
    id = Column(Integer, primary_key=True)
    dish_id = Column(Integer, ForeignKey("dishes.id"), index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), index=True)
    qty = Column(Float, default=0)
    dish = relationship("Dish", back_populates="lines")
    ingredient = relationship("Ingredient")

# ---------- combos & offers ----------
class Combo(Base):
    __tablename__ = "combos"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    price = Column(Float, default=0)          # combo price incl GST
    active = Column(Boolean, default=True)
    items = relationship("ComboItem", cascade="all, delete-orphan")

class ComboItem(Base):
    __tablename__ = "combo_items"
    id = Column(Integer, primary_key=True)
    combo_id = Column(Integer, ForeignKey("combos.id"), index=True)
    dish_id = Column(Integer, ForeignKey("dishes.id"))
    qty = Column(Integer, default=1)

class Offer(Base):
    __tablename__ = "offers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    code = Column(String(24), default="")     # optional coupon code
    kind = Column(String(12), default="percent")   # percent | flat
    value = Column(Float, default=0)
    min_amount = Column(Float, default=0)
    starts = Column(String(10), default="")   # YYYY-MM-DD
    ends = Column(String(10), default="")
    active = Column(Boolean, default=True)

# ---------- customers / loyalty ----------
class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), default="")
    phone = Column(String(20), unique=True, index=True)
    points = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# ---------- suppliers / purchase orders ----------
class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(40), default="")
    email = Column(String(120), default="")
    gstin = Column(String(20), default="")
    address = Column(String(255), default="")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    po_no = Column(String(24), unique=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=True)
    status = Column(String(16), default="draft")   # draft | received | cancelled
    total = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    lines = relationship("POLine", cascade="all, delete-orphan")

class POLine(Base):
    __tablename__ = "po_lines"
    id = Column(Integer, primary_key=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"))
    qty = Column(Float, default=0)
    rate = Column(Float, default=0)            # rupees per base unit

# ---------- orders ----------
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_no = Column(String(24), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    cashier = Column(String(120), default="")
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=True, index=True)
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    channel = Column(String(16), default="dine-in")   # dine-in|takeaway|swiggy|zomato
    gross = Column(Float, default=0)
    combo_discount = Column(Float, default=0)
    offer_discount = Column(Float, default=0)
    discount = Column(Float, default=0)        # total discount
    subtotal = Column(Float, default=0)        # ex-GST
    tax = Column(Float, default=0)
    total = Column(Float, default=0)
    cogs = Column(Float, default=0)
    points_earned = Column(Integer, default=0)
    points_redeemed = Column(Integer, default=0)
    payment_mode = Column(String(16), default="cash")
    status = Column(String(16), default="paid")   # open | paid | cancelled | refunded
    client_uuid = Column(String(64), unique=True, nullable=True, index=True)  # offline idempotency
    merged_into = Column(Integer, nullable=True)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    dish_id = Column(Integer, ForeignKey("dishes.id"), nullable=True)
    dish_name = Column(String(160))
    qty = Column(Integer, default=1)
    unit_price = Column(Float, default=0)
    line_total = Column(Float, default=0)
    line_cogs = Column(Float, default=0)
    is_combo = Column(Boolean, default=False)
    order = relationship("Order", back_populates="items")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    mode = Column(String(16), default="cash")
    amount = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# ---------- kitchen ----------
class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    ticket_no = Column(String(24), index=True)
    station = Column(String(40), default="kitchen")
    status = Column(String(16), default="pending")  # pending|preparing|ready|served
    created_at = Column(DateTime, default=datetime.utcnow)
    printed_at = Column(DateTime, nullable=True)

# ---------- overheads / salaries / stock / audit ----------
class Overhead(Base):
    __tablename__ = "overheads"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    type = Column(String(20), default="Fixed")
    amount = Column(Float, default=0)
    month = Column(String(7))
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=True)

class Salary(Base):
    __tablename__ = "salaries"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    role = Column(String(80))
    amount = Column(Float, default=0)
    month = Column(String(7))
    outlet_id = Column(Integer, ForeignKey("outlets.id"), nullable=True)

class StockMove(Base):
    __tablename__ = "stock_moves"
    id = Column(Integer, primary_key=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), index=True)
    qty_change = Column(Float, default=0)
    reason = Column(String(80), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    username = Column(String(64), default="")
    action = Column(String(40), default="")
    entity = Column(String(40), default="")
    entity_id = Column(String(32), default="")
    detail = Column(Text, default="")
    ip = Column(String(45), default="")

class Refund(Base):
    __tablename__ = "refunds"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    amount = Column(Float, default=0)
    reason = Column(String(200), default="")
    approved_by = Column(String(120), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
