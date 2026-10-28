const $ = s => document.querySelector(s);
const money = n => '₹' + Number(n || 0).toLocaleString('en-IN', {maximumFractionDigits: 2});
let TOKEN = localStorage.getItem('cafe_token') || '';
let ME = null, DISHES = [], INGREDIENTS = [], COMBOS = [], CART = {};

async function api(path, opts = {}) {
  const h = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  if (TOKEN) h['Authorization'] = 'Bearer ' + TOKEN;
  const r = await fetch(path, Object.assign({}, opts, { headers: h }));
  if (r.status === 401) { logout(); throw new Error('Session expired'); }
  if (opts.raw) return r;
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || ('HTTP ' + r.status));
  return body;
}
async function doLogin() {
  $('#loginErr').textContent = '';
  try {
    const r = await api('/api/auth/login', { method: 'POST',
      body: JSON.stringify({ username: $('#u').value.trim(), password: $('#p').value }) });
    TOKEN = r.token; localStorage.setItem('cafe_token', TOKEN); startApp();
  } catch (e) { $('#loginErr').textContent = e.message; }
}
function logout() {
  TOKEN = ''; localStorage.removeItem('cafe_token');
  $('#app').classList.add('hidden'); $('#login').classList.remove('hidden');
}
async function startApp() {
  try { ME = await api('/api/auth/me'); } catch { return; }
  $('#login').classList.add('hidden'); $('#app').classList.remove('hidden');
  $('#whoName').textContent = (ME.name || ME.username) + ' · ' + ME.role;
  await Promise.all([loadDishes(), loadIngredients(), loadCombos()]);
  show('dashboard');
}
function show(v) {
  document.querySelectorAll('main > section').forEach(s => s.classList.add('hidden'));
  $('#v-' + v).classList.remove('hidden');
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('active', b.dataset.v === v));
  ({dashboard:loadDashboard, billing:renderDishes, kitchen:loadKitchen, tables:loadTables,
    orders:loadOrders, inventory:renderInventory, purchases:loadPurchases, menu:renderMenu,
    marketing:loadMarketing, reports:loadReports, admin:loadAdmin, stock:loadStock}[v] || (()=>{}))();
}
async function loadDishes() {
  DISHES = await api('/api/dishes');
  const cats = [...new Set(DISHES.map(d => d.category))].sort();
  $('#catFilter').innerHTML = '<option value="">All categories</option>' + cats.map(c => `<option>${c}</option>`).join('');
}
async function loadIngredients() { INGREDIENTS = await api('/api/ingredients'); }
async function loadCombos() { COMBOS = await api('/api/combos'); }

/* dashboard */
async function loadDashboard() {
  const d = await api('/api/dashboard');
  $('#kpis').innerHTML = [['Orders today', d.orders], ['Items sold', d.units],
    ['Revenue (ex-GST)', money(d.revenue_ex_gst)], ['GST collected', money(d.gst_collected)],
    ['Collected', money(d.collected)], ['Food cost', money(d.cogs)],
    ['Gross profit', money(d.gross_profit)], ['Gross margin', (d.gross_margin*100).toFixed(1)+'%']]
    .map(([l,v]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
  const low = await api('/api/reports/lowstock');
  $('#lowStock').innerHTML = `<thead><tr><th>Ingredient</th><th class="num">Stock</th><th class="num">Reorder at</th><th>Status</th></tr></thead><tbody>` +
    (low.length ? low.map(i => `<tr><td>${i.name}</td><td class="num">${i.stock} ${i.unit}</td><td class="num">${i.reorder} ${i.unit}</td><td>${badge(i.stock,i.reorder)}</td></tr>`).join('')
      : '<tr><td colspan="4" class="muted">All good.</td></tr>') + '</tbody>';
}
function badge(s, r) {
  if (s <= 0) return '<span class="badge b-out">Out</span>';
  if (s < r) return '<span class="badge b-reorder">Reorder</span>';
  if (s < r*1.5) return '<span class="badge b-low">Low</span>';
  return '<span class="badge b-ok">OK</span>';
}

/* billing */
function renderDishes() {
  const q = ($('#search').value||'').toLowerCase(), cat = $('#catFilter').value;
  const list = DISHES.filter(d => d.active && (!cat || d.category===cat) &&
    (!q || d.name_en.toLowerCase().includes(q) || (d.name_mr||'').includes(q)));
  $('#dishCount').textContent = list.length + ' dishes';
  $('#dishGrid').innerHTML = list.map(d => `<div class="dish" onclick="add('d${d.id}')">
      <div class="n">${d.name_en}</div><div class="m">${d.name_mr||''}</div>
      <div class="p">${money(d.price)} <span class="badge ${d.diet==='Veg'?'b-veg':'b-nv'}">${d.diet}</span></div></div>`).join('');
  $('#comboRow').innerHTML = COMBOS.filter(c=>c.active).map(c =>
    `<button class="dish" style="padding:8px 12px" onclick="add('c${c.id}')">
       <b>${c.name}</b> · ${money(c.price)}</button>`).join('');
}
function add(key) { CART[key] = (CART[key]||0)+1; renderCart(); }
function setQty(key, d) { CART[key]=(CART[key]||0)+d; if(CART[key]<=0) delete CART[key]; renderCart(); }
function cartTotals() {
  let gross = 0;
  for (const k in CART) {
    const id = k.slice(1);
    const p = k[0]==='d' ? (DISHES.find(x=>x.id==id)||{}).price : (COMBOS.find(x=>x.id==id)||{}).price;
    gross += (p||0)*CART[k];
  }
  const pct = Number($('#discPct').value||0), disc = gross*pct/100;
  const net = gross-disc, sub = net/1.05, tax = net-sub;
  return {gross, disc, net, tax};
}
function renderCart() {
  const keys = Object.keys(CART);
  if (!keys.length) { $('#cartLines').innerHTML='<p class="muted">No items yet — tap a dish.</p>'; $('#cartTotals').innerHTML=''; return; }
  $('#cartLines').innerHTML = keys.map(k => {
    const id = k.slice(1);
    const o = k[0]==='d' ? DISHES.find(x=>x.id==id) : COMBOS.find(x=>x.id==id);
    const nm = k[0]==='d' ? o.name_en : '🎁 '+o.name;
    return `<div class="row"><span>${nm}</span><span>
      <button class="qbtn" onclick="setQty('${k}',-1)">−</button> ${CART[k]}
      <button class="qbtn" onclick="setQty('${k}',1)">+</button>
      <b>${money(o.price*CART[k])}</b></span></div>`;
  }).join('');
  const t = cartTotals();
  $('#cartTotals').innerHTML = `<div class="row"><span>Subtotal</span><span>${money(t.gross)}</span></div>
    ${t.disc?`<div class="row"><span>Discount</span><span>−${money(t.disc)}</span></div>`:''}
    <div class="row"><span>GST 5%</span><span>${money(t.tax)}</span></div>
    <div class="row"><span><b>Total</b></span><span><b>${money(t.net)}</b></span></div>`;
}
async function charge() {
  const items = Object.keys(CART).map(k => k[0]==='d'
    ? {dish_id:Number(k.slice(1)), qty:CART[k]} : {combo_id:Number(k.slice(1)), qty:CART[k]});
  if (!items.length) return alert('Add at least one item.');
  const lines = Object.keys(CART).map(k => {
    const id=k.slice(1);
    const o = k[0]==='d'?DISHES.find(x=>x.id==id):COMBOS.find(x=>x.id==id);
    return {name:o.name_en||o.name, qty:CART[k], price:o.price};
  });
  try {
    const o = await api('/api/orders', {method:'POST', body: JSON.stringify({
      items, discount_pct:Number($('#discPct').value||0),
      offer_code:$('#offerCode').value.trim(), customer_phone:$('#custPhone').value.trim(),
      channel:$('#channel').value})});
    printReceipt(o, lines);
    CART={}; $('#discPct').value=''; $('#offerCode').value=''; $('#custPhone').value='';
    renderCart(); await loadIngredients(); loadDashboard();
  } catch(e) {
    if (String(e.message).includes('Failed to fetch') || String(e.message).includes('NetworkError')) {
      const q = JSON.parse(localStorage.getItem('offline_orders') || '[]');
      q.push({ uuid: 'c-' + Date.now() + '-' + Math.random().toString(36).slice(2,8), payload: { items, discount_pct:Number($('#discPct').value||0),
        offer_code:$('#offerCode').value.trim(), customer_phone:$('#custPhone').value.trim(),
        channel:$('#channel').value }, lines, at: Date.now() });
      localStorage.setItem('offline_orders', JSON.stringify(q));
      CART={}; renderCart();
      alert('Offline — bill saved on this device and will sync when the network returns.');
    } else { alert('Could not charge: '+e.message); }
  }
}

/* offline queue: push bills captured while the network was down */
async function flushQueue() {
  const q = JSON.parse(localStorage.getItem('offline_orders') || '[]');
  if (!q.length) return;
  const left = [];
  for (const item of q) {
    try {
      item.payload.client_uuid = item.uuid;
      await api('/api/sync/orders', { method:'POST', body: JSON.stringify({ orders: [item.payload] }) });
    } catch (e) { if (String(e.message).includes('Failed to fetch')) { left.push(item); } }
  }
  localStorage.setItem('offline_orders', JSON.stringify(left));
  if (q.length !== left.length) { loadDashboard(); loadKitchen(); }
}
function printReceipt(o, lines) {
  const rows = lines.map(l=>`<div class="r"><span>${l.name} × ${l.qty}</span><span>${money(l.price*l.qty)}</span></div>`).join('');
  const w = window.open('','_blank','width=380,height=640');
  w.document.write(`<html><head><title>${o.order_no}</title></head><body onload="window.print()">
  <div class="receipt"><h4>CAFE</h4><div style="text-align:center;font-size:11px">Bill ${o.order_no}</div>
  <div class="line"></div>${rows}<div class="line"></div>
  <div class="r"><span>Gross</span><span>${money(o.gross)}</span></div>
  ${o.offer_discount?`<div class="r"><span>Offer</span><span>−${money(o.offer_discount)}</span></div>`:''}
  <div class="r"><span>Discount</span><span>−${money(o.discount)}</span></div>
  <div class="r"><span>GST 5%</span><span>${money(o.tax)}</span></div><div class="line"></div>
  <div class="r"><b>Total</b><b>${money(o.total)}</b></div>
  ${o.points_earned?`<div style="text-align:center;font-size:11px">Points earned: ${o.points_earned}</div>`:''}
  <div class="line"></div><div style="text-align:center;font-size:11px">Thank you!</div></div></body></html>`);
  w.document.close();
}

/* kitchen */
async function loadKitchen() {
  const t = await api('/api/kitchen');
  $('#kotBoard').innerHTML = t.length ? t.map(k => `<div class="panel">
    <div style="display:flex;justify-content:space-between"><b>${k.ticket_no}</b>
    <span class="badge ${k.status==='pending'?'b-reorder':k.status==='preparing'?'b-low':'b-ok'}">${k.status}</span></div>
    <div class="muted" style="margin:6px 0">${new Date(k.created_at).toLocaleTimeString('en-IN')}</div>
    ${k.items.map(i=>`<div class="row"><span>${i.name}</span><b>×${i.qty}</b></div>`).join('')}
    <div style="display:flex;gap:6px;margin-top:8px">
      <button class="qbtn" onclick="kot(${k.id},'preparing')">Prep</button>
      <button class="qbtn" onclick="kot(${k.id},'ready')">Ready</button>
      <button class="qbtn" onclick="kot(${k.id},'served')">Served</button>
      <button class="qbtn" onclick="printKot(${k.id})">Print</button></div></div>`).join('')
    : '<p class="muted">No open tickets.</p>';
}
async function kot(id, st) { await api(`/api/kitchen/${id}/status`,{method:'POST',body:JSON.stringify({status:st})}); loadKitchen(); }

/* tables */
async function loadTables() {
  const t = await api('/api/tables');
  $('#tableGrid').innerHTML = t.map(x => `<div class="kpi" style="cursor:pointer;border-color:${x.status==='free'?'var(--line)':'var(--accent)'}"
    onclick="toggleTable(${x.id},'${x.status}')"><div class="l">${x.name}</div>
    <div class="v">${x.status==='free'?'Free':'Occupied'}</div>
    <div class="muted">${x.seats} seats</div></div>`).join('');
}
async function toggleTable(id, cur) {
  await api(`/api/tables/${id}`,{method:'PUT',body:JSON.stringify({status:cur==='free'?'occupied':'free'})});
  loadTables();
}

/* orders / inventory / menu */
async function loadOrders() {
  const d = $('#orderDate').value;
  const rows = await api('/api/orders' + (d?'?d='+d:''));
  $('#ordersTable').innerHTML = `<thead><tr><th>Bill</th><th>Time</th><th>Cashier</th><th>Channel</th>
    <th class="num">Total</th><th class="num">GST</th><th>Payment</th><th>Status</th><th>Actions</th></tr></thead><tbody>` +
    (rows.length?rows.map(o=>`<tr><td>${o.order_no}</td><td>${new Date(o.created_at).toLocaleString('en-IN')}</td>
      <td>${o.cashier}</td><td>${o.channel}</td><td class="num">${money(o.total)}</td>
      <td class="num">${money(o.tax)}</td><td>${o.payment_mode}</td><td>${o.status}</td>
      <td style="white-space:nowrap">
        <button class="qbtn" onclick="printBill('${o.order_no}')">Print</button>
        <button class="qbtn" onclick="splitBill(${o.id})">Split</button>
        <button class="qbtn" onclick="voidOrder(${o.id})">Void</button>
        <button class="qbtn" onclick="refundOrder(${o.id})">Refund</button>
      </td></tr>`).join('')
      :'<tr><td colspan="9" class="muted">No orders.</td></tr>')+'</tbody>';
}
function renderInventory() {
  const q = ($('#invSearch').value||'').toLowerCase();
  const list = INGREDIENTS.filter(i=>!q||i.name_en.toLowerCase().includes(q));
  $('#invTable').innerHTML = `<thead><tr><th>Code</th><th>Ingredient</th><th>Category</th>
    <th class="num">Stock</th><th class="num">Reorder</th><th>Status</th><th></th></tr></thead><tbody>` +
    list.slice(0,400).map(i=>`<tr><td>${i.code}</td><td>${i.name_en}<div class="muted">${i.name_mr||''}</div></td>
      <td>${i.category}</td><td class="num">${i.stock_qty.toFixed(1)} ${i.unit}</td>
      <td class="num">${i.reorder_level.toFixed(1)} ${i.unit}</td><td>${badge(i.stock_qty,i.reorder_level)}</td>
      <td><button class="qbtn" onclick="adjustStock(${i.id})">+ buy</button></td></tr>`).join('')+'</tbody>';
}
async function adjustStock(id) {
  const v = prompt('Quantity to add (base units):'); if (!v) return;
  await api(`/api/ingredients/${id}/stock`,{method:'POST',body:JSON.stringify({qty_change:Number(v),reason:'purchase'})});
  await loadIngredients(); renderInventory(); loadDashboard();
}
function renderMenu() {
  const q = ($('#menuSearch').value||'').toLowerCase();
  const list = DISHES.filter(d=>!q||d.name_en.toLowerCase().includes(q));
  $('#menuTable').innerHTML = `<thead><tr><th>Dish</th><th>Category</th><th>Diet</th>
    <th class="num">Cost</th><th class="num">Price</th><th class="num">Margin</th></tr></thead><tbody>` +
    list.map(d=>`<tr><td>${d.name_en}<div class="muted">${d.name_mr||''}</div></td><td>${d.category}</td>
      <td><span class="badge ${d.diet==='Veg'?'b-veg':'b-nv'}">${d.diet}</span></td>
      <td class="num">${money(d.cost)}</td><td class="num">${money(d.price)}</td>
      <td class="num">${(d.margin*100).toFixed(1)}%</td></tr>`).join('')+'</tbody>';
}

/* purchases */
async function loadPurchases() {
  const pos = await api('/api/purchases'), sups = await api('/api/suppliers');
  $('#poTable').innerHTML = `<thead><tr><th>PO</th><th class="num">Total</th><th>Status</th><th></th></tr></thead><tbody>` +
    (pos.length?pos.map(p=>`<tr><td>${p.po_no}</td><td class="num">${money(p.total)}</td><td>${p.status}</td>
      <td>${p.status==='draft'?`<button class="qbtn" onclick="recv(${p.id})">Receive</button>`:''}</td></tr>`).join('')
      :'<tr><td colspan="4" class="muted">No purchase orders.</td></tr>')+'</tbody>';
  $('#supTable').innerHTML = `<thead><tr><th>Supplier</th><th>Phone</th></tr></thead><tbody>` +
    sups.map(s=>`<tr><td>${s.name}</td><td>${s.phone||'—'}</td></tr>`).join('')+'</tbody>';
  $('#poSupplier').innerHTML = sups.map(s=>`<option value="${s.id}">${s.name}</option>`).join('');
}
async function recv(id) { await api(`/api/purchases/${id}/receive`,{method:'POST'}); loadPurchases(); await loadIngredients(); }
let PO_LINES = [];
async function newPO() { PO_LINES = []; renderPOEditor(); addPoLine(); }
function addPoLine() {
  PO_LINES.push({ ingredient_id: INGREDIENTS[0] ? INGREDIENTS[0].id : null, qty: 0, rate: 0 });
  renderPOEditor();
}
function renderPOEditor() {
  $('#poEditor tbody').innerHTML = PO_LINES.map((l, i) => `<tr>
    <td><select onchange="PO_LINES[${i}].ingredient_id=Number(this.value)">
      ${INGREDIENTS.map(ing => `<option value="${ing.id}" ${ing.id===l.ingredient_id?'selected':''}>${ing.code} — ${ing.name_en}</option>`).join('')}
    </select></td>
    <td><input type="number" value="${l.qty}" style="width:100px" oninput="PO_LINES[${i}].qty=Number(this.value);poTotals()"></td>
    <td><input type="number" step="0.001" value="${l.rate}" style="width:110px" oninput="PO_LINES[${i}].rate=Number(this.value);poTotals()"></td>
    <td><button class="qbtn" onclick="PO_LINES.splice(${i},1);renderPOEditor()">✕</button></td>
  </tr>`).join('');
  poTotals();
}
function poTotals() {
  const t = PO_LINES.reduce((a, l) => a + (l.qty || 0) * (l.rate || 0), 0);
  $('#poTotal').textContent = 'Total: ' + money(t);
}
async function submitPO() {
  const lines = PO_LINES.filter(l => l.ingredient_id && l.qty > 0);
  if (!lines.length) return alert('Add at least one line.');
  const sid = Number($('#poSupplier').value);
  if (!sid) return alert('No supplier selected.');
  try {
    const r = await api('/api/purchases', { method:'POST', body: JSON.stringify({ supplier_id: sid, lines }) });
    alert('Created ' + r.po_no + ' — total ' + money(r.total));
    PO_LINES = []; renderPOEditor(); loadPurchases();
  } catch (e) { alert('Failed: ' + e.message); }
}

/* stock take & wastage */
let ST_ROWS = [];
async function loadStock() {
  if (!INGREDIENTS.length) await loadIngredients();
  ST_ROWS = INGREDIENTS.slice(0, 60).map(i => ({ id: i.id, code: i.code, name: i.name_en,
    unit: i.unit, stock: i.stock_qty, counted: '' }));
  renderStockTake();
}
function renderStockTake() {
  const q = ($('#stSearch').value || '').toLowerCase();
  $('#stTable').innerHTML = `<thead><tr><th>Ingredient</th><th class="num">In system</th><th>Counted</th></tr></thead><tbody>` +
    ST_ROWS.filter(r => !q || r.name.toLowerCase().includes(q) || r.code.toLowerCase().includes(q))
      .map((r, i) => `<tr><td>${r.code} — ${r.name}</td><td class="num">${r.stock.toFixed(1)} ${r.unit}</td>
      <td><input type="number" style="width:110px" value="${r.counted}" oninput="ST_ROWS[${i}].counted=this.value"></td></tr>`).join('') +
    '</tbody>';
}
async function submitStockTake() {
  const lines = ST_ROWS.filter(r => r.counted !== '' && !isNaN(Number(r.counted)))
    .map(r => ({ ingredient_id: r.id, counted_qty: Number(r.counted) }));
  if (!lines.length) return alert('Enter at least one counted quantity.');
  const res = await api('/api/stocktake', { method:'POST', body: JSON.stringify({ lines }) });
  alert('Posted ' + res.lines.length + ' lines.');
  await loadIngredients(); loadStock();
}
async function submitWastage() {
  const code = $('#wIng').value.trim().toUpperCase();
  const ing = INGREDIENTS.find(i => i.code === code);
  if (!ing) return alert('Ingredient code not found.');
  const qty = Number($('#wQty').value || 0);
  if (qty <= 0) return alert('Enter a quantity.');
  await api('/api/wastage', { method:'POST', body: JSON.stringify({
    ingredient_id: ing.id, qty, reason: $('#wReason').value }) });
  alert('Recorded wastage of ' + qty + ' ' + ing.unit);
  $('#wQty').value = ''; await loadIngredients(); loadStock();
}

/* printing, split, void, refund */
function printBill(no) { window.open(`/api/print/bill/${no}?send=1`, '_blank'); }
function printKot(id) { window.open(`/api/print/kot/${id}?send=1`, '_blank'); }
async function splitBill(oid) {
  const orders = await api('/api/orders');
  const o = orders.find(x => x.id === oid);
  if (!o) return;
  const listing = o.items.map(i => `${i.id}: ${i.name} x${i.qty}`).join('\n');
  const raw = prompt('Split by item.\n' + listing + '\n\nEnter groups of item ids separated by | (first group stays on this bill):\nExample: 1,2|3');
  if (!raw) return;
  const groups = raw.split('|').map(g => g.split(',').map(x => Number(x.trim())).filter(Boolean));
  try {
    const r = await api(`/api/orders/${oid}/split`, { method:'POST', body: JSON.stringify({ groups }) });
    alert('Split done. New bills: ' + (r.new_bills.join(', ') || 'none'));
    loadOrders();
  } catch (e) { alert('Split failed: ' + e.message); }
}
async function voidOrder(oid) {
  const reason = prompt('Reason for voiding this bill?'); if (reason === null) return;
  try { await api(`/api/orders/${oid}/void`, { method:'POST', body: JSON.stringify({ reason }) });
        alert('Voided and stock restored.'); loadOrders(); loadDashboard(); }
  catch (e) { alert('Void failed: ' + e.message); }
}
async function refundOrder(oid) {
  const amt = prompt('Refund amount (₹):'); if (!amt) return;
  const reason = prompt('Reason?') || '';
  try { const r = await api(`/api/orders/${oid}/refund`, { method:'POST',
        body: JSON.stringify({ amount: Number(amt), reason }) });
        alert('Refunded ' + money(r.refunded) + ' — status: ' + r.status); loadOrders(); }
  catch (e) { alert('Refund failed: ' + e.message); }
}

/* marketing */
async function loadMarketing() {
  const offs = await api('/api/offers'), cbs = await api('/api/combos'), cust = await api('/api/customers');
  $('#offerTable').innerHTML = `<thead><tr><th>Name</th><th>Code</th><th class="num">Value</th><th>Min</th></tr></thead><tbody>` +
    offs.map(o=>`<tr><td>${o.name}</td><td>${o.code||'—'}</td>
      <td class="num">${o.kind==='percent'?o.value+'%':money(o.value)}</td><td>${money(o.min_amount)}</td></tr>`).join('')+'</tbody>';
  $('#comboTable').innerHTML = `<thead><tr><th>Combo</th><th class="num">Price</th><th class="num">Items</th></tr></thead><tbody>` +
    cbs.map(c=>`<tr><td>${c.name}</td><td class="num">${money(c.price)}</td><td class="num">${c.items.length}</td></tr>`).join('')+'</tbody>';
  $('#custTable').innerHTML = `<thead><tr><th>Phone</th><th>Name</th><th class="num">Points</th></tr></thead><tbody>` +
    (cust.length?cust.map(c=>`<tr><td>${c.phone}</td><td>${c.name||'—'}</td><td class="num">${c.points}</td></tr>`).join('')
      :'<tr><td colspan="3" class="muted">No customers yet.</td></tr>')+'</tbody>';
}
async function newOffer() {
  const name = prompt('Offer name:'); if (!name) return;
  const code = prompt('Code (blank for auto):')||'';
  const kind = (prompt('Type: percent or flat','percent')||'percent');
  const value = Number(prompt('Value (e.g. 10 for 10%):')||0);
  const min = Number(prompt('Minimum bill amount:')||0);
  await api('/api/offers',{method:'POST',body:JSON.stringify({name,code,kind,value,min_amount:min})});
  loadMarketing();
}

/* reports */
async function loadReports() {
  if (!$('#pnlMonth').value) $('#pnlMonth').value = new Date().toISOString().slice(0,7);
  loadPnl();
  const daily = await api('/api/reports/daily?days=14');
  $('#dailyTable').innerHTML = `<thead><tr><th>Date</th><th class="num">Orders</th><th class="num">Collected</th><th class="num">Food cost</th></tr></thead><tbody>` +
    (daily.length?daily.map(d=>`<tr><td>${d.date}</td><td class="num">${d.orders}</td>
      <td class="num">${money(d.collected)}</td><td class="num">${money(d.cogs)}</td></tr>`).join('')
      :'<tr><td colspan="4" class="muted">No sales.</td></tr>')+'</tbody>';
  const items = await api('/api/reports/items');
  $('#itemTable').innerHTML = `<thead><tr><th>#</th><th>Dish</th><th class="num">Units</th>
    <th class="num">Revenue</th><th class="num">Food cost</th><th class="num">Profit</th></tr></thead><tbody>` +
    (items.length?items.map(i=>`<tr><td>${i.rank}</td><td>${i.dish}</td><td class="num">${i.units}</td>
      <td class="num">${money(i.revenue)}</td><td class="num">${money(i.cogs)}</td>
      <td class="num">${money(i.profit)}</td></tr>`).join('')
      :'<tr><td colspan="6" class="muted">No sales.</td></tr>')+'</tbody>';
  try {
    const a = await api('/api/audit?limit=50');
    $('#auditTable').innerHTML = `<thead><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead><tbody>` +
      a.map(x=>`<tr><td>${new Date(x.at).toLocaleString('en-IN')}</td><td>${x.user}</td>
        <td>${x.action}</td><td>${x.entity}</td><td>${x.detail||''}</td></tr>`).join('')+'</tbody>';
  } catch { $('#auditTable').innerHTML = '<tbody><tr><td class="muted">Owner/manager only.</td></tr></tbody>'; }
}
async function loadPnl() {
  const m = $('#pnlMonth').value;
  const p = await api('/api/reports/pnl?month='+m);
  $('#pnlTable').innerHTML = `<tbody>
    <tr><td>Revenue (ex-GST)</td><td class="num">${money(p.revenue)}</td></tr>
    <tr><td>Food cost (COGS)</td><td class="num">−${money(p.cogs)}</td></tr>
    <tr><td><b>Gross profit</b></td><td class="num"><b>${money(p.gross_profit)}</b></td></tr>
    <tr><td>Overheads</td><td class="num">−${money(p.overheads)}</td></tr>
    <tr><td>Salaries</td><td class="num">−${money(p.salaries)}</td></tr>
    <tr><td><b>Net profit</b></td><td class="num"><b style="color:${p.net_profit>=0?'var(--green)':'var(--red)'}">${money(p.net_profit)}</b></td></tr>
    <tr><td>Net margin</td><td class="num">${(p.net_margin*100).toFixed(1)}%</td></tr></tbody>`;
}
async function downloadGst() {
  const m = $('#pnlMonth').value || new Date().toISOString().slice(0,7);
  const r = await api('/api/reports/gst?month='+m, {raw:true});
  const blob = await r.blob(), a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = `gstr1-${m}.csv`; a.click();
}

/* admin */
async function loadAdmin() {
  if (!$('#adminMonth').value) $('#adminMonth').value = new Date().toISOString().slice(0,7);
  const m = $('#adminMonth').value;
  const oh = await api('/api/overheads?month='+m);
  $('#ohTable').innerHTML = `<thead><tr><th>Head</th><th class="num">Amount</th><th></th></tr></thead><tbody>` +
    (oh.length?oh.map(o=>`<tr><td>${o.name}</td><td class="num">${money(o.amount)}</td>
      <td><button class="qbtn" onclick="delOh(${o.id})">✕</button></td></tr>`).join('')
      :'<tr><td colspan="3" class="muted">None.</td></tr>')+'</tbody>';
  const sal = await api('/api/salaries?month='+m);
  $('#salTable').innerHTML = `<thead><tr><th>Name</th><th>Role</th><th class="num">Amount</th><th></th></tr></thead><tbody>` +
    (sal.length?sal.map(s=>`<tr><td>${s.name}</td><td>${s.role}</td><td class="num">${money(s.amount)}</td>
      <td><button class="qbtn" onclick="delSal(${s.id})">✕</button></td></tr>`).join('')
      :'<tr><td colspan="4" class="muted">None.</td></tr>')+'</tbody>';
  try {
    const users = await api('/api/users');
    $('#userTable').innerHTML = `<thead><tr><th>Username</th><th>Name</th><th>Role</th></tr></thead><tbody>` +
      users.map(u=>`<tr><td>${u.username}</td><td>${u.name}</td><td>${u.role}</td></tr>`).join('')+'</tbody>';
  } catch { $('#userTable').innerHTML = '<tbody><tr><td class="muted">Owner only.</td></tr></tbody>'; }
}
async function delOh(id){await api('/api/overheads/'+id,{method:'DELETE'});loadAdmin();}
async function delSal(id){await api('/api/salaries/'+id,{method:'DELETE'});loadAdmin();}
async function seedAdminDefaults() {
  const m = $('#adminMonth').value;
  if ((await api('/api/overheads?month='+m)).length) return alert('This month already has overheads.');
  const std=[["Rent",40000],["Manager salary",25000],["Head cook",20000],["Kitchen helper x2",30000],
    ["Service staff x2",28000],["Cleaner",12000],["Electricity",28306],["Water",3000],["LPG / gas",6000],
    ["Internet & phone",2000],["POS software",1500],["Marketing",8000],["Repairs",4000],["Licenses",2000],
    ["Insurance",1500],["Cleaning consumables",3000],["Depreciation",5000],["Miscellaneous",5000]];
  for (const [n,a] of std) await api('/api/overheads',{method:'POST',body:JSON.stringify({name:n,type:'Fixed',amount:a,month:m})});
  loadAdmin();
}

document.querySelectorAll('#nav button').forEach(b => b.onclick = () => show(b.dataset.v));
$('#p').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
function updateOfflineBar() {
  const n = JSON.parse(localStorage.getItem('offline_orders') || '[]').length;
  const bar = document.getElementById('offlineBar');
  if (!bar) return;
  if (!navigator.onLine || n > 0) {
    bar.classList.remove('hidden');
    bar.textContent = navigator.onLine ? `Syncing ${n} offline bill(s)…` : `OFFLINE — ${n} bill(s) queued`;
  } else { bar.classList.add('hidden'); }
}
window.addEventListener('offline', updateOfflineBar);
window.addEventListener('online', () => { updateOfflineBar(); flushQueue(); });
if (TOKEN) { startApp(); flushQueue(); }
