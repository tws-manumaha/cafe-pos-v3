"""Seed the database from data/app_data.json (exported from the Excel workbook)."""
import json, os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import Base, engine, SessionLocal
from app.models import (User, Outlet, TableT, Ingredient, Dish, RecipeLine,
                        Combo, ComboItem, Offer, Supplier, Overhead, Salary)
from app.security import hash_password

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UNITS_PER_DISH = 28
LEAD_DAYS = 2

def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Dish).count() > 0:
            print("Already seeded — skipping. (Delete cafe.db to reseed.)")
            return
        data = json.load(open(os.path.join(BASE, "data", "app_data.json"), encoding="utf-8"))

        outlet = Outlet(name="Main Outlet", address="", phone="", gstin="")
        db.add(outlet); db.flush()

        for uname, pwd, name, role in [("owner", "owner123", "Owner", "owner"),
                                       ("manager", "manager123", "Manager", "manager"),
                                       ("cashier", "cashier123", "Counter 1", "cashier"),
                                       ("kitchen", "kitchen123", "Kitchen", "kitchen")]:
            db.add(User(username=uname, name=name, role=role, outlet_id=outlet.id,
                        password_hash=hash_password(pwd)))

        for i in range(1, 9):
            db.add(TableT(outlet_id=outlet.id, name=f"T{i}", seats=4 if i <= 6 else 2))

        idx = {}
        for ing in data["ingredients"]:
            o = Ingredient(code=ing["c"], name_en=ing["en"], name_mr=ing["mr"], category=ing["cat"],
                           unit=ing["u"], cost_per_unit=ing["cost"], shelf_days=ing["shelf"],
                           storage=ing["store"])
            db.add(o); db.flush(); idx[ing["c"]] = o.id

        dish_ids = {}
        for d in data["dishes"]:
            dish = Dish(name_en=d["en"], name_mr=d["mr"], category=d["cat"], diet=d["diet"],
                        price=d["price"], active=True)
            db.add(dish); db.flush(); dish_ids[d["en"]] = dish.id
            for code, qty in d["ing"]:
                if code in idx:
                    db.add(RecipeLine(dish_id=dish.id, ingredient_id=idx[code], qty=qty))
        db.commit()

        usage = {}
        for d in data["dishes"]:
            for code, qty in d["ing"]:
                usage[code] = usage.get(code, 0) + qty * DEFAULT_UNITS_PER_DISH
        for ing in db.query(Ingredient).all():
            daily = usage.get(ing.code, 0) / 30.0
            reorder = max(1.0, daily * LEAD_DAYS * 1.2)
            ing.reorder_level = round(reorder, 1)
            ing.stock_qty = round(reorder * 4, 1)
        db.commit()

        # demo combo + offer
        combo = Combo(name="Fries + Cola Combo", price=99.0)
        db.add(combo); db.flush()
        for nm, q in [("Salted Fries", 1), ("Cold Coffee (Classic)", 1)]:
            if nm in dish_ids:
                db.add(ComboItem(combo_id=combo.id, dish_id=dish_ids[nm], qty=q))
        db.add(Offer(name="10% off over ₹500", code="SAVE10", kind="percent", value=10,
                     min_amount=500, active=True))
        db.add(Offer(name="Happy Hour ₹50 off", code="HAPPY50", kind="flat", value=50,
                     min_amount=300, active=True))

        for nm in ["Fresh Farms Dairy", "Metro Wholesale", "City Bakery Supply"]:
            db.add(Supplier(name=nm, phone="", gstin=""))

        m = date.today().strftime("%Y-%m")
        oh = [("Rent","Fixed",40000),("Manager salary","Fixed",25000),("Head cook","Fixed",20000),
              ("Kitchen helper x2","Fixed",30000),("Service staff x2","Fixed",28000),
              ("Cleaner","Fixed",12000),("Electricity","Variable",28306),("Water","Variable",3000),
              ("LPG / gas","Variable",6000),("Internet & phone","Fixed",2000),
              ("POS software","Fixed",1500),("Marketing","Variable",8000),("Repairs","Variable",4000),
              ("Licenses","Fixed",2000),("Insurance","Fixed",1500),
              ("Cleaning consumables","Variable",3000),("Depreciation","Fixed",5000),
              ("Miscellaneous","Variable",5000)]
        for n, t, a in oh:
            db.add(Overhead(name=n, type=t, amount=a, month=m, outlet_id=outlet.id))
        for n, r, a in [("Owner","Owner",0),("Manager","Manager",25000),("Head cook","Chef",20000),
                        ("Helper 1","Kitchen",15000),("Helper 2","Kitchen",15000),
                        ("Server 1","Service",14000),("Server 2","Service",14000),
                        ("Cleaner","Cleaning",12000)]:
            db.add(Salary(name=n, role=r, amount=a, month=m, outlet_id=outlet.id))
        db.commit()
        print(f"Seeded: {db.query(Ingredient).count()} ingredients, {db.query(Dish).count()} dishes, "
              f"{db.query(RecipeLine).count()} recipe lines, {db.query(TableT).count()} tables, "
              f"{db.query(Supplier).count()} suppliers, {db.query(Combo).count()} combo, "
              f"{db.query(Offer).count()} offers.")
    finally:
        db.close()

if __name__ == "__main__":
    run()
