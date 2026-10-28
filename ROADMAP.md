# Roadmap

## Shipped

### v2 — core platform
Billing with GST split, discounts and split payments · combos and offers ·
KOT and kitchen board · table layout · inventory with stock draw-down ·
suppliers and purchase orders · loyalty points · multi-outlet model ·
GSTR-1 CSV export · audit log · aggregator intake webhook · roles.

### v3 — this release

| Item | Status |
|---|---|
| Thermal printer integration (ESC/POS) for bill and KOT | ✅ Done |
| Split bill by item | ✅ Done |
| Purchase-order line editor UI | ✅ Done |
| Full offline sync with idempotent replay | ✅ Done |
| Stock take / wastage entry screen | ✅ Done |
| Refunds and voids with manager approval | ✅ Done |

## Next

**Near term**
- ESC/POS over USB / Bluetooth, not just network :9100
- Offline conflict resolution for stock and KOT state (not just bills)
- Split-bill by seat and equal-split modes
- Shift open/close with cash-drawer reconciliation
- Supplier price lists and PO approval workflow

**Medium term**
- Native Swiggy/Zomato partner API (needs partner credentials)
- Customer QR menu and self-order
- Multi-outlet consolidated reporting and stock transfer
- Attendance and payroll export
- Kitchen display on a second screen (websocket push)

**Longer term**
- GSTR-3B reconciliation helpers
- Loyalty tiers and campaigns
- Franchise / central-kitchen model
- Manager mobile app (PWA is the first step)
- Public API and outbound webhooks

## Known limitations

- ESC/POS output is Latin-1; Devanagari needs a printer font chip.
- Offline replay is idempotent per `client_uuid`, but stock/KOT changes made on
  the server while a till is offline are not reconciled automatically.
- Aggregator integration is a **contract** (token-protected webhook), not a
  direct Swiggy/Zomato partner integration.
- Multi-outlet is modelled in the data and on orders; the UI does not yet switch
  between outlets.
- Combos are priced bundles; "choose any 2 of N" is not supported yet.
- Void restores stock for regular dishes; combo line stock is not restored.
