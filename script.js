const API='/api/v1', state={products:[],locations:[],stock:[],alerts:[],suppliers:[],users:[],token:null,role:null,username:null,fullName:null};
const ROLE_LABELS={admin:'Admin / Owner',manager:'Manager',employee:'Employee',worker:'Worker'};
const AUTH_KEY='smartStoreAuth';
const ROLE_PERMISSIONS={
  admin:    {products:true, locations:true, stock:true,sales:true,transfers:true, suppliers:true, purchases:true, alerts:true, settings:true},
  manager:  {products:true, locations:true, stock:true,sales:true,transfers:true, suppliers:true, purchases:true, alerts:true, settings:true},
  employee: {products:false,locations:false,stock:true,sales:true,transfers:false,suppliers:false,purchases:false,alerts:true, settings:false},
  worker:   {products:false,locations:false,stock:false,sales:false,transfers:false,suppliers:false,purchases:false,alerts:false,settings:false},
};
const can=perm=>!!(ROLE_PERMISSIONS[state.role]||{})[perm];
const PAGE_ACCESS={
  dashboardPage: ['admin','manager','employee'],
  inventoryPage: ['admin','manager','employee'],
  salesPage:     ['admin','manager','employee'],
  warehousePage: ['admin','manager'],
  suppliersPage: ['admin','manager'],
  alertsPage:    ['admin','manager','employee'],
  analyticsPage: ['admin','manager'],
  reportsPage:   ['admin','manager'],
  settingsPage:  ['admin','manager'],
  workerPage:    ['worker'],
};
function applyRolePermissions(){
  const isWorker=state.role==='worker';
  // Show/hide main dashboard vs worker view
  const dash=$('#dashboardPage');
  const work=$('#workerPage');
  if(dash)dash.classList.toggle('hidden',isWorker);
  if(work)work.classList.toggle('hidden',!isWorker);
  $$('[data-permission]').forEach(el=>el.classList.toggle('hidden',!can(el.dataset.permission)));
  $$('[data-nav-page]').forEach(el=>{
    const allowed=(PAGE_ACCESS[el.dataset.navPage]||[]).includes(state.role);
    el.classList.toggle('hidden',!allowed);
  });
}
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const money=v=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(Number(v||0));
const compactMoney=v=>{v=Number(v||0);if(v>=100000)return '₹'+(v/100000).toFixed(1)+'L';if(v>=1000)return '₹'+(v/1000).toFixed(1)+'k';return '₹'+Math.round(v)};
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(state.token)headers['Authorization']='Bearer '+state.token;const r=await fetch(API+path,{headers,...options});const body=await r.json().catch(()=>({}));if(!r.ok){const err=Error(body.error||'Request failed.');err.status=r.status;throw err}return body}
function handleApiError(e){if(e.status===401){logout(true);return}notify(e.message,true)}
function notify(message,error=false){const t=$('#toast');t.textContent=message;t.className=`toast ${error?'error':''}`;clearTimeout(notify.timer);notify.timer=setTimeout(()=>t.classList.add('hidden'),3500)}
const ALL_PAGES=['dashboardPage','inventoryPage','salesPage','warehousePage','suppliersPage','alertsPage','analyticsPage','reportsPage','settingsPage','workerPage'];
function page(id){ALL_PAGES.forEach(x=>$('#'+x)?.classList.toggle('hidden',x!==id));$$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===id));scrollTo({top:0,behavior:'smooth'})}
function showHomeForRole(){if(state.role==='worker'){ALL_PAGES.forEach(x=>$('#'+x)?.classList.add('hidden'));$('#workerPage')?.classList.remove('hidden');renderWorkerView()}else{ALL_PAGES.forEach(x=>$('#'+x)?.classList.add('hidden'));$('#dashboardPage')?.classList.remove('hidden')}}
function grouped(){const m=new Map(state.products.map(product=>[product.id,{product,store:0,warehouse:0}]));state.stock.forEach(x=>{const row=m.get(x.product_id);if(row&&(x.location_type==='store'||x.location_type==='warehouse'))row[x.location_type]+=Number(x.quantity)||0});return [...m.values()]}
function renderInventory(){const q=($('#inventorySearch')?.value||'').toLowerCase(),cat=$('#categoryFilter')?.value||'All Categories',filter=$('#stockFilter')?.value||'All Status';const rows=grouped().filter(({product,store})=>{const status=store===0?'Out of Stock':store<=product.reorder_point?'Low Stock':'Normal';return(!q||`${product.name} ${product.sku} ${product.category||''}`.toLowerCase().includes(q))&&(cat==='All Categories'||cat===product.category)&&(filter==='All Status'||filter===status)});const host=$('#inventoryRows');if(!host)return;host.innerHTML=rows.length?rows.map(({product,store,warehouse})=>{const cls=store===0?'out':store<=product.reorder_point?'low':'normal',label=cls==='out'?'Out of Stock':cls==='low'?'Low Stock':'Normal';return `<div class="inv-row"><span>□</span><span class="prod">📦 ${esc(product.name)}</span><span>${esc(product.category||'—')}</span><span>${esc(product.sku)}</span><span>${store}</span><span>${warehouse}</span><span>${store+warehouse}</span><span>${money(product.sale_price)}</span><span class="badge ${cls}">${label}</span><span class="actions"><button data-stock="${product.id}">✎ Stock</button><button class="btn-price" data-priceid="${product.id}" data-curprice="${product.sale_price}">₹ Price</button></span></div>`}).join(''):'<div class="empty-state">No products yet. Add a location and product to begin.</div>';$('#inventoryCount').textContent=`Showing ${rows.length} of ${state.products.length} products`;$$('[data-stock]',host).forEach(b=>b.onclick=()=>stockForm(+b.dataset.stock));$$('[data-priceid]',host).forEach(b=>b.onclick=()=>priceForm(+b.dataset.priceid,+b.dataset.curprice))}
function renderWorkerView(){
  const wName=$('#workerUserName');if(wName)wName.textContent=state.fullName||state.username;
  const wRole=$('#workerRoleLabel');if(wRole)wRole.textContent=ROLE_LABELS[state.role]||state.role;
  const g=grouped();
  const storeItems=g.filter(x=>x.store>0||x.product.reorder_point>0);
  const whItems=g.filter(x=>x.warehouse>0);
  const storeHost=$('#workerStoreStock');
  const whHost=$('#workerWhStock');
  if(storeHost)storeHost.innerHTML=storeItems.length
    ?storeItems.map(x=>{const low=x.store<=x.product.reorder_point&&x.product.reorder_point>0;return`<div class="wk-row"><span>${esc(x.product.name)}</span><span>${esc(x.product.category||'—')}</span><strong class="${x.store===0?'danger':low?'warn':''}">${x.store}</strong><span class="badge ${x.store===0?'out':low?'low':'normal'}">${x.store===0?'Out of Stock':low?'Low':'OK'}</span></div>`}).join('')
    :'<div class="empty-state">No store stock data.</div>';
  if(whHost)whHost.innerHTML=whItems.length
    ?whItems.map(x=>`<div class="wk-row"><span>${esc(x.product.name)}</span><span>${esc(x.product.category||'—')}</span><strong>${x.warehouse}</strong><span class="badge normal">In Stock</span></div>`).join('')
    :'<div class="empty-state">No warehouse stock data.</div>';
  const lowCount=g.filter(x=>x.store>0&&x.store<=x.product.reorder_point&&x.product.reorder_point>0).length;
  const outCount=g.filter(x=>x.store===0).length;
  const wLow=$('#workerLowCount');if(wLow)wLow.textContent=lowCount;
  const wOut=$('#workerOutCount');if(wOut)wOut.textContent=outCount;
  const wTotal=$('#workerTotalProducts');if(wTotal)wTotal.textContent=g.length;
}
async function renderSalesPage(){
  try{
    const[trend7,best]=await Promise.all([
      api('/analytics/sales-trend?days=7'),
      api('/analytics/best-sellers'),
    ]);

    // Stats
    const today=trend7.items[trend7.items.length-1];
    const todayRev=today?today.total:0;
    const yesterday=trend7.items[trend7.items.length-2];
    const ystRev=yesterday?yesterday.total:0;
    const pct=ystRev>0?Math.round((todayRev-ystRev)/ystRev*100):0;
    const el=id=>$('#'+id);
    if(el('salesTodayStat'))el('salesTodayStat').textContent=money(todayRev);
    if(el('salesTodaySmall'))el('salesTodaySmall').innerHTML=pct>=0?`<span class="up">↑ ${Math.abs(pct)}% vs yesterday</span>`:`<span class="down">↓ ${Math.abs(pct)}% vs yesterday</span>`;

    // Transaction count & avg (last 7 days)
    const period7Rev=trend7.items.reduce((s,r)=>s+r.total,0);
    const txCount=trend7.items.reduce((s,r)=>s+(r.count||0),0);
    if(el('salesTxCount'))el('salesTxCount').textContent=txCount>0?txCount.toLocaleString('en-IN'):'—';
    if(el('salesAvgOrder'))el('salesAvgOrder').textContent=txCount>0?money(period7Rev/txCount):'—';

    // Top product
    if(best.items.length>0){
      const top=best.items[0];
      if(el('salesTopProduct'))el('salesTopProduct').textContent=top.name;
      if(el('salesTopUnits'))el('salesTopUnits').textContent=`${top.units_sold?.toLocaleString('en-IN')||'—'} units sold`;
    }

    // Bar chart
    renderSalesBarChart(trend7.items);

    // Category bars from stock data
    const g=grouped();
    const catSales={};
    best.items.forEach(p=>{
      const prod=state.products.find(x=>x.id===p.product_id);
      const cat=prod?.category||'Other';
      catSales[cat]=(catSales[cat]||0)+p.units_sold;
    });
    const totalUnits=Object.values(catSales).reduce((a,b)=>a+b,0)||1;
    const catHost=el('salesCategoryBars');
    if(catHost){
      const sorted=Object.entries(catSales).sort((a,b)=>b[1]-a[1]).slice(0,6);
      catHost.innerHTML=sorted.map(([cat,units])=>{
        const pct=Math.round(units/totalUnits*100);
        return`<p>${esc(cat)} <b>${pct}%</b><i style="width:${pct}%"></i></p>`;
      }).join('')||'<div class="empty-state">No sales data yet.</div>';
    }

    // Recent transactions
    const txHost=el('salesTxTable');
    if(txHost){
      const sales=state.sales||[];
      const recent=[...sales].sort((a,b)=>b.id-a.id).slice(0,20);
      if(recent.length===0){txHost.innerHTML='<div class="empty-state">No transactions recorded yet.</div>';return;}
      txHost.innerHTML=recent.map((s,i)=>{
        const prod=state.products.find(p=>p.id===s.product_id);
        const loc=state.locations.find(l=>l.id===s.location_id);
        const dateStr=s.created_at?s.created_at.substring(0,10):'—';
        const amt=money((s.quantity||0)*(s.unit_price||0));
        return`<div>INV-${String(s.id).padStart(4,'0')} | ${esc(prod?.name||'Unknown')} | ${s.quantity} | ${amt} | ${esc(loc?.name||'—')} | ${dateStr}</div>`;
      }).join('');
    }
  }catch(e){handleApiError(e)}
}

function renderSalesBarChart(items){
  const host=$('#salesBarChart');
  if(!host||!items||!items.length)return;
  const max=Math.max(...items.map(r=>r.total),1);
  host.innerHTML=items.map(r=>{
    const h=Math.max(4,Math.round((r.total/max)*100));
    const label=new Date(r.date+'T00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short'});
    return`<div title="${label}: ${money(r.total)}"><i style="height:${h}%"></i><small>${label.split(' ')[0]}</small></div>`;
  }).join('');
}

function id(x){return x}
// ── Alerts state ──────────────────────────────────────────────────────────────
let _alertFilter = 'all';       // tab: 'all' | 'low_stock' | 'out_of_stock' | 'critical'
let _alertSevFilter = new Set(); // severity checkboxes
let _alertStatus = 'open';       // 'open' | 'all'

function _alertTypeIcon(type){
  if(type==='out_of_stock') return '🚫';
  if(type==='low_stock')    return '〽️';
  if(type==='supplier')     return '🚚';
  return '🔔';
}
function _alertTypeLabel(type){
  if(type==='out_of_stock') return 'Out of Stock';
  if(type==='low_stock')    return 'Low Stock';
  if(type==='supplier')     return 'Supplier';
  return type||'Alert';
}
function _sevClass(sev){
  return {critical:'priority critical',high:'priority medium',warning:'priority low',info:'priority low'}[sev]||'priority low';
}
function _timeAgo(dtStr){
  if(!dtStr) return '—';
  const d=new Date(dtStr.includes('T')||dtStr.endsWith('Z')?dtStr:dtStr.replace(' ','T')+'Z');
  const diff=Date.now()-d.getTime();
  const m=Math.floor(diff/60000);
  if(m<1) return 'Just now';
  if(m<60) return `${m}m ago`;
  const h=Math.floor(m/60);
  if(h<24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
}

// ── Live Clock ────────────────────────────────────────────────────────────────
function startLiveClock(){
  const DAYS=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function tick(){
    const now=new Date();
    const dateEl=$('#liveDateStr');
    const timeEl=$('#liveTimeStr');
    if(dateEl) dateEl.textContent=`${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
    if(timeEl){
      const h=now.getHours(),m=String(now.getMinutes()).padStart(2,'0'),s=String(now.getSeconds()).padStart(2,'0');
      const ampm=h>=12?'PM':'AM';
      timeEl.textContent=`${h%12||12}:${m}:${s} ${ampm}`;
    }
    const name=$('#dashWelcomeName');
    if(name&&state.fullName) name.textContent=state.fullName.split(' ')[0];
  }
  tick();
  setInterval(tick,1000);
}

// ── Price Edit Form ───────────────────────────────────────────────────────────
function priceForm(productId, currentPrice){
  const prod=state.products.find(p=>p.id===productId);
  if(!prod) return notify('Product not found.',true);
  modal(
    `Edit Price — ${prod.name}`,
    `<div style="margin-bottom:14px">
       <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">Current Price</label>
       <div style="font-size:22px;font-weight:700;color:#2563eb;margin-bottom:16px">${money(currentPrice)}</div>
       <label style="display:block;font-size:13px;font-weight:600;margin-bottom:6px">New Sale Price (₹)</label>
       <input name="sale_price" type="number" min="0" step="0.01" value="${currentPrice}" 
              style="width:100%;height:42px;border:1px solid #d8e3ee;border-radius:8px;padding:0 12px;font-size:18px;font-weight:700">
       <label style="display:block;font-size:13px;font-weight:600;margin:14px 0 6px">Reorder Point</label>
       <input name="reorder_point" type="number" min="0" value="${prod.reorder_point}"
              style="width:100%;height:42px;border:1px solid #d8e3ee;border-radius:8px;padding:0 12px;font-size:15px">
     </div>`,
    'Update Price',
    async f=>{
      const newPrice=+(f.get('sale_price'));
      const newReorder=+(f.get('reorder_point'));
      if(!newPrice||newPrice<=0) throw new Error('Price must be greater than 0.');
      await api(`/products/${productId}`,{
        method:'POST',
        body:JSON.stringify({sale_price:newPrice,reorder_point:newReorder})
      });
      notify(`Price updated to ${money(newPrice)} ✓`);
      refresh();
    }
  );
}

// ── Supplier forms ────────────────────────────────────────────────────────────
function supplierForm(){
  modal('Add Supplier',
    `<label>Supplier Name *<input name="name" required placeholder="e.g. Metro Wholesale"></label>
     <label>Contact Person<input name="contact_name" placeholder="e.g. Ramesh Kumar"></label>
     <label>Email<input name="email" type="email" placeholder="supplier@example.com"></label>
     <label>Lead Time (days)<input name="lead_time_days" type="number" min="1" max="60" value="3"></label>`,
    'Add Supplier',
    async f=>{
      const d=Object.fromEntries(f);
      d.lead_time_days=+(d.lead_time_days||3);
      await api('/suppliers',{method:'POST',body:JSON.stringify(d)});
      notify('Supplier added successfully ✓');
      const sup=await api('/suppliers');
      state.suppliers=sup.items;
      renderSuppliers();
    }
  );
}

function purchaseForm(supplierId, supplierName){
  const stores=state.locations.filter(l=>l.location_type==='store');
  const warehouses=state.locations.filter(l=>l.location_type==='warehouse');
  const allLocs=[...stores,...warehouses];
  if(!state.products.length) return notify('No products found.',true);
  modal(`Create Purchase Order — ${supplierName}`,
    `<label>Product *<select name="product_id">${options(state.products)}</select></label>
     <label>Deliver to *<select name="destination_location_id">${options(allLocs)}</select></label>
     <label>Quantity *<input name="quantity" type="number" min="1" value="50" required></label>`,
    'Create Order',
    async f=>{
      const d=Object.fromEntries(f);
      d.supplier_id=supplierId;
      d.product_id=+(d.product_id);
      d.destination_location_id=+(d.destination_location_id);
      d.quantity=+(d.quantity);
      await api('/purchase-requests',{method:'POST',body:JSON.stringify(d)});
      notify('Purchase order created ✓');
      refresh();
    }
  );
}

async function deleteSupplier(id){
  if(!confirm('Remove this supplier?')) return;
  // No DELETE endpoint yet — notify coming soon
  notify('Supplier removal: Coming Soon in next update.',true);
}

// ── Warehouse page ────────────────────────────────────────────────────────────
function renderWarehouse(){
  const g=grouped();
  const whUnits=g.reduce((n,x)=>n+x.warehouse,0);
  const whValue=g.reduce((n,x)=>n+x.warehouse*x.product.sale_price,0);
  const locs=state.locations.filter(l=>l.location_type==='warehouse');
  const transfers=state.transfers||[];
  const pendingTx=transfers.filter(t=>t.status==='pending').length;

  // At-risk = store items below reorder that have warehouse stock available
  const atRisk=g.filter(x=>x.store<=x.product.reorder_point&&x.warehouse>0&&x.product.reorder_point>0);

  const set=(id,v)=>{const e=$('#'+id);if(e)e.textContent=v};
  set('whUnits',    whUnits.toLocaleString('en-IN'));
  set('whValue',    money(whValue));
  set('whPendingTx',pendingTx);
  set('whAtRisk',   atRisk.length);
  set('whLocLabel', `Across ${locs.length} warehouse${locs.length!==1?'s':''}`);
  set('whPendingLabel', pendingTx===1?'1 awaiting completion':`${pendingTx} awaiting completion`);

  // Transfer table
  const txHost=$('#transferTable');
  if(txHost){
    if(!transfers.length){
      txHost.innerHTML='<div class="empty-state">No transfers recorded yet. Use the button above to create one.</div>';
    } else {
      txHost.innerHTML=transfers.slice(0,20).map(t=>{
        const prod=state.products.find(p=>p.id===t.product_id);
        const src=state.locations.find(l=>l.id===t.source_location_id);
        const dst=state.locations.find(l=>l.id===t.destination_location_id);
        const cls=t.status==='completed'?'ok':t.status==='pending'?'pending':'';
        const date=t.created_at?t.created_at.substring(0,10):'—';
        return`<div style="display:grid;grid-template-columns:60px 2fr 1.5fr 1.5fr 80px 100px 100px;gap:8px;padding:11px 12px;border-bottom:1px solid #edf1f5;font-size:12px;align-items:center">
          <span style="color:#7185a0">#${t.id}</span>
          <span><b>${esc(prod?.name||'—')}</b></span>
          <span>${esc(src?.name||'—')}</span>
          <span>${esc(dst?.name||'—')}</span>
          <span>${t.quantity}</span>
          <span><span class="pill ${cls}">${t.status}</span></span>
          <span style="color:#7185a0">${date}</span>
        </div>`;
      }).join('');
    }
  }

  // At-risk table
  const riskHost=$('#whRiskRows');
  if(riskHost){
    if(!atRisk.length){
      riskHost.innerHTML='<div class="empty-state" style="color:#0a9860">✓ All store stock is above reorder points.</div>';
    } else {
      riskHost.innerHTML=atRisk.map(x=>`
        <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 120px;gap:8px;padding:11px 12px;border-bottom:1px solid #edf1f5;font-size:12px;align-items:center">
          <span><b>${esc(x.product.name)}</b><br><small style="color:#7185a0">${esc(x.product.category||'')}</small></span>
          <span style="color:${x.store===0?'#ef4444':'#f59e0b'};font-weight:700">${x.store}</span>
          <span style="color:#6b84a0">${x.product.reorder_point}</span>
          <span style="color:#16a34a;font-weight:600">${x.warehouse} avail.</span>
          <span>${can('transfers')?`<button class="btn-stock" onclick="quickTransfer(${x.product.id})">⇄ Transfer</button>`:'<small style="color:#aaa">No access</small>'}</span>
        </div>`).join('');
    }
  }
}

function quickTransfer(productId){
  const stores=state.locations.filter(l=>l.location_type==='store');
  const warehouses=state.locations.filter(l=>l.location_type==='warehouse');
  if(!stores.length||!warehouses.length) return notify('Need both store and warehouse locations.',true);
  const prod=state.products.find(p=>p.id===productId);
  modal(`Transfer Stock — ${prod?.name||'Product'}`,
    `<label>From (Warehouse)<select name="source_location_id">${options(warehouses)}</select></label>
     <label>To (Store)<select name="destination_location_id">${options(stores)}</select></label>
     <label>Quantity<input name="quantity" type="number" min="1" value="${prod?.reorder_point||10}" required></label>`,
    'Create Transfer',
    async f=>{
      const d=Object.fromEntries(f);
      d.product_id=productId;
      d.source_location_id=+(d.source_location_id);
      d.destination_location_id=+(d.destination_location_id);
      d.quantity=+(d.quantity);
      await api('/transfers',{method:'POST',body:JSON.stringify(d)});
      notify('Transfer created ✓ Complete it from the transfer list.');
      refresh();
    }
  );
}

function renderAlerts(){
  const alerts = state.alerts || [];

  // ── Stat counts — purely from alert_type in DB ────────────────────────────
  const lowCount      = alerts.filter(a=>a.alert_type==='low_stock').length;
  const outCount      = alerts.filter(a=>a.alert_type==='out_of_stock').length;
  const criticalCount = alerts.filter(a=>a.severity==='critical').length;
  const supplierCount = alerts.filter(a=>a.alert_type==='supplier').length;

  const set = (id, val) => { const el=$('#'+id); if(el) el.textContent=val; };
  set('aStatLow',      lowCount);
  set('aStatOut',      outCount);
  set('aStatExpiry',   '—');   // Coming Soon — no expiry_date column yet
  set('aStatSupplier', supplierCount > 0 ? supplierCount : '—');
  set('aStatCritical', criticalCount);

  // ── Nav badge (total open) ─────────────────────────────────────────────────
  const openCount = alerts.filter(a=>a.status==='open'||!a.status).length;
  const badge=$('#alertNavBadge'); if(badge) badge.textContent=openCount||0;

  // ── Date range (rolling 30 days ending today) ─────────────────────────────
  const today=new Date();
  const prior=new Date(today); prior.setDate(prior.getDate()-29);
  const fmt=d=>d.toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});
  const rangeEl=$('#alertDateRange'); if(rangeEl) rangeEl.textContent=`${fmt(prior)} – ${fmt(today)}`;

  // ── Tab counts — each type counted separately ─────────────────────────────
  set('tabCountAll',      `(${alerts.length})`);
  set('tabCountLow',      `(${lowCount})`);
  set('tabCountOut',      `(${outCount})`);
  set('tabCountCritical', `(${criticalCount})`);

  // ── Filter + render rows ──────────────────────────────────────────────────
  renderAlertRows();

  // ── Recommendations sidebar (real data) ───────────────────────────────────
  const recHost=$('#alertRecommendations');
  if(recHost){
    const recs=state.recommendations||[];
    if(!recs.length){
      recHost.innerHTML='<div class="recommend"><b style="color:#0a9860">✓ All Clear</b><small>No restock action is required right now.</small></div>';
    } else {
      recHost.innerHTML=recs.slice(0,4).map(r=>`
        <div class="recommend">
          <b>${r.type==='transfer'?'◇ Transfer Stock':r.type==='purchase'?'! Purchase Order':'▣ Monitor'}</b>
          <small>${esc(r.message||r.product_name||'')}</small>
        </div>`).join('');
    }
  }

  // ── Dashboard alerts card (mini) ──────────────────────────────────────────
  const card=$('#dashboardPage .alerts-card');
  if(card){
    $$('.alert',card).forEach(x=>x.remove());
    alerts.slice(0,5).forEach(a=>card.insertAdjacentHTML('beforeend',
      `<div class="alert"><i class="${a.severity==='critical'?'red':'orange'}"></i>
       <div><b>${esc(a.product_name||'—')}</b><small>${esc(a.message)}</small></div>
       <time>${_timeAgo(a.created_at)}</time></div>`));
    if(!alerts.length) card.insertAdjacentHTML('beforeend','<div class="alert"><div><small>No open alerts. Stock is healthy ✓</small></div></div>');
  }
}

function renderAlertRows(){
  const host=$('#alertRows'); if(!host) return;
  let alerts=state.alerts||[];

  // Tab filter — strict: low_stock shows ONLY low_stock, out_of_stock shows ONLY out_of_stock
  // critical tab shows ALL severity=critical (includes out_of_stock)
  if(_alertFilter==='low_stock')    alerts=alerts.filter(a=>a.alert_type==='low_stock');
  else if(_alertFilter==='out_of_stock') alerts=alerts.filter(a=>a.alert_type==='out_of_stock');
  else if(_alertFilter==='critical') alerts=alerts.filter(a=>a.severity==='critical');
  // 'all' = no filter

  // Severity checkboxes (additional refinement)
  if(_alertSevFilter.size>0) alerts=alerts.filter(a=>_alertSevFilter.has(a.severity));

  if(!alerts.length){
    host.innerHTML='<div class="empty-state">No alerts match the current filter. Your stock is healthy ✓</div>';
    return;
  }
  host.innerHTML=alerts.map(a=>`
    <div class="alert-row ${a.alert_type==='out_of_stock'?'row-out':''}">
      <span>${_alertTypeIcon(a.alert_type)} <b style="font-size:11px">${_alertTypeLabel(a.alert_type)}</b></span>
      <span><b>${esc(a.product_name||'—')}</b></span>
      <span>${esc(a.message)}</span>
      <span><span class="${_sevClass(a.severity)}">${esc(a.severity||'—')}</span></span>
      <span title="${a.created_at||''}">${_timeAgo(a.created_at)}</span>
      <span>${can('alerts')?`<button class="primary-btn resolve" style="padding:4px 10px;font-size:11px" data-id="${a.id}">Resolve</button>`:'<small style="color:#aaa">No permission</small>'}</span>
    </div>`).join('');

  $$('.resolve',host).forEach(b=>b.onclick=async()=>{
    try{await api(`/alerts/${b.dataset.id}/resolve`,{method:'POST'});notify('Alert resolved.');refresh()}
    catch(e){handleApiError(e)}
  });
}
function renderDashboard(d,best,recs){const stats=$$('#dashboardPage .stats .stat strong');if(stats.length){stats[0].textContent=d.product_count;stats[1].textContent=money(d.sales_today);stats[2].textContent=money(grouped().reduce((n,x)=>n+x.store*x.product.sale_price,0));stats[3].textContent=money(grouped().reduce((n,x)=>n+x.warehouse*x.product.sale_price,0));stats[4].textContent=d.low_stock_count+d.critical_alert_count}const top=$('#dashboardPage .table-card');if(top){$$('.product-row',top).forEach(x=>x.remove());best.slice(0,5).forEach((x,i)=>top.insertAdjacentHTML('beforeend',`<div class="product-row"><span>${i+1}</span><span>📦 ${esc(x.name)}</span><span>${x.units_sold}</span><b>${money(x.revenue)}</b></div>`))}const rec=$('#alertsPage .recommendation');if(rec){rec.innerHTML=`<h2>✦ Smart recommendations</h2><p>Rule-based decisions. ML forecasting is <b>Coming Soon</b>.</p>${recs.slice(0,3).map(x=>`<div class="recommend"><b>${x.action==='transfer'?'⇄ Transfer Stock':'▣ Purchase Request'}</b><small>${esc(x.product_name)}: ${esc(x.reason)}</small>${can(x.action==='transfer'?'transfers':'purchases')?`<button data-rec="${x.product_id}" data-kind="${x.action}">${x.action==='transfer'?'Create transfer':'Create purchase request'} →</button>`:'<small>No permission for this action</small>'}</div>`).join('')||'<div class="recommend"><b>All clear</b><small>No restock action is required right now.</small></div>'}`;$$('[data-rec]',rec).forEach(b=>b.onclick=()=>b.dataset.kind==='transfer'?transferForm(+b.dataset.rec):purchaseForm(+b.dataset.rec))}}
function renderSalesChart(trend){if(!trend||!trend.length)return;const n=trend.length;const x0=40,x1=630,y0=20,y1=215;const card=$('.sales-card');const svg=$('svg',card);if(!svg)return;const max=Math.max(...trend.map(t=>t.total),1);const niceMax=Math.ceil(max/4)*4||4;const step=(x1-x0)/(n-1||1);const points=trend.map((t,i)=>({x:x0+i*step,y:y1-(t.total/niceMax)*(y1-y0),total:t.total,date:t.date}));const lineStr=points.map(p=>`${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');const areaStr=`M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)} `+points.slice(1).map(p=>`L${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')+` L${x1} ${y1} L${x0} ${y1} Z`;const lineEl=$('.line',svg);const areaEl=$('.area',svg);const dotsEl=$('.dots',svg);if(lineEl)lineEl.setAttribute('points',lineStr);if(areaEl)areaEl.setAttribute('d',areaStr);if(dotsEl)dotsEl.innerHTML=points.map(p=>`<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="5"><title>${new Date(p.date+'T00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short'})}: ${money(p.total)}</title></circle>`).join('');const yLabels=$$('.y-labels span',card);if(yLabels.length===5)for(let i=0;i<5;i++)yLabels[i].textContent=compactMoney(niceMax*(4-i)/4);const xLabels=$$('.x-labels span',card);const step2=Math.max(1,Math.floor(n/7));trend.forEach((t,i)=>{if(xLabels[Math.floor(i*7/(n||1))])xLabels[Math.floor(i*7/(n||1))].textContent=new Date(t.date+'T00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short'})});const periodTotal=trend.reduce((s,t)=>s+t.total,0);const peak=trend.reduce((a,b)=>b.total>a.total?b:a,trend[0]);const avg=periodTotal/(n||1);const chartTotal=$('#chartTotalRevenue');const chartPeak=$('#chartPeakDay');const chartAvg=$('#chartAvgDay');if(chartTotal)chartTotal.textContent=money(periodTotal);if(chartPeak)chartPeak.textContent=new Date(peak.date+'T00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short'});if(chartAvg)chartAvg.textContent=money(avg)}
function renderStockDistribution(){const g=grouped();const storeUnits=g.reduce((n,x)=>n+x.store,0),whUnits=g.reduce((n,x)=>n+x.warehouse,0),total=storeUnits+whUnits;const storePct=total?Math.round(storeUnits/total*100):0,whPct=100-storePct;const storeVal=g.reduce((n,x)=>n+x.store*x.product.sale_price,0),whVal=g.reduce((n,x)=>n+x.warehouse*x.product.sale_price,0);const donut=$('.donut');if(donut)donut.style.background=`conic-gradient(#176bd6 0 ${storePct}%,#20b778 ${storePct}% 100%)`;const tot=$('#donutTotal');if(tot)tot.textContent=total.toLocaleString('en-IN');const ls=$('#legendStore');if(ls)ls.textContent=`${storeUnits.toLocaleString('en-IN')} units (${storePct}%)`;const lw=$('#legendWarehouse');if(lw)lw.textContent=`${whUnits.toLocaleString('en-IN')} units (${whPct}%)`;const sv=$('#stockStoreValue');if(sv)sv.textContent=money(storeVal);const wv=$('#stockWhValue');if(wv)wv.textContent=money(whVal)}
function renderLowStockDashboard(){const card=$('#dashboardPage .low-card');if(!card)return;$$('.product-row',card).forEach(x=>x.remove());const low=grouped().filter(({store,product})=>store<=product.reorder_point).sort((a,b)=>a.store-b.store).slice(0,5);if(!low.length){card.insertAdjacentHTML('beforeend','<div class="empty-state">No low-stock products. 🎉</div>');return}low.forEach(({product,store})=>card.insertAdjacentHTML('beforeend',`<div class="product-row"><span>📦 ${esc(product.name)}</span><strong class="danger">${store}</strong><span>${product.reorder_point}</span></div>`))}
function renderSuppliers(filter=''){
  const sups = state.suppliers||[];
  // Stats
  const set=(id,v)=>{const e=$('#'+id);if(e)e.textContent=v};
  set('supCount', sups.length);
  const pending = (state.purchase_requests||[]).filter(r=>r.status==='pending').length;
  set('supPending', pending);
  const avgLead = sups.length ? (sups.reduce((s,x)=>s+(x.lead_time_days||0),0)/sups.length).toFixed(1)+' days' : '—';
  set('supAvgLead', avgLead);

  // Table rows
  const host=$('#supplierRows'); if(!host) return;
  const filtered = filter ? sups.filter(s=>s.name.toLowerCase().includes(filter.toLowerCase())||
    (s.contact_name||'').toLowerCase().includes(filter.toLowerCase())) : sups;
  if(!filtered.length){
    host.innerHTML=`<div class="empty-state">${sups.length?'No suppliers match your search.':'No suppliers added yet. Click <b>+ Add Supplier</b> to get started.'}</div>`;
    return;
  }
  host.innerHTML=filtered.map(s=>`
    <div class="sup-row">
      <span><b>${esc(s.name)}</b></span>
      <span>${esc(s.contact_name||'—')}</span>
      <span><a href="mailto:${esc(s.email||'')}" style="color:#2563eb">${esc(s.email||'—')}</a></span>
      <span>⏱ ${s.lead_time_days||3} days</span>
      <span class="actions">
        ${can('purchases')?`<button class="btn-stock" onclick="purchaseForm(${s.id},'${esc(s.name)}')">+ Order</button>`:''}
        ${can('suppliers')?`<button class="btn-price" onclick="deleteSupplier(${s.id})">✕ Remove</button>`:''}
      </span>
    </div>`).join('');
}
function filterSuppliers(v){renderSuppliers(v)}
function renderUsers(){const host=$('#userTable');if(!host)return;host.innerHTML='<div class="data-head">Username | Full Name | Role | Created</div>'+(state.users.length?state.users.map(u=>`<div>${esc(u.username)} | ${esc(u.full_name||'—')} | ${esc(ROLE_LABELS[u.role]||u.role)} | ${new Date(u.created_at+'Z').toLocaleDateString()}</div>`).join(''):'<div class="empty-state">No users yet.</div>')}
function renderCategoryOptions(){const sel=$('#categoryFilter');if(!sel)return;const cats=[...new Set(state.products.map(p=>p.category).filter(Boolean))].sort();const current=sel.value;sel.innerHTML='<option>All Categories</option>'+cats.map(c=>`<option>${esc(c)}</option>`).join('');if(cats.includes(current))sel.value=current}
function renderInventoryStats(){const stats=$$('#inventoryPage .inv-stats .stat strong');if(!stats.length)return;const g=grouped();const storeValue=g.reduce((n,x)=>n+x.store*x.product.sale_price,0),whValue=g.reduce((n,x)=>n+x.warehouse*x.product.sale_price,0),lowCount=g.filter(x=>x.store<=x.product.reorder_point).length;stats[0].textContent=state.products.length;stats[1].textContent=money(storeValue);stats[2].textContent=money(whValue);stats[3].textContent=lowCount}
function renderInventorySidebar(){const widgets=$$('#inventoryPage .inventory-side .side-widget');if(widgets.length<3)return;const g=grouped();const total=g.length,normal=g.filter(x=>x.store>x.product.reorder_point).length,low=g.filter(x=>x.store>0&&x.store<=x.product.reorder_point).length,out=g.filter(x=>x.store===0).length;const pct=n=>total?Math.round(n/total*1000)/10:0;const summary=widgets[0];const dTotal=$('.mini-donut b',summary);if(dTotal)dTotal.textContent=total;const ps=$$('p',summary);if(ps[0])ps[0].innerHTML=`🟢 Normal <span>${normal} (${pct(normal)}%)</span>`;if(ps[1])ps[1].innerHTML=`🟠 Low Stock <span>${low} (${pct(low)}%)</span>`;if(ps[2])ps[2].innerHTML=`🔴 Out of Stock <span>${out} (${pct(out)}%)</span>`;if(ps[3])ps[3].remove();const catCounts={};state.products.forEach(p=>{const c=p.category||'Uncategorized';catCounts[c]=(catCounts[c]||0)+1});const entries=Object.entries(catCounts).sort((a,b)=>b[1]-a[1]).slice(0,6);const catHost=widgets[1];catHost.innerHTML='<h2>Quick Filters</h2>'+(entries.length?entries.map(([cat,count])=>`<div class="quick-filter" data-cat="${esc(cat)}">🔵 ${esc(cat)} <span>${count} ›</span></div>`).join(''):'<div class="empty-state">No categories yet.</div>');$$('.quick-filter',catHost).forEach(el=>el.onclick=()=>{const sel=$('#categoryFilter');if(sel){sel.value=el.dataset.cat;renderInventory()}});const recent=state.alerts.slice(0,4);const alertHost=widgets[2];alertHost.innerHTML='<h2>Recent Stock Alerts <a href="#" data-page="alertsPage">View All →</a></h2>'+(recent.length?recent.map(a=>`<div class="side-alert">${a.severity==='critical'?'🔴':'🟠'} ${esc(a.product_name)} <small>${esc(a.message)}</small></div>`).join(''):'<div class="empty-state">No active alerts. 🎉</div>');const link=$('[data-page]',alertHost);if(link)link.onclick=e=>{e.preventDefault();page('alertsPage')}}
async function refresh(){try{
  if(state.role==='worker'){
    const[p,l,s]=await Promise.all([api('/products'),api('/locations'),api('/stock')]);
    state.products=p.items;state.locations=l.items;state.stock=s.items;
    renderWorkerView();return;
  }
  const[p,l,s,a,sup,d,b,r,trend,sal,tx,pr]=await Promise.all([api('/products'),api('/locations'),api('/stock'),api('/alerts'),api('/suppliers'),api('/dashboard'),api('/analytics/best-sellers'),api('/recommendations'),api('/analytics/sales-trend?days=7'),api('/sales'),api('/transfers'),api('/purchase-requests')]);
  state.products=p.items;state.locations=l.items;state.stock=s.items;state.alerts=a.items;state.suppliers=sup.items;state.sales=sal.items;state.recommendations=r.items||[];state.transfers=tx.items||[];state.purchase_requests=pr.items||[];
  renderCategoryOptions();renderInventory();renderInventoryStats();renderInventorySidebar();renderAlerts();
  renderDashboard(d,b.items,r.items);renderSalesChart(trend.items);renderStockDistribution();renderLowStockDashboard();renderSuppliers();renderWarehouse();
  if(can('settings')){try{const u=await api('/users');state.users=u.items;renderUsers()}catch(e){}}
}catch(e){if(e.status===401)return logout(true);notify('Cannot reach backend: '+e.message,true)}}
const options=(items,label='name')=>items.map(x=>`<option value="${x.id}">${esc(x[label])}</option>`).join('');
function modal(title,fields,button,save){const m=$('#actionModal');m.innerHTML=`<div class="modal-box"><button class="close" type="button">×</button><h2>${title}</h2><form>${fields}<button class="primary-btn">${button}</button></form></div>`;m.classList.remove('hidden');$('.close',m).onclick=()=>m.classList.add('hidden');$('form',m).onsubmit=async e=>{e.preventDefault();try{await save(new FormData(e.currentTarget));m.classList.add('hidden');refresh()}catch(x){handleApiError(x)}}}
function locationForm(){modal('Add Location','<label>Location name<input name="name" required></label><label>Type<select name="location_type"><option value="store">Store</option><option value="warehouse">Warehouse</option></select></label><label>Address<input name="address"></label>','Save Location',async f=>{await api('/locations',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});notify('Location added.')})}
function stockForm(productId){if(!state.locations.length)return notify('Add a location before setting stock.',true);modal('Set Stock Level',`<label>Location<select name="location_id">${options(state.locations)}</select></label><label>Quantity<input name="quantity" type="number" min="0" required value="0"></label>`,'Save Stock',async f=>{const d=Object.fromEntries(f);d.product_id=productId;d.location_id=+d.location_id;d.quantity=+d.quantity;await api('/stock',{method:'POST',body:JSON.stringify(d)});notify('Stock level updated.')})}
function saleForm(){const stores=state.locations.filter(x=>x.location_type==='store');if(!state.products.length||!stores.length)return notify('Add a product and store location first.',true);modal('Record Sale',`<label>Product<select name="product_id">${options(state.products)}</select></label><label>Store<select name="location_id">${options(stores)}</select></label><label>Quantity<input name="quantity" type="number" min="1" required value="1"></label><label>Unit price<input name="unit_price" type="number" min="0" step=".01"></label>`,'Record Sale',async f=>{const d=Object.fromEntries(f);['product_id','location_id','quantity'].forEach(k=>d[k]=+d[k]);if(d.unit_price==='')delete d.unit_price;else d.unit_price=+d.unit_price;await api('/sales',{method:'POST',body:JSON.stringify(d)});notify('Sale recorded and stock updated.')})}
function transferForm(productId){if(!state.products.length||state.locations.length<2)return notify('Add products and at least two locations first.',true);modal('Create Transfer',`<label>Product<select name="product_id">${options(state.products)}</select></label><label>From<select name="source_location_id">${options(state.locations)}</select></label><label>To<select name="destination_location_id">${options(state.locations)}</select></label><label>Quantity<input name="quantity" type="number" min="1" required value="1"></label>`,'Create Transfer',async f=>{const d=Object.fromEntries(f);['product_id','source_location_id','destination_location_id','quantity'].forEach(k=>d[k]=+d[k]);if(productId)d.product_id=productId;await api('/transfers',{method:'POST',body:JSON.stringify(d)});notify('Transfer created. Complete it from the API workflow.')})}
function purchaseForm(productId){if(!state.suppliers.length)return notify('Add a supplier before creating a purchase request.',true);if(!state.locations.length||!state.products.length)return notify('Add products and locations first.',true);modal('Create Purchase Request',`<label>Supplier<select name="supplier_id">${options(state.suppliers)}</select></label><label>Product<select name="product_id">${options(state.products)}</select></label><label>Deliver to<select name="destination_location_id">${options(state.locations)}</select></label><label>Quantity<input name="quantity" type="number" min="1" required value="1"></label>`,'Create Request',async f=>{const d=Object.fromEntries(f);['supplier_id','product_id','destination_location_id','quantity'].forEach(k=>d[k]=+d[k]);if(productId)d.product_id=productId;await api('/purchase-requests',{method:'POST',body:JSON.stringify(d)});notify('Purchase request created.')})}
function userForm(){modal('Add User','<label>Username<input name="username" required autocomplete="off"></label><label>Full name<input name="full_name"></label><label>Role<select name="role"><option value="employee">Employee (Stock + Sales)</option><option value="worker">Worker (View Stock Only)</option><option value="manager">Manager (Full Access)</option><option value="admin">Admin / Owner (Full Access)</option></select></label><label>Password<input name="password" type="password" required minlength="6" placeholder="At least 6 characters"></label>','Create User',async f=>{await api('/users',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});notify('User created.')});}
function clearAuthStorage(){localStorage.removeItem(AUTH_KEY);sessionStorage.removeItem(AUTH_KEY)}
async function logout(expired=false){const token=state.token;state.token=null;state.role=null;state.username=null;state.fullName=null;clearAuthStorage();if(token){try{await fetch(API+'/auth/logout',{method:'POST',headers:{Authorization:'Bearer '+token}})}catch(e){}}ALL_PAGES.forEach(id=>$('#'+id)?.classList.add('hidden'));$('#loginPage').classList.remove('hidden');$('#loginForm')?.reset();const err=$('#loginError');if(err){err.textContent=expired?'Your session expired. Please log in again.':'';err.classList.toggle('hidden',!expired)}}
async function changePassword(){const form=$('#changePasswordForm');if(!form)return;const f=new FormData(form);const newPwd=f.get('new_password'),confirmPwd=f.get('confirm_password');if(newPwd!==confirmPwd){notify('Passwords do not match.',true);return}try{await api('/auth/change-password',{method:'POST',body:JSON.stringify({current_password:f.get('current_password'),new_password:newPwd})});notify('Password changed. Please log in again.');logout(false)}catch(e){handleApiError(e)}}
async function restoreSession(){const raw=localStorage.getItem(AUTH_KEY)||sessionStorage.getItem(AUTH_KEY);if(!raw)return false;try{const saved=JSON.parse(raw);state.token=saved.token;state.role=saved.role;state.username=saved.username;state.fullName=saved.fullName;const me=await api('/auth/me');state.role=me.user.role;state.username=me.user.username;state.fullName=me.user.full_name;return true}catch(e){state.token=null;clearAuthStorage();return false}}
async function init(){const side=$('#dashboardPage .sidebar'),top=$('#dashboardPage .topbar');$$('.app-page .sidebar').forEach(x=>x.innerHTML=side.innerHTML);$$('.app-page .topbar').forEach(x=>x.innerHTML=top.innerHTML);$('#showPassword').onclick=()=>{const p=$('#password');p.type=p.type==='password'?'text':'password'};$('#loginForm').onsubmit=async e=>{e.preventDefault();const username=$('#loginUsername').value.trim();const password=$('#password').value;const remember=$('#rememberMe')?.checked;const err=$('#loginError');err.classList.add('hidden');try{const res=await api('/auth/login',{method:'POST',body:JSON.stringify({username,password})});state.token=res.token;state.role=res.user.role;state.username=res.user.username;state.fullName=res.user.full_name;const payload=JSON.stringify({token:state.token,role:state.role,username:state.username,fullName:state.fullName});clearAuthStorage();(remember?localStorage:sessionStorage).setItem(AUTH_KEY,payload);$('#loginPage').classList.add('hidden');$$('#currentRoleLabel').forEach(x=>x.textContent=ROLE_LABELS[state.role]||state.role);$$('#currentUserLabel').forEach(x=>x.textContent=state.fullName||state.username);applyRolePermissions();showHomeForRole();refresh()}catch(x){err.textContent=x.message||'Login failed.';err.classList.remove('hidden')}};$('#logoutBtn')?.addEventListener('click',()=>logout(false));if(await restoreSession()){$('#loginPage').classList.add('hidden');$$('#currentRoleLabel').forEach(x=>x.textContent=ROLE_LABELS[state.role]||state.role);$$('#currentUserLabel').forEach(x=>x.textContent=state.fullName||state.username);applyRolePermissions();showHomeForRole();refresh()}$$('[data-page]').forEach(x=>x.onclick=e=>{
  e.preventDefault();
  page(x.dataset.page);
  if(x.dataset.page==='salesPage')     renderSalesPage();
  if(x.dataset.page==='alertsPage')    renderAlerts();
  if(x.dataset.page==='warehousePage') renderWarehouse();
  if(x.dataset.page==='suppliersPage') renderSuppliers();
});
$('#addSupplierBtn')?.addEventListener('click', supplierForm);
// Alert tabs
$$('.atab').forEach(btn=>btn.addEventListener('click',()=>{
  $$('.atab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  _alertFilter=btn.dataset.filter;
  renderAlertRows();
}));
// Alert status filter
$$('.afilt').forEach(btn=>btn.addEventListener('click',async()=>{
  $$('.afilt').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  _alertStatus=btn.dataset.status;
  try{
    const status=_alertStatus==='all'?'all':'open';
    const a=await api(`/alerts?status=${status}`);
    state.alerts=a.items;
    renderAlerts();
  }catch(e){handleApiError(e)}
}));
// Severity checkboxes
$$('.sev-filter').forEach(cb=>cb.addEventListener('change',()=>{
  _alertSevFilter=new Set($$('.sev-filter').filter(c=>c.checked).map(c=>c.value));
  renderAlertRows();
}));
// Clear all filters
$('#clearAlertFilter')?.addEventListener('click',()=>{
  _alertFilter='all';_alertSevFilter=new Set();
  $$('.atab').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
  $$('.sev-filter').forEach(c=>c.checked=false);
  renderAlertRows();
});
startLiveClock();
$$('.sales-tab').forEach(btn=>btn.addEventListener('click',async()=>{$$('.sales-tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');try{const t=await api(`/analytics/sales-trend?days=${btn.dataset.days}`);renderSalesBarChart(t.items)}catch(e){handleApiError(e)}}));['inventorySearch','categoryFilter','stockFilter'].forEach(id=>$('#'+id)?.addEventListener('input',renderInventory));$('#resetInventory')?.addEventListener('click',()=>{$('#inventorySearch').value='';$('#categoryFilter').value='All Categories';$('#stockFilter').value='All Status';renderInventory()});$('#addLocationBtn').onclick=locationForm;$('#addProductBtn').onclick=()=>$('#productModal').classList.remove('hidden');$('#productModal .close').onclick=()=>$('#productModal').classList.add('hidden');$('#saveProduct').onclick=async()=>{try{await api('/products',{method:'POST',body:JSON.stringify({sku:$('#newProductSku').value,name:$('#newProductName').value,category:$('#newProductCategory').value,sale_price:+$('#newProductPrice').value||0,reorder_point:+$('#newProductReorder').value||0})});$('#productModal').classList.add('hidden');notify('Product added.');refresh()}catch(e){handleApiError(e)}};$('#newSaleBtn')?.addEventListener('click',saleForm);$('#transferBtn')?.addEventListener('click',()=>transferForm());$('#purchaseBtn')?.addEventListener('click',()=>purchaseForm());$('#userBtn')?.addEventListener('click',userForm);$$('.quick-grid .q').forEach(b=>b.onclick=()=>{const t=b.textContent;t.includes('Add Product')?$('#addProductBtn').click():t.includes('Transfer')?transferForm():t.includes('Purchase')?purchaseForm():t.includes('Suppliers')?page('suppliersPage'):page('reportsPage')});$('#logoutBtn2')?.addEventListener('click',()=>logout(false));$$('.chart-tab').forEach(btn=>btn.addEventListener('click',async()=>{$$('.chart-tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');const days=+btn.dataset.days;const sub=$('#salesChartSubtitle');if(sub)sub.textContent=`Daily sales (last ${days} days)`;try{const t=await api(`/analytics/sales-trend?days=${days}`);const xLabels=$$('.sales-card .x-labels span');xLabels.forEach(s=>s.textContent='');renderSalesChart(t.items)}catch(e){handleApiError(e)}}));$('#changePasswordForm')?.addEventListener('submit',async e=>{e.preventDefault();await changePassword();$('#changePasswordForm').reset()});}
init();
