// CallProfiler Dashboard v3.0.0 — Glass-Industrial Command Center
(function() {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────
    var state = {
        activeTab: 'overview',
        sseConnected: false,
        callsPage: 0,
        callsLimit: 50,
        searchQuery: '',
    };

    // ── DOM refs ───────────────────────────────────────────────────────────
    var $ = function(sel) { return document.querySelector(sel); };
    var $$ = function(sel) { return document.querySelectorAll(sel); };

    var tabs = $$('#tab-nav .tab');
    var panels = $$('.tab-panel');
    var sseDot = $('#sse-dot');
    var clock = $('#clock');

    // ── Tab Switching ──────────────────────────────────────────────────────
    function switchTab(name) {
        state.activeTab = name;
        tabs.forEach(function(t) { t.classList.toggle('active', t.dataset.tab === name); });
        panels.forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + name); });
        location.hash = name;
        if (name === 'overview') loadOverview();
        else if (name === 'calls') loadCalls();
        else if (name === 'entities') loadEntities();
        else if (name === 'system') loadSystem();
    }

    tabs.forEach(function(t) {
        t.addEventListener('click', function() { switchTab(this.dataset.tab); });
    });

    // Restore tab from URL hash
    var hash = location.hash.replace('#', '');
    if (hash && $('#panel-' + hash)) switchTab(hash);

    // ── Clock ──────────────────────────────────────────────────────────────
    function updateClock() {
        var now = new Date();
        var h = String(now.getHours()).padStart(2, '0');
        var m = String(now.getMinutes()).padStart(2, '0');
        var s = String(now.getSeconds()).padStart(2, '0');
        clock.textContent = h + ':' + m + ':' + s;
    }
    updateClock();
    setInterval(updateClock, 1000);

    // ── SSE ────────────────────────────────────────────────────────────────
    function connectSSE() {
        var es = new EventSource('/api/sse');
        es.onopen = function() {
            state.sseConnected = true;
            sseDot.className = 'sse-indicator connected';
            sseDot.title = 'SSE connected';
        };
        es.onmessage = function(evt) {
            try {
                var data = JSON.parse(evt.data);
                if (data.type === 'tick' && state.activeTab === 'overview') {
                    updateStatCards(data.status);
                    addFeedItem(data.status);
                }
            } catch (e) { /* ignore parse errors */ }
        };
        es.onerror = function() {
            state.sseConnected = false;
            sseDot.className = 'sse-indicator disconnected';
            sseDot.title = 'SSE disconnected — reconnecting...';
            es.close();
            setTimeout(connectSSE, 5000);
        };
    }
    connectSSE();

    // ── Overview ───────────────────────────────────────────────────────────
    function loadOverview() {
        fetch('/api/overview')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                updateStatCards(data.status || data);
                renderPipeline(data.status || data);
                if (typeof echarts !== 'undefined') {
                    renderTrendChart();
                    renderDistChart();
                }
            })
            .catch(function(e) { console.error('Overview load failed:', e); });
    }

    function updateStatCards(status) {
        var total = (status.processed || 0) + (status.pending || 0) + (status.error || 0);
        var cards = $$('#stat-cards .stat-card');
        var values = [
            total,
            status.pending || 0,
            status.error || 0,
            status.processed || 0,
        ];
        cards.forEach(function(card, i) {
            card.classList.remove('skeleton');
            card.querySelector('.stat-value').textContent = values[i];
        });
    }

    function renderPipeline(status) {
        var steps = ['new', 'normalizing', 'transcribing', 'diarizing', 'analyzing', 'done'];
        var labels = ['New', 'Norm', 'Transcribe', 'Diarize', 'Analyze', 'Done'];
        var stepper = $('#pipeline-stepper');
        stepper.classList.remove('skeleton');
        var html = '';
        steps.forEach(function(s, i) {
            var count = status[s] || 0;
            var cls = 'pipe-dot';
            if (s === 'error' && count > 0) cls += ' error';
            else if (count > 0 && s === 'done') cls += ' active';
            html += '<div class="pipe-step">';
            html += '<div class="' + cls + '"></div>';
            html += '<span class="pipe-count">' + count + '</span>';
            html += '<span class="pipe-label">' + labels[i] + '</span>';
            html += '</div>';
        });
        stepper.innerHTML = html;
    }

    var feedItems = [];
    function addFeedItem(status) {
        var now = new Date();
        var time = String(now.getHours()).padStart(2, '0') + ':' +
                   String(now.getMinutes()).padStart(2, '0') + ':' +
                   String(now.getSeconds()).padStart(2, '0');
        var msg = 'Processed: ' + (status.processed || 0) +
                  ' | Pending: ' + (status.pending || 0) +
                  ' | Errors: ' + (status.error || 0);
        feedItems.unshift({ time: time, msg: msg, cls: status.error > 0 ? 'err' : 'ok' });
        if (feedItems.length > 20) feedItems.length = 20;
        var feed = $('#realtime-feed');
        feed.innerHTML = feedItems.map(function(item) {
            return '<div class="feed-item">' +
                   '<span class="feed-dot ' + item.cls + '"></span>' +
                   '<span class="feed-time">' + item.time + '</span>' +
                   '<span class="feed-msg">' + item.msg + '</span>' +
                   '</div>';
        }).join('');
    }

    // ECharts trend chart
    function renderTrendChart() {
        var el = $('#chart-trend');
        if (!el) return;
        var chart = echarts.init(el);
        var days = [];
        for (var i = 6; i >= 0; i--) {
            var d = new Date();
            d.setDate(d.getDate() - i);
            days.push(d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        }
        chart.setOption({
            grid: { top: 10, right: 16, bottom: 24, left: 44 },
            xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            series: [{
                data: [0, 0, 0, 0, 0, 0, 0],
                type: 'line',
                smooth: true,
                symbol: 'circle',
                symbolSize: 6,
                lineStyle: { color: '#00D4C8', width: 2 },
                itemStyle: { color: '#00D4C8' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(0,212,200,0.2)' },
                        { offset: 1, color: 'rgba(0,212,200,0)' }
                    ])
                }
            }]
        });
        // Fetch real data
        fetch('/api/calls?limit=7&offset=0')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var counts = [0, 0, 0, 0, 0, 0, 0];
                if (data.calls) {
                    data.calls.forEach(function(c) {
                        if (c.created_at) {
                            var callDate = new Date(c.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                            var idx = days.indexOf(callDate);
                            if (idx >= 0) counts[idx]++;
                        }
                    });
                }
                chart.setOption({ series: [{ data: counts }] });
            })
            .catch(function() {});
        window.addEventListener('resize', function() { chart.resize(); });
    }

    // ECharts distribution chart
    function renderDistChart() {
        var el = $('#chart-dist');
        if (!el) return;
        var chart = echarts.init(el);
        chart.setOption({
            tooltip: { trigger: 'item' },
            legend: { bottom: 0, textStyle: { color: '#8B95A5', fontSize: 10 } },
            series: [{
                type: 'pie',
                radius: ['45%', '72%'],
                center: ['50%', '46%'],
                itemStyle: { borderColor: '#060B16', borderWidth: 2 },
                label: { color: '#8B95A5', fontSize: 10 },
                data: [
                    { value: 1, name: 'Incoming', itemStyle: { color: '#00D4C8' } },
                    { value: 1, name: 'Outgoing', itemStyle: { color: '#00A8FF' } },
                    { value: 1, name: 'Missed', itemStyle: { color: '#FFB800' } },
                    { value: 1, name: 'Unknown', itemStyle: { color: '#4A5568' } },
                ]
            }]
        });
        // Fetch real data
        fetch('/api/calls?limit=500&offset=0')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var dist = { incoming: 0, outgoing: 0, missed: 0, unknown: 0 };
                if (data.calls) {
                    data.calls.forEach(function(c) {
                        var t = (c.direction || '').toLowerCase();
                        if (t === 'incoming' || t === 'in') dist.incoming++;
                        else if (t === 'outgoing' || t === 'out') dist.outgoing++;
                        else if (t === 'missed') dist.missed++;
                        else dist.unknown++;
                    });
                }
                chart.setOption({ series: [{ data: [
                    { value: dist.incoming || 0, name: 'Incoming', itemStyle: { color: '#00D4C8' } },
                    { value: dist.outgoing || 0, name: 'Outgoing', itemStyle: { color: '#00A8FF' } },
                    { value: dist.missed || 0, name: 'Missed', itemStyle: { color: '#FFB800' } },
                    { value: dist.unknown || 0, name: 'Unknown', itemStyle: { color: '#4A5568' } },
                ]}]});
            })
            .catch(function() {});
        window.addEventListener('resize', function() { chart.resize(); });
    }

    // ── Calls Tab ──────────────────────────────────────────────────────────
    function loadCalls(page) {
        if (page === undefined) page = state.callsPage;
        state.callsPage = page;
        var offset = page * state.callsLimit;
        fetch('/api/calls?limit=' + state.callsLimit + '&offset=' + offset)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                renderCallsTable(data.calls || []);
                $('#calls-page').textContent = 'Page ' + (page + 1);
                $('#calls-prev').disabled = page === 0;
            })
            .catch(function(e) { console.error('Calls load failed:', e); });
    }

    function renderCallsTable(calls) {
        var tbody = $('#calls-table tbody');
        if (calls.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text-muted);text-align:center">No calls found</td></tr>';
            return;
        }
        tbody.innerHTML = calls.map(function(c) {
            var created = c.created_at ? new Date(c.created_at).toLocaleString() : '--';
            var contact = c.display_name || c.phone_e164 || '--';
            var duration = c.duration_sec ? Math.floor(c.duration_sec / 60) + 'm ' + (c.duration_sec % 60) + 's' : '--';
            var status = c.status || '--';
            var risk = c.risk_score != null ? c.risk_score : '--';
            var cls = risk > 0.6 ? 'risk-high' : (risk > 0.3 ? 'risk-med' : 'risk-low');
            var type = c.direction || '--';
            var summary = c.summary ? c.summary.substring(0, 80) : '--';
            var badge = status === 'done' ? 'badge-done' : (status === 'error' ? 'badge-error' : 'badge-pending');
            if (status === 'processing' || status === 'analyzing' || status === 'transcribing' || status === 'diarizing') badge = 'badge-processing';
            return '<tr>' +
                '<td>' + (c.call_id || '--') + '</td>' +
                '<td>' + created + '</td>' +
                '<td>' + contact + '</td>' +
                '<td>' + duration + '</td>' +
                '<td><span class="badge ' + badge + '">' + status + '</span></td>' +
                '<td><span class="risk ' + cls + '">' + risk + '</span></td>' +
                '<td>' + type + '</td>' +
                '<td>' + summary + '</td>' +
                '</tr>';
        }).join('');
    }

    $('#calls-prev').addEventListener('click', function() {
        if (state.callsPage > 0) loadCalls(state.callsPage - 1);
    });
    $('#calls-next').addEventListener('click', function() {
        loadCalls(state.callsPage + 1);
    });
    $('#calls-export').addEventListener('click', function() {
        toast('CSV export coming soon', '');
    });

    // ── Search Tab ─────────────────────────────────────────────────────────
    $('#search-btn').addEventListener('click', function() {
        var q = $('#search-input').value.trim();
        if (!q) return;
        state.searchQuery = q;
        fetch('/api/search?q=' + encodeURIComponent(q) + '&limit=20')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                renderSearchResults(data.results || []);
            })
            .catch(function(e) { console.error('Search failed:', e); });
    });
    $('#search-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') $('#search-btn').click();
    });

    function renderSearchResults(results) {
        var el = $('#search-results');
        if (results.length === 0) {
            el.innerHTML = '<div class="empty-state">No results found for "' + state.searchQuery + '"</div>';
            return;
        }
        el.innerHTML = results.map(function(r) {
            return '<div class="feed-item" style="cursor:pointer">' +
                '<span class="feed-dot ok"></span>' +
                '<span class="feed-msg"><strong>' + (r.snippet || r.text || '--') + '</strong></span>' +
                '</div>';
        }).join('');
    }

    // ── Entities Tab ───────────────────────────────────────────────────────
    function loadEntities() {
        fetch('/api/entities?limit=100')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                renderEntitiesTable(data.entities || []);
            })
            .catch(function(e) { console.error('Entities load failed:', e); });
    }

    function renderEntitiesTable(entities) {
        var tbody = $('#entities-table tbody');
        if (entities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">No entities found</td></tr>';
            return;
        }
        tbody.innerHTML = entities.map(function(e) {
            return '<tr>' +
                '<td>' + (e.display_name || e.phone_e164 || '--') + '</td>' +
                '<td>' + (e.entity_type || '--') + '</td>' +
                '<td>' + (e.call_count || 0) + '</td>' +
                '<td>' + (e.bs_index != null ? e.bs_index.toFixed(2) : '--') + '</td>' +
                '<td>' + (e.risk_score != null ? '<span class="risk ' + (e.risk_score > 0.6 ? 'risk-high' : (e.risk_score > 0.3 ? 'risk-med' : 'risk-low')) + '">' + e.risk_score.toFixed(2) + '</span>' : '--') + '</td>' +
                '<td>' + (e.last_seen || '--') + '</td>' +
                '</tr>';
        }).join('');
    }

    // ── System Tab ─────────────────────────────────────────────────────────
    function loadSystem() {
        fetch('/api/system')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                $('#sys-metrics').innerHTML =
                    '<div class="sys-row"><span class="sys-label">CPU</span><span class="sys-value">' + data.cpu_percent + '%</span></div>' +
                    '<div class="sys-row"><span class="sys-label">RAM</span><span class="sys-value">' + data.ram.used_gb + ' / ' + data.ram.total_gb + ' GB</span></div>' +
                    '<div class="sys-row"><span class="sys-label">Disk</span><span class="sys-value">' + data.disk.used_gb + ' / ' + data.disk.total_gb + ' GB</span></div>' +
                    '<div class="sys-row"><span class="sys-label">Version</span><span class="sys-value">' + data.version + '</span></div>';
                $('#sys-db').innerHTML =
                    '<div class="sys-row"><span class="sys-label">DB Path</span><span class="sys-value">' + data.db_path + '</span></div>';
                $('#footer-api').textContent = 'API v' + data.version + ' ● healthy';
                $('#footer-db').textContent = 'DB: ' + data.db_path.split('\\').slice(-2).join('\\');
            })
            .catch(function(e) { console.error('System load failed:', e); });
    }

    // ── Command Palette ────────────────────────────────────────────────────
    var commands = [
        { name: 'Go to Overview', shortcut: '1', action: function() { switchTab('overview'); } },
        { name: 'Go to Calls', shortcut: '2', action: function() { switchTab('calls'); } },
        { name: 'Go to Search', shortcut: '3', action: function() { switchTab('search'); } },
        { name: 'Go to Entities', shortcut: '4', action: function() { switchTab('entities'); } },
        { name: 'Go to System', shortcut: '5', action: function() { switchTab('system'); } },
        { name: 'Focus Search', shortcut: '/', action: function() { switchTab('search'); setTimeout(function() { $('#search-input').focus(); }, 100); } },
    ];

    function openCmdPalette() {
        var overlay = $('#cmd-overlay');
        var input = $('#cmd-input');
        var results = $('#cmd-results');
        overlay.classList.add('open');
        input.value = '';
        input.focus();
        renderCmdResults('');
    }

    function closeCmdPalette() {
        $('#cmd-overlay').classList.remove('open');
    }

    function renderCmdResults(filter) {
        var results = $('#cmd-results');
        var f = filter.toLowerCase();
        var filtered = commands.filter(function(c) { return c.name.toLowerCase().indexOf(f) >= 0; });
        results.innerHTML = filtered.map(function(c) {
            return '<div class="cmd-result-item" data-action="' + c.name + '">' +
                '<span>' + c.name + '</span>' +
                '<span class="cmd-result-shortcut">' + c.shortcut + '</span>' +
                '</div>';
        }).join('');
        // Click handler
        results.querySelectorAll('.cmd-result-item').forEach(function(item) {
            item.addEventListener('click', function() {
                var name = item.dataset.action;
                var cmd = commands.find(function(c) { return c.name === name; });
                if (cmd) { cmd.action(); closeCmdPalette(); }
            });
        });
    }

    $('#cmd-trigger').addEventListener('click', openCmdPalette);
    $('#cmd-input').addEventListener('input', function() { renderCmdResults(this.value); });
    $('#cmd-input').addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeCmdPalette();
        if (e.key === 'Enter') {
            var first = $('#cmd-results .cmd-result-item');
            if (first) first.click();
        }
    });
    $('#cmd-overlay').addEventListener('click', function(e) {
        if (e.target === this) closeCmdPalette();
    });

    // ── Keyboard Shortcuts ─────────────────────────────────────────────────
    document.addEventListener('keydown', function(e) {
        // Cmd+K or Ctrl+K → command palette
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openCmdPalette();
            return;
        }
        // Don't intercept when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === '1') switchTab('overview');
        else if (e.key === '2') switchTab('calls');
        else if (e.key === '3') switchTab('search');
        else if (e.key === '4') switchTab('entities');
        else if (e.key === '5') switchTab('system');
        else if (e.key === 'Escape') closeCmdPalette();
    });

    // ── Toast ───────────────────────────────────────────────────────────────
    function toast(msg, type) {
        var container = $('#toast-container');
        var el = document.createElement('div');
        el.className = 'toast ' + (type || '');
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(function() {
            el.remove();
        }, 3000);
    }

    // ── Footer status ───────────────────────────────────────────────────────
    function updateFooter() {
        var uptime = Math.floor(performance.now() / 1000);
        var h = Math.floor(uptime / 3600);
        var m = Math.floor((uptime % 3600) / 60);
        var s = uptime % 60;
        $('#footer-uptime').textContent = 'Uptime: ' + h + 'h ' + m + 'm ' + s + 's';
    }
    setInterval(updateFooter, 10000);
    updateFooter();

    // ── Init ────────────────────────────────────────────────────────────────
    loadOverview();
    loadSystem();

})();
