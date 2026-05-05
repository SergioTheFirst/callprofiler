const MAX_EVENTS = 100;
const es = new EventSource('/events/stream');
es.onopen = () => { dot('connected','live'); };
es.onerror = () => { dot('disconnected','reconnecting...'); };
es.onmessage = (e) => { try { handleEvent(JSON.parse(e.data)); } catch(ex) {} };

function dot(cls, txt) {
    document.getElementById('connection-dot').className = 'dot '+cls;
    document.getElementById('connection-text').textContent = txt;
}

function handleEvent(evt) {
    if (evt.type === 'analysis') addCard(evt);
    if (evt.type === 'stats' && evt.data) updateStats(evt.data);
}

const feed = document.getElementById('feed-container');

function addCard(a) {
    const card = document.createElement('div');
    card.className = 'card';
    const st = a.parse_status === 'parsed_ok' ? 'OK' : (a.parse_status||'?');
    const sc = a.parse_status === 'parsed_ok' ? 'ok' : 'partial';
    const ri = a.risk_score >= 70 ? 'R' : a.risk_score >= 40 ? 'W' : 'G';
    const rc = a.risk_score >= 70 ? 'risk-high' : a.risk_score >= 40 ? 'risk-med' : 'risk-low';
    const dur = a.duration_sec ? Math.floor(a.duration_sec/60)+'m'+a.duration_sec%60+'s' : '?';
    const di = a.direction === 'IN' ? 'IN' : a.direction === 'OUT' ? 'OUT' : '?';
    const ts = a.created_at ? a.created_at.substring(11,19) : '--:--:--';
    const callDate = a.call_datetime ? a.call_datetime.substring(0,10) : '?';
    const m = (a.model||'').substring(0,15) || 'local';
    const src = (a.source_filename||'').substring(0,40) || '?';
    card.innerHTML =
        '<div class="c-top"><span class="c-id">#'+a.call_id+'</span>'+
        '<span class="c-contact" onclick="findProfile(\''+esc(a.contact)+'\')">'+esh(a.contact)+'</span>'+
        '<span class="c-badge '+sc+'">'+st+'</span>'+
        '<span class="c-risk '+rc+'">'+ri+' '+a.risk_score+'</span>'+
        '<span class="c-type">'+esh(a.call_type||'?')+'</span>'+
        '<span class="c-dir">'+di+'</span>'+
        '<span class="c-time">'+ts+'</span></div>'+
        '<div class="c-meta">'+
        '<span>date: '+callDate+'</span>'+
        '<span>dur: '+dur+'</span>'+
        '<span>model: '+m+'</span>'+
        '<span>src: '+src+'</span>'+
        '<span>schema: '+esh(a.schema_version||'v2')+'</span></div>'+
        (a.summary ? '<div class="c-summary">'+esh(a.summary)+'</div>' : '');
    feed.prepend(card);
    while (feed.children.length > MAX_EVENTS) feed.lastChild.remove();
}

function updateStats(s) {
    document.getElementById('s-calls').textContent = fmt(s.total_calls);
    document.getElementById('s-entities').textContent = fmt(s.total_entities);
    document.getElementById('s-portraits').textContent = fmt(s.total_portraits);
    if (s.avg_risk != null) document.getElementById('s-risk').textContent = Math.round(s.avg_risk)+'%';
}

async function doShutdown() {
    if (!confirm('Stop dashboard server and close?')) return;
    try { await fetch('/api/shutdown'); } catch(ex) {}
    window.close();
}

async function findProfile(name) {
    if (!name || name==='?') return;
    document.getElementById('modal-name').textContent = name;
    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('modal-body').innerHTML = '<div class="loading">loading...</div>';
    try {
        const r = await fetch('/api/history?limit=300');
        const h = await r.json();
        const m = h.find(x => x.contact_label && x.contact_label.indexOf(name)>=0);
        if (m) {
            document.getElementById('modal-body').innerHTML =
                '<div class="prof"><p><b>Contact:</b> '+esh(name)+'</p>'+
                '<p><b>Call type:</b> '+esh(m.call_type||'?')+'</p>'+
                '<p><b>Risk:</b> '+m.risk_score+'</p>'+
                '<p><b>Last call:</b> '+(m.call_datetime||'').substring(0,16)+'</p>'+
                '<p class="hint">Full profile: run graph-backfill + profile-all</p></div>';
        } else { document.getElementById('modal-body').innerHTML = '<div class="nodata">not found</div>'; }
    } catch(ex) { document.getElementById('modal-body').innerHTML = '<div class="nodata">error</div>'; }
}

document.getElementById('modal-close').onclick = () => document.getElementById('modal-overlay').style.display = 'none';
document.getElementById('modal-overlay').onclick = e => { if(e.target===e.currentTarget) document.getElementById('modal-overlay').style.display='none'; };

function fmt(n) { return n==null?'--':n>=1000?(n/1000).toFixed(1)+'k':String(n); }
function esh(s) { if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function esc(s) { return s?s.replace(/'/g,"\\'").replace(/"/g,'\\"'):''; }