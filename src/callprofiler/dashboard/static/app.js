// CallProfiler Dashboard — Live Analysis Feed
(function() {
    var MAX = 100;
    var feed = document.getElementById('feed-container');
    var countEl = document.getElementById('feed-count');
    var connEl = document.getElementById('connection-dot');
    var txtEl = document.getElementById('connection-text');

    var es = new EventSource('/events/stream');

    es.addEventListener('open', function() {
        connEl.className = 'dot connected';
        txtEl.textContent = 'live';
    });

    es.addEventListener('error', function() {
        connEl.className = 'dot disconnected';
        txtEl.textContent = 'reconnecting...';
    });

    es.addEventListener('message', function(e) {
        try {
            var evt = JSON.parse(e.data);
            if (evt.type === 'analysis') renderCard(evt);
            if (evt.type === 'stats' && evt.data) updateStats(evt.data);
            if (evt.type === 'heartbeat') updateHeartbeat(evt);
        } catch(ex) { console.error(ex); }
    });

    var pollTimer = null;
    var pollSec = 0;
    var feedTitle = document.querySelector('#live-feed .section-header h2');

    function updateHeartbeat(hb) {
        pollSec = 0;
        if (feedTitle) feedTitle.textContent = 'Live Feed [' + (hb.last_id || 0) + ']';
    }

    // Countdown refresh indicator
    setInterval(function() {
        pollSec += 1;
        if (countEl) countEl.textContent = 'refresh in ' + (Math.max(5 - pollSec, 0)) + 's';
        if (pollSec >= 5) {
            pollSec = 0;
            if (countEl) countEl.textContent = 'polling...';
        }
    }, 1000);

    function renderCard(a) {
        var card = document.createElement('div');
        card.className = 'card';

        var statusIcon = a.parse_status === 'parsed_ok' ? 'OK' : (a.parse_status || '?');
        var statusCls = a.parse_status === 'parsed_ok' ? 'ok' : 'partial';
        var riskEmoji = a.risk_score >= 70 ? 'R' : a.risk_score >= 40 ? 'W' : 'G';
        var riskCls = a.risk_score >= 70 ? 'risk-high' : a.risk_score >= 40 ? 'risk-med' : 'risk-low';
        var dur = a.duration_sec ? (Math.floor(a.duration_sec/60)+'m'+a.duration_sec%60+'s') : '?';
        var dir = a.direction === 'IN' ? 'IN' : a.direction === 'OUT' ? 'OUT' : '?';
        var ts = a.created_at ? a.created_at.substring(11, 19) : '--:--:--';
        var callDate = a.call_datetime ? a.call_datetime.substring(0, 10) : '?';
        var model = (a.model || '').substring(0, 15) || 'local';
        var src = (a.source_filename || '').substring(0, 40) || '?';

        card.innerHTML =
            '<div class="c-top">' +
            '<span class="c-id">#' + a.call_id + '</span>' +
            '<span class="c-contact" onclick="window._openProfile(\'' + esc(a.contact) + '\')">' + esh(a.contact) + '</span>' +
            '<span class="c-badge ' + statusCls + '">' + statusIcon + '</span>' +
            '<span class="c-risk ' + riskCls + '">' + riskEmoji + ' ' + a.risk_score + '</span>' +
            '<span class="c-type">' + esh(a.call_type || '?') + '</span>' +
            '<span class="c-dir">' + dir + '</span>' +
            '<span class="c-time">' + ts + '</span>' +
            '</div>' +
            '<div class="c-meta">' +
            '<span>date: ' + callDate + '</span>' +
            '<span>dur: ' + dur + '</span>' +
            '<span>model: ' + model + '</span>' +
            '<span>src: ' + src + '</span>' +
            '<span>schema: ' + esh(a.schema_version || 'v2') + '</span>' +
            '</div>' +
            (a.summary ? '<div class="c-summary">' + esh(a.summary) + '</div>' : '');

        feed.insertBefore(card, feed.firstChild);
        while (feed.children.length > MAX) feed.lastChild.remove();
        if (countEl) countEl.textContent = feed.children.length + ' analyses';
    }

    function updateStats(s) {
        var el;
        el = document.getElementById('s-calls'); if (el) el.textContent = fmt(s.total_calls);
        el = document.getElementById('s-entities'); if (el) el.textContent = fmt(s.total_entities);
        el = document.getElementById('s-portraits'); if (el) el.textContent = fmt(s.total_portraits);
        el = document.getElementById('s-risk');
        if (el && s.avg_risk != null) el.textContent = Math.round(s.avg_risk) + '%';
    }

    // ── Shutdown ────────────────────────────────────────────────────────
    window.doShutdown = function() {
        if (!confirm('Stop dashboard server and close?')) return;
        fetch('/api/shutdown').then(function() {
            document.body.innerHTML = '<div style=\"color:#10b981;text-align:center;padding:100px;font-size:24px\">Server stopped. You may close this tab.</div>';
            setTimeout(function() { window.close(); }, 2000);
        }).catch(function() {});
    };

    // ── Entity Profile ──────────────────────────────────────────────────
    window._openProfile = function(name) {
        if (!name || name === '?') return;
        document.getElementById('modal-name').textContent = name;
        document.getElementById('modal-overlay').style.display = 'flex';
        document.getElementById('modal-body').innerHTML = '<div class="loading">loading...</div>';

        fetch('/api/history?limit=300')
            .then(function(r) { return r.json(); })
            .then(function(hist) {
                var m = null;
                for (var i = 0; i < hist.length; i++) {
                    if (hist[i].contact_label && hist[i].contact_label.indexOf(name) >= 0) {
                        m = hist[i]; break;
                    }
                }
                if (m) {
                    document.getElementById('modal-body').innerHTML =
                        '<div class="prof">' +
                        '<p><b>Contact:</b> ' + esh(name) + '</p>' +
                        '<p><b>Call type:</b> ' + esh(m.call_type || '?') + '</p>' +
                        '<p><b>Risk:</b> ' + m.risk_score + '</p>' +
                        '<p><b>Last call:</b> ' + (m.call_datetime || '').substring(0, 16) + '</p>' +
                        '<p class="hint">Full profile: run graph-backfill + profile-all</p>' +
                        '</div>';
                } else {
                    document.getElementById('modal-body').innerHTML = '<div class="nodata">not found</div>';
                }
            })
            .catch(function() {
                document.getElementById('modal-body').innerHTML = '<div class="nodata">error</div>';
            });
    };

    document.getElementById('modal-close').onclick = function() {
        document.getElementById('modal-overlay').style.display = 'none';
    };
    document.getElementById('modal-overlay').onclick = function(e) {
        if (e.target === document.getElementById('modal-overlay')) {
            document.getElementById('modal-overlay').style.display = 'none';
        }
    };

    // ── Helpers ─────────────────────────────────────────────────────────
    function fmt(n) {
        if (n == null) return '--';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
        return String(n);
    }
    function esh(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function esc(s) {
        if (!s) return '';
        return s.replace(/'/g, "\\'").replace(/"/g, '\\"');
    }
})();