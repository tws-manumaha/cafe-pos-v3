"""Minimal ESC/POS builder for 80mm (42-col) and 58mm (32-col) thermal printers.

Produces raw bytes that can be sent straight to a printer on TCP :9100,
a USB device, or saved to a file for testing.  Text is ASCII/Latin only —
Devanagari needs a printer with a font chip, so bills use English names.
"""
from datetime import datetime

ESC = b"\x1b"
GS = b"\x1d"

def init():            return ESC + b"@"
def align(n: int):     return ESC + b"a" + bytes([n])      # 0=L 1=C 2=R
def bold(on: bool):    return ESC + b"E" + bytes([1 if on else 0])
def double(on: bool):  return GS + b"!" + bytes([0x11 if on else 0x00])
def feed(n: int = 1):  return ESC + b"d" + bytes([n])
def cut():             return GS + b"V" + bytes([66, 0])

def _t(s: str) -> bytes:
    return str(s).encode("latin-1", "replace")

def rule(width=42, ch="-"): return _t(ch * width + "\n")

def row(left: str, right: str, width=42) -> bytes:
    right = str(right)
    left = str(left)
    space = max(1, width - len(left) - len(right))
    return _t(left + " " * space + right + "\n")

def _money(v) -> str:
    return f"{float(v or 0):,.2f}"

def bill_receipt(order, items, outlet_name="CAFE", address="", gstin="", width=42) -> bytes:
    b = bytearray()
    b += init()
    b += align(1) + bold(True) + double(True) + _t((outlet_name or "CAFE") + "\n") + double(False) + bold(False)
    if address:
        b += align(1) + _t(address[:width] + "\n")
    if gstin:
        b += align(1) + _t(f"GSTIN: {gstin}\n")
    b += align(0) + rule(width)
    b += _t(f"Bill : {order.order_no}\n")
    b += _t(f"Date : {order.created_at:%d-%m-%Y %H:%M}\n")
    b += _t(f"By   : {order.cashier}\n")
    b += _t(f"Type : {order.channel}\n")
    b += rule(width)
    b += row("Item", "Amount", width)
    b += rule(width)
    for it in items:
        nm = str(it.dish_name)[: max(10, width - 14)]
        b += _t(f"{nm}\n")
        b += row(f"  {it.qty} x {_money(it.unit_price)}", _money(it.line_total), width)
    b += rule(width)
    b += row("Gross", _money(order.gross), width)
    if order.discount:
        b += row("Discount", "-" + _money(order.discount), width)
    b += row("Taxable", _money(order.subtotal), width)
    b += row("GST 5%", _money(order.tax), width)
    b += rule(width)
    b += bold(True) + double(True) + row("TOTAL", _money(order.total), width) + double(False) + bold(False)
    b += rule(width)
    b += _t(f"Paid by: {order.payment_mode}\n")
    if getattr(order, "points_earned", 0):
        b += _t(f"Points earned: {order.points_earned}\n")
    b += align(1) + _t("\nThank you! Visit again.\n")
    b += feed(3) + cut()
    return bytes(b)

def kot_ticket(ticket, order, items, width=42) -> bytes:
    b = bytearray()
    b += init()
    b += align(1) + bold(True) + double(True) + _t("KITCHEN ORDER\n") + double(False) + bold(False)
    b += align(0) + rule(width)
    b += bold(True) + _t(f"KOT  : {ticket.ticket_no}\n") + bold(False)
    b += _t(f"Bill : {order.order_no}\n")
    b += _t(f"Time : {ticket.created_at:%d-%m-%Y %H:%M}\n")
    b += _t(f"Type : {order.channel}\n")
    b += rule(width)
    for it in items:
        b += bold(True) + double(True) + _t(f"{it.qty} x {str(it.dish_name)[:width-8]}\n") + double(False) + bold(False)
    b += rule(width)
    b += align(1) + _t("-- prepare --\n")
    b += feed(3) + cut()
    return bytes(b)
