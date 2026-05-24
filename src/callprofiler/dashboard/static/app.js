// CallProfiler Admin Panel
(function() {
    // ── Tab switching ────────────────────────────────────────────────────
    var tabs = document.querySelectorAll('#tab-nav .tab');
    var panels = document.querySelectorAll('.tab-panel');

    tabs.forEach(function(t) {
        t.addEventListener('click', function() {
            var tabName = this.dataset.tab;
            tabs.forEach(function(tb) { tb.classList.remove('active'); });
            this.classList.add('active');
            panels.forEach(function(p) {
                p.classList.remove('active');
                if (p.id === 'tab-' + tabName) p.classList.add('active');
            });
            if (tabName === 'characters') loadCharacters();
            if (tabName === 'analytics') loadAnalytics();
            if (tabName === 'tools') loadToolsStatus();
        });
    });

    // ── SSE / Live Feed ──────────────────────────────────────────────────
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

    var feedTitle = document.querySelector('#live-feed .section-header h2');
    function updateHeartbeat(hb) {
        if (feedTitle) feedTitle.textContent = 'Live Feed [' + (hb.last_id || 0) + ']';
    }
    setInterval(function() {
        if (countEl) {
            var n = feed ? feed.querySelectorAll('.card').length : 0;
            countEl.textContent = n + ' analyses';
        }
    }, 3000);

    function renderCard(a) {
        var empty = feed.querySelector('.empty-feed');
        if (empty) empty.remove();
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
            (a.summary ? '<div class="c-summary">' + esh(a.summary) + '</div>' : '') +
            '<div class="c-audio"><button class="btn-audio" onclick="window._playAudio(' + a.call_id + ', this)">&#9654;&#65039; Прослушать</button></div>';
        feed.insertBefore(card, feed.firstChild);
        while (feed.children.length > MAX) feed.lastChild.remove();
    }

    function updateStats(s) {
        var el;
        el = document.getElementById('s-calls'); if (el) el.textContent = fmt(s.total_calls);
        el = document.getElementById('s-entities'); if (el) el.textContent = fmt(s.total_entities);
        el = document.getElementById('s-portraits'); if (el) el.textContent = fmt(s.total_portraits);
        el = document.getElementById('s-risk');
        if (el && s.avg_risk != null) el.textContent = Math.round(s.avg_risk) + '%';
    }

    // ── Characters Tab ───────────────────────────────────────────────────
    var allChars = [];
    var activeCharId = null;

    function loadCharacters() {
        var list = document.getElementById('char-list');
        if (!list) return;
        if (list.children.length > 0 && list.children[0].className === 'char-item') return;
        list.innerHTML = '<div class="loading">загрузка...</div>';
        fetch('/api/characters').then(function(r) { return r.json(); }).then(function(data) {
            allChars = data || [];
            renderCharList(allChars);
            document.getElementById('char-count').textContent = allChars.length + ' персонажей';
        }).catch(function() {
            list.innerHTML = '<div class="nodata">Ошибка загрузки</div>';
        });
    }

    function renderCharList(chars) {
        var list = document.getElementById('char-list');
        if (!list) return;
        list.innerHTML = '';
        if (!chars.length) { list.innerHTML = '<div class="nodata">Нет персонажей</div>'; return; }
        chars.forEach(function(c) {
            var div = document.createElement('div');
            div.className = 'char-item';
            if (c.avg_risk && c.avg_risk >= 70) div.classList.add('char-risk-high');
            else if (c.avg_risk && c.avg_risk >= 40) div.classList.add('char-risk-med');
            if (c.entity_id === activeCharId) div.classList.add('active');
            div.innerHTML =
                '<div class="char-name">' + esh(c.canonical_name) + ' <span style="font-size:10px;color:var(--muted)">' + esh(c.entity_type) + '</span></div>' +
                '<div class="char-label">' + esh(c.character_label || '') + '</div>' +
                '<div class="char-meta">' +
                '<span>звонков: ' + (c.total_calls || 0) + '</span>' +
                '<span>риск: ' + (c.avg_risk != null ? Math.round(c.avg_risk) : '?') + '</span>' +
                '<span>BS: ' + (c.bs_index != null ? Math.round(c.bs_index) : '?') + '</span>' +
                '</div>';
            div.onclick = function() { showCharacter(c.entity_id, div); };
            list.appendChild(div);
        });
    }

    window.filterCharacters = function() {
        var q = (document.getElementById('char-search').value || '').toLowerCase();
        var filtered = allChars.filter(function(c) {
            var s = (c.canonical_name || '') + ' ' + (c.character_label || '') + ' ' + (c.entity_type || '');
            return s.toLowerCase().indexOf(q) >= 0;
        });
        renderCharList(filtered);
    };

    function showCharacter(entityId, el) {
        activeCharId = entityId;
        var items = document.querySelectorAll('#char-list .char-item');
        items.forEach(function(it) { it.classList.remove('active'); });
        if (el) el.classList.add('active');

        var body = document.getElementById('char-profile-body');
        body.innerHTML = '<div class="loading">загрузка...</div>';
        document.getElementById('char-profile-name').textContent = 'Загрузка...';

        fetch('/api/character/' + entityId).then(function(r) { return r.json(); }).then(function(p) {
            document.getElementById('char-profile-name').textContent = p.canonical_name || '?';
            renderCharacterProfile(p, body);
        }).catch(function() {
            body.innerHTML = '<div class="nodata">Ошибка загрузки</div>';
        });
    }

    function renderCharacterProfile(p, body) {
        var risk = p.avg_risk != null ? Math.round(p.avg_risk) : '?';
        var bs = p.bs_index != null ? Math.round(p.bs_index) : '?';
        var t = p.temperament || {};
        var bf = p.big_five || {};
        var mot = p.motivation || {};

        var html = '';

        // Summary
        if (p.character_summary) {
            html += '<div class="prof-section"><h4>Характеристика</h4><p>' + esh(p.character_summary) + '</p></div>';
        }

        // Key metrics
        html += '<div class="prof-section"><h4>Метрики</h4><div class="prof-grid">';
        html += kv('Риск', risk + '%'); html += kv('BS индекс', bs);
        html += kv('Звонков', p.total_calls || 0);
        html += kv('Тип', esh(p.entity_type || '?'));
        if (p.trust_score != null) html += kv('Доверие', Math.round(p.trust_score));
        if (p.volatility != null) html += kv('Волатильность', (p.volatility * 100).toFixed(0) + '%');
        if (p.conflict_count != null) html += kv('Конфликтов', p.conflict_count);
        html += '</div></div>';

        // Psychology
        if (t.type || Object.keys(bf).length) {
            html += '<div class="prof-section"><h4>Психология</h4><div class="prof-grid">';
            if (t.type) html += kv('Темперамент', t.type);
            if (t.energy) html += kv('Энергия', t.energy);
            if (t.reactivity) html += kv('Реактивность', t.reactivity);
            if (bf.openness != null) html += kv('Открытость', (bf.openness * 100).toFixed(0) + '%');
            if (bf.conscientiousness != null) html += kv('Сознательность', (bf.conscientiousness * 100).toFixed(0) + '%');
            if (bf.extraversion != null) html += kv('Экстраверсия', (bf.extraversion * 100).toFixed(0) + '%');
            if (bf.agreeableness != null) html += kv('Доброжелательность', (bf.agreeableness * 100).toFixed(0) + '%');
            if (bf.neuroticism != null) html += kv('Нейротизм', (bf.neuroticism * 100).toFixed(0) + '%');
            html += '</div></div>';
        }

        // Motivation
        if (mot.primary || (mot.drivers && mot.drivers.length)) {
            html += '<div class="prof-section"><h4>Мотивация</h4><p>';
            html += '<strong>' + esh(mot.primary || '?') + '</strong> ';
            if (mot.drivers) {
                mot.drivers.forEach(function(d) {
                    html += '<span class="tag">' + esh(d.driver) + ' ' + (d.weight ? (d.weight * 100).toFixed(0) + '%' : '') + '</span>';
                });
            }
            html += '</p></div>';
        }

        // Patterns
        if (p.patterns && p.patterns.length) {
            html += '<div class="prof-section"><h4>Поведенческие паттерны</h4><p>';
            p.patterns.forEach(function(pt) {
                var cls = pt.severity === 'positive' ? 'pattern-positive' :
                    pt.severity === 'high' ? 'pattern-high' :
                    pt.severity === 'medium' ? 'pattern-medium' : 'pattern-negative';
                var icon = pt.severity === 'positive' ? '&#10003;' : pt.severity === 'high' ? '&#9888;' : '&#9432;';
                html += '<span class="pattern-badge ' + cls + '">' + icon + ' ' + esh(pt.label || pt.name) + (pt.ratio != null ? ' (' + (pt.ratio * 100).toFixed(0) + '%)' : '') + '</span>';
            });
            html += '</p></div>';
        }

        // Contradictions
        if (p.contradictions && p.contradictions.length) {
            html += '<div class="prof-section"><h4>Противоречия</h4>';
            p.contradictions.forEach(function(cr) {
                html += '<p style="font-size:12px;margin-bottom:4px;padding:6px;background:var(--bg);border-radius:4px">';
                html += '<span style="color:var(--yellow)">' + esh(cr.severity) + '</span> ';
                html += '"' + esh((cr.quote_1 || '') + ' vs ' + (cr.quote_2 || '')) + '" ';
                html += '<span style="color:var(--muted);font-size:10px">' + cr.delta_days + 'д</span>';
                html += '</p>';
            });
            html += '</div>';
        }

        // Contact
        if (p.contact && p.contact.contact_id) {
            html += '<div class="prof-section"><h4>Контакт</h4>';
            html += '<p>Телефон: ' + esh(p.contact.phone_e164 || '?') + ' | ';
            html += 'Имя: ' + esh(p.contact.display_name || p.contact.guessed_name || '?');
            html += '</p></div>';
        }

        // Promises
        if (p.open_promises && p.open_promises.length) {
            html += '<div class="prof-section"><h4>Открытые обещания</h4>';
            p.open_promises.forEach(function(pr) {
                html += '<div class="promise-item">';
                html += '<div class="promise-what">' + esh(pr.what || '?') + '</div>';
                html += '<div class="promise-status">' + esh(pr.status || 'open') + (pr.due ? ' · до ' + pr.due : '') + '</div>';
                html += '</div>';
            });
            html += '</div>';
        }

        // Recent calls
        if (p.recent_calls && p.recent_calls.length) {
            html += '<div class="prof-section"><h4>Последние звонки</h4>';
            p.recent_calls.forEach(function(c) {
                var dt = (c.call_datetime || '').substring(0, 16);
                var cr = c.risk_score != null ? Math.round(c.risk_score) : '?';
                var crCls = c.risk_score >= 70 ? 'var(--red)' : c.risk_score >= 40 ? 'var(--yellow)' : 'var(--green)';
                html += '<div class="call-history-item">';
                html += '<span class="chi-date">' + dt + '</span>';
                html += '<span class="chi-summary">' + esh((c.summary || c.contact_label || '').substring(0, 80)) + '</span>';
                html += '<span class="chi-risk" style="color:' + crCls + '">' + cr + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        // Portrait
        if (p.prose) {
            html += '<div class="prof-section"><h4>Литературный портрет</h4>';
            html += '<div class="portrait-prose">' + esh(p.prose) + '</div>';
            if (p.traits && p.traits.length) {
                html += '<p style="margin-top:8px">';
                p.traits.forEach(function(tr) { html += '<span class="tag">' + esh(tr) + '</span>'; });
                html += '</p>';
            }
            html += '</div>';
        }

        body.innerHTML = html;
    }

    function kv(label, value) {
        return '<div class="prof-kv"><div class="kv-label">' + esh(label) + '</div><div class="kv-value">' + esh(String(value)) + '</div></div>';
    }

    // ── Analytics Tab ────────────────────────────────────────────────────
    var charts = {};

    function loadAnalytics() {
        var body = document.getElementById('tab-analytics');
        if (body.dataset.loaded === '1') return;
        body.dataset.loaded = '1';
        fetch('/api/analytics').then(function(r) { return r.json(); }).then(function(data) {
            renderAnalyticsCharts(data);
        }).catch(function() {}).then(function() {
            loadAnalyticsFromLocal();
        });
    }

    function loadAnalyticsFromLocal() {
        fetch('/api/analytics').then(function(r) { return r.json(); }).then(function(data) {
            renderAnalyticsCharts(data);
        }).catch(function(e) { console.log('Analytics endpoint not ready yet:', e); });
    }

    function renderAnalyticsCharts(data) {
        if (!data || !data.calls_by_day) return;
        destroyChart('chart-calls-by-day');
        destroyChart('chart-risk-dist');
        destroyChart('chart-top-calls');
        destroyChart('chart-top-risk');
        destroyChart('chart-temperament');
        destroyChart('chart-call-types');

        charts['calls_by_day'] = new Chart(document.getElementById('chart-calls-by-day'), barChart(
            data.calls_by_day.map(function(d) { return d.date; }),
            data.calls_by_day.map(function(d) { return d.count; }),
            'Звонки'
        ));
        charts['risk_dist'] = new Chart(document.getElementById('chart-risk-dist'), doughnutChart(
            ['0-20', '20-40', '40-60', '60-80', '80-100'],
            data.risk_distribution
        ));
        charts['top_calls'] = new Chart(document.getElementById('chart-top-calls'), hbarChart(
            (data.top_contacts_by_calls || []).map(function(d) { return d.name; }),
            (data.top_contacts_by_calls || []).map(function(d) { return d.count; }),
            'Звонков'
        ));
        charts['top_risk'] = new Chart(document.getElementById('chart-top-risk'), hbarChart(
            (data.top_contacts_by_risk || []).map(function(d) { return d.name; }),
            (data.top_contacts_by_risk || []).map(function(d) { return d.avg_risk; }),
            'Ср.риск'
        ));
        charts['temperament'] = new Chart(document.getElementById('chart-temperament'), doughnutChart(
            Object.keys(data.temperament_distribution || {}),
            Object.values(data.temperament_distribution || {})
        ));
        charts['call_types'] = new Chart(document.getElementById('chart-call-types'), doughnutChart(
            Object.keys(data.call_type_distribution || {}),
            Object.values(data.call_type_distribution || {})
        ));
    }

    function destroyChart(id) {
        if (charts[id]) { charts[id].destroy(); delete charts[id]; }
    }

    function barChart(labels, data, label) {
        return { type: 'bar', data: { labels: labels, datasets: [{ label: label, data: data, backgroundColor: '#3b82f6', borderRadius: 4 }] }, options: chartOptions() };
    }
    function hbarChart(labels, data, label) {
        return { type: 'bar', data: { labels: labels, datasets: [{ label: label, data: data, backgroundColor: '#8b5cf6', borderRadius: 4 }] }, options: hbarOptions() };
    }
    function doughnutChart(labels, data) {
        return { type: 'doughnut', data: { labels: labels, datasets: [{ data: data, backgroundColor: ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316'] }] }, options: doughnutOptions() };
    }
    function chartOptions() {
        return { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8', maxTicksLimit: 12 }, grid: { display: false } }, y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } } } };
    }
    function hbarOptions() {
        return { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }, y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } } } };
    }
    function doughnutOptions() {
        return { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 } } } } };
    }

    // ── Tools Tab ────────────────────────────────────────────────────────
    function loadToolsStatus() {
        var body = document.getElementById('tools-status-body');
        if (!body) return;
        fetch('/api/stats').then(function(r) { return r.json(); }).then(function(s) {
            body.innerHTML =
                '<table class="status-table">' +
                '<tr><td>Всего звонков</td><td>' + fmt(s.total_calls) + '</td></tr>' +
                '<tr><td>Персонажей</td><td>' + fmt(s.total_entities) + '</td></tr>' +
                '<tr><td>Портретов</td><td>' + fmt(s.total_portraits) + '</td></tr>' +
                '<tr><td>Средний риск</td><td>' + (s.avg_risk != null ? Math.round(s.avg_risk) + '%' : '?') + '</td></tr>' +
                '</table>';
        }).catch(function() {
            body.innerHTML = '<div class="nodata">Ошибка загрузки</div>';
        });
    }

    window.toolAction = function(url) {
        var btns = document.querySelectorAll('.tool-btn');
        btns.forEach(function(b) { b.disabled = true; });
        var log = document.getElementById('tools-log-body');
        log.innerHTML = '<div class="loading">выполнение...</div>';
        fetch(url, { method: 'POST' }).then(function(r) { return r.json(); }).then(function(res) {
            log.innerHTML = '<div class="tool-msg ' + (res.status === 'ok' ? '' : 'error') + '">' +
                new Date().toLocaleTimeString() + ' · ' + esh(res.message || 'OK') + '</div>' + log.innerHTML;
            btns.forEach(function(b) { b.disabled = false; });
        }).catch(function() {
            log.innerHTML = '<div class="tool-msg error">' + new Date().toLocaleTimeString() + ' · Ошибка</div>' + log.innerHTML;
            btns.forEach(function(b) { b.disabled = false; });
        });
    };

    // ── Shutdown ──────────────────────────────────────────────────────────
    window.doShutdown = function() {
        if (!confirm('Stop dashboard server and close?')) return;
        fetch('/api/shutdown').then(function() {
            document.body.innerHTML = '<div style="color:#10b981;text-align:center;padding:100px;font-size:24px">Server stopped. You may close this tab.</div>';
            setTimeout(function() { window.close(); }, 2000);
        }).catch(function() {});
    };

    // ── Entity Profile (live feed modal) ──────────────────────────────────
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
                        '<p class="hint">Full profile: switch to Characters tab</p>' +
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

    // ── Audio player ──────────────────────────────────────────────────────
    window._playAudio = function(callId, el) {
        var audio = new Audio('/api/audio/' + callId);
        audio.onerror = function() { el.textContent = 'err'; };
        audio.onended = function() { el.textContent = '\u25b6\ufe0f \u041f\u0440\u043e\u0441\u043b\u0443\u0448\u0430\u0442\u044c'; };
        audio.play();
        el.textContent = '\u23f8\ufe0f ...';
    };

    // ── Helpers ───────────────────────────────────────────────────────────
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
