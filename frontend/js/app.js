/**
 * BBL-ELECTRA Monitoring v2.0 — Premium Dashboard
 */
let currentPlantId = 1, mainChart = null, historyChart = null;
let donutPV = null, donutConso = null;
let monthCompareChart = null, monthDetailChart = null, yearEvolutionChart = null, kwhEvolutionChart = null, psChart = null;
let invoicesData = [], refreshInterval = null, refreshTimer = 0;
const REFRESH_SECONDS = 300;
const MONTHS = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc'];
const YC = { 2024: '#7c3aed', 2025: '#0284c7', 2026: '#059669' };
const GC = 'rgba(0,0,0,0.03)', TC = '#94a3b8';
const CHART_OPTS = { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' } };

function showPage(p) {
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(`page-${p}`)?.classList.add('active');
  const m = { dashboard:0, stats:1, factures:2, alerts:3, settings:4 };
  document.querySelectorAll('.nav-btn')[m[p]]?.classList.add('active');
  if (p==='stats') loadStatsPage();
  if (p==='alerts') loadAllAlerts();
  if (p==='settings') { loadSettings(); loadUsers(); }
  if (p==='factures') loadInvoices();
  if (typeof lucide!=='undefined') setTimeout(()=>lucide.createIcons(),100);
}

// === DASHBOARD ===
async function updateDashboard() {
  try {
    const d = await api.getRealtime(currentPlantId);
    if (d.error) return;

    // === DÉTECTION HORS LIGNE ===
    const offlineBanner = document.getElementById('offline-banner');
    if (d.is_offline) {
      if (offlineBanner) offlineBanner.style.display = 'flex';
      document.getElementById('liveDot').style.background = '#94a3b8';
      document.getElementById('liveText').textContent = 'Hors ligne';
      return; // Ne pas mettre à jour les KPIs avec des données périmées
    } else {
      if (offlineBanner) offlineBanner.style.display = 'none';
      document.getElementById('liveText').textContent = 'Live';
    }
    document.getElementById('kpi-pv').textContent = fmt(d.pv_power);
    document.getElementById('kpi-conso').textContent = fmt(d.consumption_corrected);
    document.getElementById('kpi-import').textContent = fmt(d.grid_import);
    document.getElementById('kpi-export').textContent = fmt(d.grid_export);

    // Flow
    document.getElementById('flow-pv').textContent = `${fmt(d.pv_power)} kW`;
    document.getElementById('flow-conso').textContent = `${fmt(d.consumption_corrected)} kW`;
    const gf = d.grid_import > 0 ? d.grid_import : d.grid_export;
    document.getElementById('flow-grid').textContent = `${fmt(gf)} kW`;

    // Grid circle state
    const gc = document.getElementById('gridCircle');
    gc.className = `flow-circle grid ${d.grid_import > 0 ? 'importing' : d.grid_export > 0 ? 'exporting' : ''}`;

    // Flow animation direction
    const dotGrid = document.getElementById('dot-grid');
    const lineGrid = document.getElementById('line-grid');
    if (d.grid_export > 0) {
      dotGrid.className.baseVal = 'flow-particle grid-p exporting';
      lineGrid.className.baseVal = 'flow-line grid-line exporting';
    } else if (d.grid_import > 0) {
      dotGrid.className.baseVal = 'flow-particle grid-p importing';
      lineGrid.className.baseVal = 'flow-line grid-line importing';
    }

    // PV line opacity
    const linePv = document.getElementById('line-pv');
    const dotPv = document.getElementById('dot-pv');
    linePv.style.opacity = d.pv_power > 1 ? '1' : '0.15';
    dotPv.style.opacity = d.pv_power > 1 ? '1' : '0';

    // Tariff badge
    const b = document.getElementById('tariffBadge');
    b.textContent = d.tariff_period || '--';
    b.className = `tariff-pill tariff-${d.tariff_period || 'HPL'}`;

    if (d.timestamp) document.getElementById('flowTime').textContent = new Date(d.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
    document.getElementById('liveDot').style.background = '#10b981';

    // Chart point
    if (mainChart) {
      const t = new Date(d.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
      mainChart.data.labels.push(t);
      mainChart.data.datasets[0].data.push(d.pv_power);
      mainChart.data.datasets[1].data.push(d.consumption_corrected);
      mainChart.data.datasets[2].data.push(d.grid_import);
      mainChart.data.datasets[3].data.push(d.grid_export);
      if (mainChart.data.labels.length > 288) { mainChart.data.labels.shift(); mainChart.data.datasets.forEach(ds=>ds.data.shift()); }
      mainChart.update('none');
    }

    loadDailySummary(); loadRecentAlerts(); loadDonuts();
  } catch(e) { document.getElementById('liveDot').style.background='#ef4444'; }
}

async function loadMainChartHistory() {
  try {
    const d = await api.getHistory(currentPlantId, 24);
    if (!d?.length) return;
    mainChart.data.labels = d.map(r=>new Date(r.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}));
    mainChart.data.datasets[0].data = d.map(r=>r.pv_power);
    mainChart.data.datasets[1].data = d.map(r=>r.consumption);
    mainChart.data.datasets[2].data = d.map(r=>r.grid_import);
    mainChart.data.datasets[3].data = d.map(r=>r.grid_export);
    mainChart.update('none');
  } catch(e) {}
}

async function loadDailySummary() {
  try {
    const d = await api.getDailySummary(currentPlantId);
    if (d.error) return;
    const b = d.breakdown||{};
    if(b.HC){document.getElementById('cost-hc').textContent=`${b.HC.cost_dh.toFixed(0)} DH`;document.getElementById('kwh-hc').textContent=b.HC.kwh_import.toFixed(0);}
    if(b.HPL){document.getElementById('cost-hn').textContent=`${b.HPL.cost_dh.toFixed(0)} DH`;document.getElementById('kwh-hn').textContent=b.HPL.kwh_import.toFixed(0);}
    if(b.HP){document.getElementById('cost-hp').textContent=`${b.HP.cost_dh.toFixed(0)} DH`;document.getElementById('kwh-hp').textContent=b.HP.kwh_import.toFixed(0);}
    document.getElementById('cost-total').textContent=`${d.total_cost_dh.toFixed(0)} DH`;
  } catch(e) {}
}

// === DONUTS ===
async function loadDonuts() {
  try {
    const d = await api.getDailySummary(currentPlantId);
    if (d.error) return;
    const b = d.breakdown||{};
    const totalPV = d.total_pv_kwh||0;
    const totalSelfuse = (b.HC?.kwh_selfuse||0)+(b.HPL?.kwh_selfuse||0)+(b.HP?.kwh_selfuse||0);
    const totalExport = d.total_export_kwh||0;
    const totalImport = d.total_import_kwh||0;
    const totalConso = d.total_consumption_kwh||0;

    // PV donut
    document.getElementById('donut-pv-val').textContent = totalPV.toFixed(0);
    document.getElementById('donut-selfuse').textContent = totalSelfuse.toFixed(0);
    document.getElementById('donut-export').textContent = totalExport.toFixed(1);
    if (donutPV) donutPV.destroy();
    donutPV = new Chart(document.getElementById('donutPV'), {
      type: 'doughnut',
      data: { labels: ['Autoconsommé','Exporté'], datasets: [{data:[totalSelfuse, totalExport], backgroundColor:['#0d9488','#ea580c'], borderWidth:0, cutout:'75%'}] },
      options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.label}: ${Number(c.raw).toFixed(1)} kWh`}}} }
    });

    // Conso donut
    document.getElementById('donut-conso-val').textContent = totalConso.toFixed(0);
    document.getElementById('donut-from-pv').textContent = totalSelfuse.toFixed(0);
    document.getElementById('donut-from-grid').textContent = totalImport.toFixed(0);
    if (donutConso) donutConso.destroy();
    donutConso = new Chart(document.getElementById('donutConso'), {
      type: 'doughnut',
      data: { labels: ['Depuis PV','Importé'], datasets: [{data:[totalSelfuse, totalImport], backgroundColor:['#0d9488','#e11d48'], borderWidth:0, cutout:'75%'}] },
      options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.label}: ${Number(c.raw).toFixed(0)} kWh`}}} }
    });
  } catch(e) {}
}

// === ALERTS ===
async function loadRecentAlerts() {
  try {
    const a = await api.getAlerts('all',5); const c = document.getElementById('alertsList');
    if(!a?.length){c.innerHTML='<div class="alert-none">✅ Aucune alerte</div>';return;}
    c.innerHTML=a.map(x=>`<div class="alert-row"><div class="alert-dot ${x.severity||'warning'}"></div><div class="alert-body"><div class="alert-msg">${x.message||x.rule}</div><div class="alert-ts">${fmtTime(x.triggered_at)}</div></div></div>`).join('');
  } catch(e) {}
}
async function loadAllAlerts() {
  try {
    const a = await api.getAlerts('all',50); const c = document.getElementById('allAlertsList');
    if(!a?.length){c.innerHTML='<div class="alert-none">✅ Aucune alerte</div>';return;}
    c.innerHTML=a.map(x=>`<div class="alert-row"><div class="alert-dot ${x.severity||'warning'}"></div><div class="alert-body"><div class="alert-msg">${x.message||x.rule}</div><div class="alert-ts">${fmtTime(x.triggered_at)} — ${x.rule}</div></div></div>`).join('');
  } catch(e) {}
}

// === INVOICES ===
async function loadInvoices() {
  try {
    invoicesData = await api.getInvoices();
    if(!invoicesData?.length) return;
    invoicesData.sort((a,b)=>a.year!==b.year?a.year-b.year:a.month-b.month);
    renderYearEvolution(); renderKwhEvolution(); renderPsChart(); renderInvTable(); updateMonthComparison();
  } catch(e) {}
}

function updateMonthComparison() {
  const mo = parseInt(document.getElementById('monthSelector').value);
  document.getElementById('monthDetailLabel').textContent = MONTHS[mo-1];
  const f = invoicesData.filter(i=>i.month===mo);
  const yrs = f.map(i=>String(i.year));
  if(monthCompareChart) monthCompareChart.destroy();
  monthCompareChart = new Chart(document.getElementById('monthCompareChart'),{type:'bar',data:{labels:yrs,datasets:[{label:'Facture TTC',data:f.map(i=>i.total_ttc),backgroundColor:f.map(i=>YC[i.year]||'#888'),borderRadius:8,maxBarThickness:50}]},options:{...CHART_OPTS,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${Number(c.raw).toLocaleString('fr-FR')} DH`}}},scales:{x:{grid:{display:false},ticks:{color:TC,font:{weight:'700'}}},y:{grid:{color:GC},ticks:{color:TC,callback:v=>`${(v/1000).toFixed(0)}k`}}}}});
  if(monthDetailChart) monthDetailChart.destroy();
  monthDetailChart = new Chart(document.getElementById('monthDetailChart'),{type:'bar',data:{labels:yrs,datasets:[{label:'HP',data:f.map(i=>i.kwh_hp||0),backgroundColor:'rgba(225,29,72,0.65)',borderRadius:4},{label:'HPL',data:f.map(i=>i.kwh_hpl||0),backgroundColor:'rgba(5,150,105,0.65)',borderRadius:4},{label:'HC',data:f.map(i=>i.kwh_hc||0),backgroundColor:'rgba(2,132,199,0.65)',borderRadius:4}]},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,font:{size:11},usePointStyle:true,pointStyle:'circle'}},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${Number(c.raw).toLocaleString('fr-FR')} kWh`}}},scales:{x:{stacked:true,grid:{display:false},ticks:{color:TC,font:{weight:'700'}}},y:{stacked:true,grid:{color:GC},ticks:{color:TC,callback:v=>`${(v/1000).toFixed(0)}k`}}}}});
}

function renderYearEvolution() {
  const yrs = [...new Set(invoicesData.map(i=>i.year))].sort();
  if(yearEvolutionChart) yearEvolutionChart.destroy();
  yearEvolutionChart = new Chart(document.getElementById('yearEvolutionChart'),{type:'line',data:{labels:MONTHS,datasets:yrs.map(y=>({label:String(y),data:Array.from({length:12},(_,m)=>{const i=invoicesData.find(x=>x.year===y&&x.month===m+1);return i?i.total_ttc:null;}),borderColor:YC[y]||'#888',backgroundColor:'transparent',tension:0.3,pointRadius:4,borderWidth:2.5,spanGaps:false}))},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,font:{size:12,weight:'600'},usePointStyle:true,pointStyle:'circle',padding:16}},tooltip:{callbacks:{label:c=>c.raw?`${c.dataset.label}: ${Number(c.raw).toLocaleString('fr-FR')} DH`:''}}},scales:{x:{grid:{color:GC},ticks:{color:TC}},y:{grid:{color:GC},ticks:{color:TC,callback:v=>`${(v/1000).toFixed(0)}k`}}}}});
}

function renderKwhEvolution() {
  const yrs = [...new Set(invoicesData.map(i=>i.year))].sort();
  if(kwhEvolutionChart) kwhEvolutionChart.destroy();
  kwhEvolutionChart = new Chart(document.getElementById('kwhEvolutionChart'),{type:'line',data:{labels:MONTHS,datasets:yrs.map(y=>({label:String(y),data:Array.from({length:12},(_,m)=>{const i=invoicesData.find(x=>x.year===y&&x.month===m+1);return i?i.kwh_total:null;}),borderColor:YC[y]||'#888',backgroundColor:'transparent',tension:0.3,pointRadius:4,borderWidth:2.5,spanGaps:false}))},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,font:{size:12,weight:'600'},usePointStyle:true,pointStyle:'circle',padding:16}},tooltip:{callbacks:{label:c=>c.raw?`${c.dataset.label}: ${Number(c.raw).toLocaleString('fr-FR')} kWh`:''}}},scales:{x:{grid:{color:GC},ticks:{color:TC}},y:{grid:{color:GC},ticks:{color:TC,callback:v=>`${(v/1000).toFixed(0)}k`}}}}});
}

function renderPsChart() {
  const labels = invoicesData.map(i=>`${MONTHS[i.month-1]} ${i.year}`);
  if(psChart) psChart.destroy();
  psChart = new Chart(document.getElementById('psChart'),{type:'line',data:{labels,datasets:[{label:'PS (KVA)',data:invoicesData.map(i=>i.subscribed_power_kva),borderColor:'#0d9488',backgroundColor:'rgba(13,148,136,0.06)',fill:true,tension:0,pointRadius:2,borderWidth:1.8,stepped:true}]},options:{...CHART_OPTS,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{color:TC,font:{size:9},maxTicksLimit:10}},y:{grid:{color:GC},ticks:{color:TC},min:0,max:700}}}});
}

function renderInvTable() {
  const t=document.getElementById('invoiceTable');
  let h=`<thead><tr><th>Période</th><th>HP</th><th>HPL</th><th>HC</th><th>Total kWh</th><th>PS</th><th>RDPS</th><th>TTC</th></tr></thead><tbody>`;
  for(const i of invoicesData){
    const r=i.excess_power_penalty>0?`<span class="rdps">${Number(i.excess_power_penalty).toLocaleString('fr-FR')}</span>`:'-';
    h+=`<tr><td>${MONTHS[i.month-1]} ${i.year}</td><td>${Number(i.kwh_hp||0).toLocaleString('fr-FR')}</td><td>${Number(i.kwh_hpl||0).toLocaleString('fr-FR')}</td><td>${Number(i.kwh_hc||0).toLocaleString('fr-FR')}</td><td>${Number(i.kwh_total||0).toLocaleString('fr-FR')}</td><td>${i.subscribed_power_kva}</td><td>${r}</td><td class="ttc">${Number(i.total_ttc).toLocaleString('fr-FR',{maximumFractionDigits:0})}</td></tr>`;
  }
  t.innerHTML=h+'</tbody>';
}

function toggleInvoiceForm(){const f=document.getElementById('invoiceForm');f.style.display=f.style.display==='none'?'block':'none';document.getElementById('invoiceFormMsg').textContent='';}

async function submitInvoice(){
  const data={year:parseInt(document.getElementById('inv-year').value),month:parseInt(document.getElementById('inv-month').value),kwh_hp:parseFloat(document.getElementById('inv-hp').value)||0,kwh_hpl:parseFloat(document.getElementById('inv-hpl').value)||0,kwh_hc:parseFloat(document.getElementById('inv-hc').value)||0,subscribed_power_kva:parseFloat(document.getElementById('inv-ps').value)||260,excess_power_penalty:parseFloat(document.getElementById('inv-rdps').value)||0,total_ttc:parseFloat(document.getElementById('inv-total').value)||0,notes:document.getElementById('inv-notes').value||null};
  const msg=document.getElementById('invoiceFormMsg');
  try{const r=await api.createInvoice(data);if(r.error){msg.innerHTML=`<span style="color:var(--red)">❌ ${r.error}</span>`;return;}msg.innerHTML=`<span style="color:var(--green)">✅ ${r.message}</span>`;setTimeout(()=>{toggleInvoiceForm();loadInvoices();},1500);}catch(e){msg.innerHTML=`<span style="color:var(--red)">❌ Erreur</span>`;}
}

// === SETTINGS ===
async function loadSettings(){
  try{const s=await api.getSettings();const map={tarifs_energie:'settings-tarifs_energie',puissance:'settings-puissance',compteur:'settings-compteur',rdps:'settings-rdps',correction:'settings-correction'};
  for(const[cat,id]of Object.entries(map)){const c=document.getElementById(id);if(!c||!s[cat])continue;c.innerHTML=s[cat].map(x=>`<div class="set-row" data-key="${x.key}"><div><div class="set-label">${x.label}</div><div class="set-unit">${x.unit||''}</div></div><input class="set-input" type="text" value="${x.value}" data-key="${x.key}" data-original="${x.value}" oninput="onSetChange(this)"/><button class="set-save" id="btn-${x.key}" onclick="saveSetting('${x.key}',this)">✓</button></div>`).join('');}}catch(e){}
}
function onSetChange(i){document.getElementById(`btn-${i.dataset.key}`).classList.toggle('visible',i.value!==i.dataset.original);}
async function saveSetting(k,btn){const input=document.querySelector(`input[data-key="${k}"]`);try{const r=await api.updateSetting(k,input.value);if(r.error){alert(r.error);return;}input.dataset.original=input.value;btn.classList.remove('visible');btn.closest('.set-row').style.background='rgba(16,185,129,0.05)';setTimeout(()=>btn.closest('.set-row').style.background='',1500);}catch(e){alert('Erreur');}}

// === CHARTS ===
function initMainChart(){
  mainChart = new Chart(document.getElementById('mainChart'),{type:'line',data:{labels:[],datasets:[
    {label:'Production PV',data:[],borderColor:'#d97706',backgroundColor:'rgba(217,119,6,0.05)',fill:true,tension:0.4,pointRadius:0,borderWidth:1.8},
    {label:'Consommation',data:[],borderColor:'#0284c7',backgroundColor:'rgba(2,132,199,0.05)',fill:true,tension:0.4,pointRadius:0,borderWidth:1.8},
    {label:'Import',data:[],borderColor:'#e11d48',backgroundColor:'rgba(225,29,72,0.03)',fill:true,tension:0.4,pointRadius:0,borderWidth:1.2,borderDash:[5,5]},
    {label:'Export',data:[],borderColor:'#ea580c',backgroundColor:'rgba(234,88,12,0.03)',fill:true,tension:0.4,pointRadius:0,borderWidth:1.2,borderDash:[3,3]}
  ]},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,font:{size:11},boxWidth:12,padding:12,usePointStyle:true,pointStyle:'circle'}},tooltip:{backgroundColor:'#fff',titleColor:'#111',bodyColor:'#555',borderColor:'rgba(0,0,0,0.08)',borderWidth:1,padding:12,cornerRadius:10,callbacks:{label:c=>`${c.dataset.label}: ${c.parsed.y.toFixed(1)} kW`}}},scales:{x:{grid:{color:GC},ticks:{color:TC,font:{size:10},maxTicksLimit:12}},y:{grid:{color:GC},ticks:{color:TC,font:{size:10},callback:v=>`${v} kW`}}}}});
}

async function loadHistory(){
  try{const d=await api.getHistory(currentPlantId,24);if(!d?.length)return;const ctx=document.getElementById('historyChart');if(historyChart)historyChart.destroy();
  historyChart=new Chart(ctx,{type:'line',data:{labels:d.map(r=>new Date(r.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})),datasets:[
    {label:'Production PV',data:d.map(r=>r.pv_power),borderColor:'#d97706',backgroundColor:'rgba(217,119,6,0.05)',fill:true,tension:0.35,pointRadius:0,borderWidth:1.8},
    {label:'Consommation',data:d.map(r=>r.consumption),borderColor:'#0284c7',backgroundColor:'rgba(2,132,199,0.05)',fill:true,tension:0.35,pointRadius:0,borderWidth:1.8},
    {label:'Export',data:d.map(r=>r.grid_export),borderColor:'#ea580c',backgroundColor:'rgba(234,88,12,0.03)',fill:true,tension:0.35,pointRadius:0,borderWidth:1.2,borderDash:[3,3]}
  ]},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,usePointStyle:true,pointStyle:'circle'}}},scales:{x:{grid:{color:GC},ticks:{color:TC,font:{size:10},maxTicksLimit:12}},y:{grid:{color:GC},ticks:{color:TC,callback:v=>`${v} kW`}}}}});}catch(e){}
}

// === PUSH ===
async function requestNotificationPermission(){
  if(!('Notification'in window))return;
  const p=await Notification.requestPermission();
  if(p==='granted'){
    document.getElementById('btnNotifPermission').textContent='✅ Notifications activées';
    document.getElementById('btnNotifPermission').style.background='linear-gradient(135deg,#10b981,#34d399)';
    if('serviceWorker'in navigator){
      const reg=await navigator.serviceWorker.register('/frontend/sw.js');
      try{const vapid=await api.getVapidKey();if(vapid.publicKey){const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:vapid.publicKey});await api.subscribePush(sub.toJSON());}}catch(e){console.log('Push sub error:',e);}
    }
  }
}

// === TIMER ===
function startRefresh(){
  refreshTimer=0;const bar=document.getElementById('refreshProgress');
  if(refreshInterval)clearInterval(refreshInterval);
  refreshInterval=setInterval(()=>{refreshTimer++;bar.style.width=`${Math.min((refreshTimer/REFRESH_SECONDS)*100,100)}%`;if(refreshTimer>=REFRESH_SECONDS){refreshTimer=0;bar.style.width='0%';updateDashboard();}},1000);
}

function fmt(v){return(v==null||v==='--')?'--':Number(v).toFixed(1);}
function fmtTime(s){if(!s)return'--';return new Date(s).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}

// === STATS PAGE (Jour/Mois/Année) ===
let statsView = 'day';
let statsDate = new Date();
let statsChart = null, statsDonutPV = null, statsDonutConso = null;

function setStatsView(v) {
  statsView = v;
  document.querySelectorAll('.stats-tab').forEach(t=>t.classList.remove('active'));
  document.querySelector(`.stats-tab[onclick*="${v}"]`)?.classList.add('active');
  statsDate = new Date();
  loadStatsPage();
}

function statsNav(dir) {
  if (statsView==='day') statsDate.setDate(statsDate.getDate()+dir);
  else if (statsView==='month') statsDate.setMonth(statsDate.getMonth()+dir);
  else statsDate.setFullYear(statsDate.getFullYear()+dir);
  loadStatsPage();
}

async function loadStatsPage() {
  const d = statsDate;
  let label = '';
  if (statsView==='day') label = d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit',year:'numeric'});
  else if (statsView==='month') label = d.toLocaleDateString('fr-FR',{month:'long',year:'numeric'});
  else label = d.getFullYear().toString();
  document.getElementById('statsLabel').textContent = label;

  if (statsView==='day') {
    const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    try {
      const s = await api.getDailySummary(currentPlantId, dateStr);
      if (s.error) { clearStatsKpis(); return; }
      const b = s.breakdown||{};
      document.getElementById('stats-pv').textContent = s.total_pv_kwh?.toFixed(0)||'0';
      document.getElementById('stats-conso').textContent = s.total_consumption_kwh?.toFixed(0)||'0';
      document.getElementById('stats-import').textContent = s.total_import_kwh?.toFixed(0)||'0';
      document.getElementById('stats-export').textContent = s.total_export_kwh?.toFixed(0)||'0';
      document.getElementById('stats-savings').textContent = s.total_savings_dh?.toFixed(0)||'0';
      document.getElementById('stats-cost').textContent = s.total_cost_dh?.toFixed(0)||'0';
      const exportLost = (s.total_export_kwh||0) * 1.01;
      document.getElementById('stats-lost').textContent = exportLost.toFixed(0);
      renderStatsDonuts(s);

      // Day chart from history
      const hist = await api.getHistory(currentPlantId, 24);
      renderStatsChart(hist?.map(r=>new Date(r.timestamp).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})), hist?.map(r=>r.pv_power), hist?.map(r=>r.consumption), 'kW');
    } catch(e) { clearStatsKpis(); }
  } else {
    // Month or Year - use aggregated data
    try {
      const year = d.getFullYear();
      const data = await fetch(`/api/v1/stats/monthly/${currentPlantId}?year=${year}`,{headers:getHeaders()}).then(r=>r.json());
      const months = data.months||{};
      if (statsView==='month') {
        const m = d.getMonth()+1;
        const md = months[m]||{};
        document.getElementById('stats-pv').textContent = (md.pv||0).toFixed(0);
        document.getElementById('stats-conso').textContent = (md.conso||0).toFixed(0);
        document.getElementById('stats-import').textContent = (md.import||0).toFixed(0);
        document.getElementById('stats-export').textContent = (md.export||0).toFixed(0);
        document.getElementById('stats-savings').textContent = (md.savings||0).toFixed(0);
        document.getElementById('stats-cost').textContent = (md.cost||0).toFixed(0);
        document.getElementById('stats-lost').textContent = ((md.export||0)*1.01).toFixed(0);
        renderStatsDonuts({total_pv_kwh:md.pv,total_consumption_kwh:md.conso,total_import_kwh:md.import,total_export_kwh:md.export,breakdown:{}});
      } else {
        let totPv=0,totConso=0,totImp=0,totExp=0,totSav=0,totCost=0;
        Object.values(months).forEach(m=>{totPv+=m.pv||0;totConso+=m.conso||0;totImp+=m.import||0;totExp+=m.export||0;totSav+=m.savings||0;totCost+=m.cost||0;});
        document.getElementById('stats-pv').textContent = totPv.toFixed(0);
        document.getElementById('stats-conso').textContent = totConso.toFixed(0);
        document.getElementById('stats-import').textContent = totImp.toFixed(0);
        document.getElementById('stats-export').textContent = totExp.toFixed(0);
        document.getElementById('stats-savings').textContent = totSav.toFixed(0);
        document.getElementById('stats-cost').textContent = totCost.toFixed(0);
        document.getElementById('stats-lost').textContent = (totExp*1.01).toFixed(0);
        renderStatsDonuts({total_pv_kwh:totPv,total_consumption_kwh:totConso,total_import_kwh:totImp,total_export_kwh:totExp,breakdown:{}});
      }
      // Chart by month
      const labels = MONTHS;
      const pvData = labels.map((_,i)=>(months[i+1]?.pv)||0);
      const consoData = labels.map((_,i)=>(months[i+1]?.conso)||0);
      renderStatsChart(labels, pvData, consoData, 'kWh');
    } catch(e) { clearStatsKpis(); }
  }
  if(typeof lucide!=='undefined')setTimeout(()=>lucide.createIcons(),100);
}

function clearStatsKpis() {
  ['stats-pv','stats-conso','stats-import','stats-export','stats-savings','stats-cost','stats-lost'].forEach(id=>document.getElementById(id).textContent='--');
}

function renderStatsDonuts(s) {
  const su = (s.total_pv_kwh||0)-(s.total_export_kwh||0);
  document.getElementById('stats-donut-pv').textContent = (s.total_pv_kwh||0).toFixed(0);
  document.getElementById('stats-donut-conso').textContent = (s.total_consumption_kwh||0).toFixed(0);
  if(statsDonutPV) statsDonutPV.destroy();
  statsDonutPV = new Chart(document.getElementById('statsDonutPV'),{type:'doughnut',data:{labels:['Autoconsommé','Exporté'],datasets:[{data:[su,s.total_export_kwh||0],backgroundColor:['#0d9488','#ea580c'],borderWidth:0,cutout:'75%'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  if(statsDonutConso) statsDonutConso.destroy();
  statsDonutConso = new Chart(document.getElementById('statsDonutConso'),{type:'doughnut',data:{labels:['Depuis PV','Importé'],datasets:[{data:[su,s.total_import_kwh||0],backgroundColor:['#0d9488','#e11d48'],borderWidth:0,cutout:'75%'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
}

function renderStatsChart(labels, pvData, consoData, unit) {
  if(statsChart) statsChart.destroy();
  if(!labels?.length) return;
  document.getElementById('statsChartTitle').textContent = statsView==='day'?'Production vs Consommation':'Production vs Consommation mensuelle';
  statsChart = new Chart(document.getElementById('statsChart'),{type:statsView==='day'?'line':'bar',data:{labels,datasets:[
    {label:'Production PV',data:pvData,borderColor:'#d97706',backgroundColor:statsView==='day'?'rgba(217,119,6,0.05)':'rgba(217,119,6,0.6)',fill:statsView==='day',tension:0.35,pointRadius:0,borderWidth:1.8,borderRadius:statsView==='day'?0:6},
    {label:'Consommation',data:consoData,borderColor:'#e11d48',backgroundColor:statsView==='day'?'rgba(225,29,72,0.04)':'rgba(225,29,72,0.6)',fill:statsView==='day',tension:0.35,pointRadius:0,borderWidth:1.8,borderRadius:statsView==='day'?0:6}
  ]},options:{...CHART_OPTS,plugins:{legend:{labels:{color:TC,usePointStyle:true,pointStyle:'circle'}}},scales:{x:{grid:{color:GC},ticks:{color:TC}},y:{grid:{color:GC},ticks:{color:TC,callback:v=>`${v} ${unit}`}}}}});
}

function getHeaders() {
  const token = localStorage.getItem('bbl_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

// === DARK MODE ===
function toggleDarkMode() {
  const isDark = document.documentElement.getAttribute('data-theme')==='dark';
  document.documentElement.setAttribute('data-theme', isDark?'':'dark');
  localStorage.setItem('bbl_theme', isDark?'light':'dark');
  document.getElementById('darkToggle').classList.toggle('active',!isDark);
}

function initTheme() {
  const saved = localStorage.getItem('bbl_theme');
  if (saved==='dark') {
    document.documentElement.setAttribute('data-theme','dark');
    document.getElementById('darkToggle')?.classList.add('active');
  }
}

// === USERS MANAGEMENT ===
async function loadUsers() {
  try {
    const users = await api.getUsers();
    const c = document.getElementById('usersList');
    if (!users?.length) { c.innerHTML='<div class="alert-none">Aucun utilisateur</div>'; return; }
    c.innerHTML = users.map(u => `
      <div class="user-row">
        <div class="user-info">
          <div class="user-name">${u.name}</div>
          <div class="user-email">${u.email}</div>
        </div>
        <span class="user-role ${u.role}">${u.role}</span>
        <div class="user-actions">
          <button class="btn-del" onclick="deleteUser(${u.id},'${u.name}')">Suppr</button>
        </div>
      </div>
    `).join('');
  } catch(e) { console.log('Users load error:', e); }
}

function toggleUserForm() {
  const f = document.getElementById('addUserForm');
  f.style.display = f.style.display==='none'?'block':'none';
  document.getElementById('userFormMsg').textContent = '';
}

async function addUser() {
  const data = {
    name: document.getElementById('newUserName').value,
    email: document.getElementById('newUserEmail').value,
    password: document.getElementById('newUserPwd').value,
    role: document.getElementById('newUserRole').value
  };
  const msg = document.getElementById('userFormMsg');
  if (!data.name||!data.email||!data.password) { msg.innerHTML='<span style="color:var(--red)">Remplir tous les champs</span>'; return; }
  try {
    const r = await fetch('/api/v1/auth/users',{method:'POST',headers:getHeaders(),body:JSON.stringify(data)});
    const d = await r.json();
    if (r.ok) { msg.innerHTML=`<span style="color:var(--green)">✅ ${d.message}</span>`; setTimeout(()=>{toggleUserForm();loadUsers();},1000); }
    else msg.innerHTML=`<span style="color:var(--red)">❌ ${d.detail||'Erreur'}</span>`;
  } catch(e) { msg.innerHTML='<span style="color:var(--red)">❌ Erreur</span>'; }
}

async function deleteUser(id, name) {
  if (!confirm(`Supprimer ${name} ?`)) return;
  try {
    await fetch(`/api/v1/auth/users/${id}`,{method:'DELETE',headers:getHeaders()});
    loadUsers();
  } catch(e) {}
}

// === INIT ===
async function init(){
  initTheme();
  if(!localStorage.getItem('bbl_token')){window.location.href='/login';return;}
  try{const p=await api.getPlants();if(p?.length)currentPlantId=p[0].id;}catch(e){}
  initMainChart();
  await loadMainChartHistory();
  await updateDashboard();
  startRefresh();
  if('serviceWorker'in navigator)navigator.serviceWorker.register('/frontend/sw.js').catch(()=>{});
  // Re-render Lucide icons for dynamic content
  setTimeout(()=>{if(typeof lucide!=='undefined')lucide.createIcons();},500);
}

document.addEventListener('DOMContentLoaded',init);
