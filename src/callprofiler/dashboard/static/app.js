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
        callsStatus: '',
        callsDays: 0,
    };

    // ── DOM refs ───────────────────────────────────────────────────────────
    var $ = function(sel) { return document.querySelector(sel); };
    var $$ = function(sel) { return document.querySelectorAll(sel); };

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    var tabs = $$('#tab-nav .tab');
    var panels = $$('.tab-panel');
    var sseDot = $('#sse-dot');
    var clock = $('#clock');

    // ── URL state (?tab=&status=&days=) ──────────────────────────────────────
    // Shareable, reload-safe dashboard state. replaceState (not pushState) so
    // filter changes don't flood the back-stack.
    function syncURL() {
        var params = new URLSearchParams();
        params.set('tab', state.activeTab);
        if (state.callsStatus) params.set('status', state.callsStatus);
        if (state.callsDays) params.set('days', String(state.callsDays));
        var qs = params.toString();
        history.replaceState(null, '', qs ? '?' + qs : location.pathname);
    }

    // ── Tab Switching ──────────────────────────────────────────────────────
    function switchTab(name) {
        state.activeTab = name;
        tabs.forEach(function(t) { t.classList.toggle('active', t.dataset.tab === name); });
        panels.forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + name); });
        syncURL();
        if (name === 'overview') loadOverview();
        else if (name === 'calls') loadCalls();
        else if (name === 'entities') loadEntities();
        else if (name === 'insight') loadInsight();
        else if (name === 'system') loadSystem();
    }

    tabs.forEach(function(t) {
        t.addEventListener('click', function() { switchTab(this.dataset.tab); });
    });

    // Restore state from URL query (?tab=&status=&days=). Set the filter
    // selects BEFORE switching so loadCalls() picks up the restored values.
    (function restoreFromURL() {
        var params = new URLSearchParams(location.search);
        var st = params.get('status');
        var dys = params.get('days');
        var stEl = $('#calls-status-filter');
        var dyEl = $('#calls-days-filter');
        if (st && stEl) stEl.value = st;
        if (dys && dyEl) dyEl.value = dys;
        var tab = params.get('tab');
        if (tab && $('#panel-' + tab)) switchTab(tab);
    })();

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
                if (data.type !== 'tick') return;
                // Real-time: обновлять АКТИВНУЮ вкладку, не только overview.
                updateStatCards(data.status);            // карточки-счётчики всегда
                if (state.activeTab === 'overview') {
                    renderPipeline(data.by_stage || {});  // степпер живьём
                    addFeedItem(data.status);
                } else if (state.activeTab === 'calls') {
                    loadCalls();
                } else if (state.activeTab === 'entities') {
                    loadEntities();
                } else if (state.activeTab === 'system') {
                    loadSystem();
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

    // ── Profile switcher ───────────────────────────────────────────────────
    (function initProfiles() {
        var sel = $('#profile-select');
        if (!sel) return;
        fetch('/api/users')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var users = data.users || [];
                if (!users.length) return;
                sel.innerHTML = users.map(function(u) {
                    var on = u.user_id === data.active ? ' selected' : '';
                    return '<option value="' + escapeHtml(u.user_id) + '"' + on + '>'
                        + escapeHtml(u.user_id) + ' (' + (u.calls || 0) + ')</option>';
                }).join('');
            })
            .catch(function(e) { console.error('Profiles load failed:', e); });
        sel.addEventListener('change', function() {
            var u = this.value;
            fetch('/api/users/select?user=' + encodeURIComponent(u), { method: 'POST' })
                .then(function() { location.reload(); })
                .catch(function(e) { console.error('Profile switch failed:', e); });
        });
    })();

    // ── Overview ───────────────────────────────────────────────────────────
    function loadOverview() {
        fetch('/api/overview')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                updateStatCards(data);
                renderPipeline(data.by_stage || {});
                if (typeof echarts !== 'undefined') {
                    renderTrendChart(data.daily_counts || []);
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

    function renderPipeline(by_stage) {
        // Порядок = реальный конвейер: диаризация ДО транскрибации; добавлен Deliver.
        var steps = ['new', 'normalizing', 'diarizing', 'transcribing', 'analyzing', 'delivering', 'done', 'error'];
        var labels = ['New', 'Norm', 'Diarize', 'Transcribe', 'Analyze', 'Deliver', 'Done', 'Errors'];
        // Стадии «в работе» подсвечиваем как active (видно, что сейчас крутится).
        var active = { normalizing: 1, diarizing: 1, transcribing: 1, analyzing: 1, delivering: 1, done: 1 };
        var stepper = $('#pipeline-stepper');
        stepper.classList.remove('skeleton');
        var html = '';
        steps.forEach(function(s, i) {
            var count = by_stage[s] || 0;
            var cls = 'pipe-dot';
            if (s === 'error' && count > 0) cls += ' error';
            else if (count > 0 && active[s]) cls += ' active';
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
    function renderTrendChart(daily_counts) {
        var el = $('#chart-trend');
        if (!el) return;
        var chart = echarts.init(el);
        var days = [];
        var date_map = {};
        for (var i = 6; i >= 0; i--) {
            var d = new Date();
            d.setDate(d.getDate() - i);
            var key = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            days.push(key);
            date_map[d.toISOString().slice(0, 10)] = i;
        }
        var counts = [0, 0, 0, 0, 0, 0, 0];
        daily_counts.forEach(function(dc) {
            if (dc.date && date_map[dc.date] !== undefined) {
                counts[date_map[dc.date]] = dc.count || 0;
            }
        });
        chart.setOption({
            grid: { top: 10, right: 16, bottom: 24, left: 44 },
            xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            series: [{
                data: counts,
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
        var statusFilter = ($('#calls-status-filter') || {}).value || '';
        var daysFilter = parseInt(($('#calls-days-filter') || {}).value || '0') || 0;
        state.callsStatus = statusFilter;
        state.callsDays = daysFilter;
        syncURL();
        var url = '/api/calls?limit=' + state.callsLimit + '&offset=' + offset;
        if (statusFilter) url += '&status=' + encodeURIComponent(statusFilter);
        if (daysFilter > 0) url += '&days=' + daysFilter;
        fetch(url)
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
            var rawRisk = c.risk_score != null ? c.risk_score : null;
            var risk = rawRisk !== null ? rawRisk : '--';
            var cls = rawRisk !== null ? (rawRisk >= 60 ? 'risk-high' : (rawRisk >= 30 ? 'risk-med' : 'risk-low')) : '';
            var type = c.direction || '--';
            var summary = c.summary ? c.summary.substring(0, 80) : '--';
            var badge = status === 'done' ? 'badge-done' : (status === 'error' ? 'badge-error' : 'badge-pending');
            if (status === 'processing' || status === 'analyzing' || status === 'transcribing' || status === 'diarizing') badge = 'badge-processing';
            return '<tr class="call-row" data-call-id="' + c.call_id + '" title="Click for details">' +
                '<td>' + (c.call_id || '--') + '</td>' +
                '<td>' + created + '</td>' +
                '<td>' + escapeHtml(contact) + '</td>' +
                '<td>' + duration + '</td>' +
                '<td><span class="badge ' + badge + '">' + status + '</span></td>' +
                '<td><span class="risk ' + cls + '">' + risk + '</span></td>' +
                '<td>' + type + '</td>' +
                '<td>' + escapeHtml(summary) + '</td>' +
                '</tr>';
        }).join('');
        document.querySelectorAll('#calls-table tbody .call-row').forEach(function(row) {
            row.addEventListener('click', function() {
                loadCallDetail(this.dataset.callId);
            });
        });
    }

    function loadCallDetail(callId) {
        var panel = $('#call-detail-panel');
        panel.classList.add('open');
        $('#detail-content').innerHTML = '<div class="skeleton">Loading call #' + callId + '...</div>';
        fetch('/api/calls/' + callId)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    $('#detail-content').innerHTML = '<div class="detail-empty">' + data.error + '</div>';
                    return;
                }
                renderCallDetail(data);
            })
            .catch(function(e) {
                $('#detail-content').innerHTML = '<div class="detail-empty">Failed to load: ' + e.message + '</div>';
            });
    }

    function renderCallDetail(d) {
        var created = d.created_at ? new Date(d.created_at).toLocaleString() : '--';
        var callDt = d.call_datetime ? new Date(d.call_datetime).toLocaleString() : '--';
        var duration = d.duration_sec ? Math.floor(d.duration_sec/60) + 'm ' + (d.duration_sec%60) + 's' : '--';
        var risk = d.risk_score != null ? d.risk_score : '--';
        var riskCls = d.risk_score >= 60 ? 'risk-high' : (d.risk_score >= 30 ? 'risk-med' : 'risk-low');
        var status = d.status || '--';
        var summary = d.summary || 'No summary available';

        var flagsHtml = '';
        if (d.flags && Object.keys(d.flags).length) {
            flagsHtml = '<div class="detail-section"><h4>Flags</h4>';
            Object.keys(d.flags).forEach(function(k) {
                flagsHtml += '<span class="sr-tag call-type" style="margin-right:4px">' + escapeHtml(k) + ': ' + d.flags[k] + '</span>';
            });
            flagsHtml += '</div>';
        }

        var segsHtml = '<div class="detail-section"><h4>Transcript (' + d.segments.length + ' segments)</h4><div class="segment-list">';
        if (d.segments.length === 0) {
            segsHtml += '<span class="detail-empty">No transcript available</span>';
        } else {
            d.segments.forEach(function(s) {
                var speaker = s.speaker || '?';
                var spCls = speaker.toUpperCase() === 'OWNER' ? 'owner' : '';
                var time = (s.start_ms / 1000).toFixed(1) + 's';
                segsHtml += '<div class="segment-item" data-start="' + s.start_ms + '">' +
                    '<span class="seg-time">' + time + '</span>' +
                    '<span class="seg-speaker ' + spCls + '">' + escapeHtml(speaker) + '</span>' +
                    '<span class="seg-text">' + escapeHtml(s.text || '') + '</span>' +
                    '</div>';
            });
        }
        segsHtml += '</div></div>';

        var promHtml = '<div class="detail-section"><h4>Promises</h4>';
        if (!d.promises || d.promises.length === 0) {
            promHtml += '<span class="detail-empty">No promises</span>';
        } else {
            promHtml += '<ul class="detail-promises">';
            d.promises.forEach(function(p) {
                promHtml += '<li><span class="promise-who">' + escapeHtml(p.who || '?') + '</span> — ' +
                    escapeHtml(p.what || '?') +
                    (p.due ? '<span class="promise-due">due ' + p.due + '</span>' : '') +
                    (p.status ? ' [' + p.status + ']' : '') +
                    '</li>';
            });
            promHtml += '</ul>';
        }
        promHtml += '</div>';

        $('#detail-content').innerHTML =
            '<div class="detail-section"><h4>Metadata</h4><dl class="detail-meta">' +
            '<dt>Call #</dt><dd>' + d.call_id + '</dd>' +
            '<dt>File</dt><dd>' + escapeHtml(d.source_filename || '--') + '</dd>' +
            '<dt>Date</dt><dd>' + callDt + '</dd>' +
            '<dt>Created</dt><dd>' + created + '</dd>' +
            '<dt>Direction</dt><dd>' + escapeHtml(d.direction || '--') + '</dd>' +
            '<dt>Duration</dt><dd>' + duration + '</dd>' +
            '<dt>Status</dt><dd>' + status + '</dd>' +
            '<dt>Risk</dt><dd><span class="risk ' + riskCls + '">' + risk + '</span></dd>' +
            '<dt>Contact</dt><dd>' + escapeHtml(d.display_name || d.phone_e164 || '--') + '</dd>' +
            '<dt>Call Type</dt><dd>' + escapeHtml(d.call_type || '--') + '</dd>' +
            '<dt>Model</dt><dd>' + escapeHtml(d.model || '--') + '</dd>' +
            '</dl></div>' +
            '<div class="detail-section"><h4>Summary</h4><p style="font-size:13px;color:var(--text-secondary);line-height:1.6">' + escapeHtml(summary) + '</p></div>' +
            flagsHtml + segsHtml + promHtml;
    }

    $('#detail-close').addEventListener('click', function() {
        $('#call-detail-panel').classList.remove('open');
    });

    $('#calls-prev').addEventListener('click', function() {
        if (state.callsPage > 0) loadCalls(state.callsPage - 1);
    });
    $('#calls-next').addEventListener('click', function() {
        loadCalls(state.callsPage + 1);
    });
    $('#calls-status-filter').addEventListener('change', function() { loadCalls(0); });
    $('#calls-days-filter').addEventListener('change', function() { loadCalls(0); });
    $('#calls-export').addEventListener('click', function() {
        var stEl = $('#calls-status-filter');
        var dyEl = $('#calls-days-filter');
        var st = stEl ? (stEl.value || '') : '';
        var dys = dyEl ? (dyEl.value || '0') : '0';
        var url = '/api/export/calls.csv?status=' + encodeURIComponent(st) +
                  '&days=' + encodeURIComponent(dys || '0');
        window.location.href = url;  // triggers download (Content-Disposition: attachment)
        toast('Exporting CSV…', '');
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

    function highlightMatch(text, query) {
        if (!text || !query) return escapeHtml(text || '');
        var escaped = escapeHtml(text);
        var words = query.split(/\s+/).filter(function(w) { return w.length > 1; });
        words.forEach(function(w) {
            var re = new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
            escaped = escaped.replace(re, '<mark>$1</mark>');
        });
        return escaped;
    }

    function renderSearchResults(results) {
        var el = $('#search-results');
        var q = state.searchQuery;
        if (results.length === 0) {
            el.innerHTML = '<div class="empty-state">No results found for "' + escapeHtml(q) + '"</div>';
            return;
        }
        el.innerHTML = results.map(function(r) {
            var snippet = r.snippet || r.text || '';
            var date = r.call_datetime ? new Date(r.call_datetime).toLocaleString() : '--';
            var tags = [];
            if (r.entity_type) tags.push('<span class="sr-tag entity">' + escapeHtml(r.entity_type) + '</span>');
            if (r.call_type) tags.push('<span class="sr-tag call-type">' + escapeHtml(r.call_type) + '</span>');
            return '<div class="search-result" data-call-id="' + r.call_id + '">' +
                '<div><span class="sr-call-id">#' + r.call_id + '</span>' +
                '<span class="sr-contact">' + escapeHtml(r.contact_name || '?') + '</span>' +
                '<span class="sr-date">' + date + '</span></div>' +
                '<div class="sr-snippet">' + highlightMatch(snippet, q) + '</div>' +
                (tags.length ? '<div class="sr-tags">' + tags.join('') + '</div>' : '') +
                '</div>';
        }).join('');
        document.querySelectorAll('.search-result').forEach(function(item) {
            item.addEventListener('click', function() {
                state.activeTab = 'calls';
                switchTab('calls');
                setTimeout(function() { loadCallDetail(item.dataset.callId); }, 200);
            });
        });
    }

    // ── Entity Modal ────────────────────────────────────────────────────────
    function openEntityModal(entityId) {
        var overlay = $('#entity-overlay');
        overlay.classList.add('open');
        $('#entity-modal-body').innerHTML = '<div class="skeleton">Loading entity #' + entityId + '...</div>';
        $('#entity-modal-title').textContent = 'Entity #' + entityId;
        fetch('/api/character/' + entityId)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                $('#entity-modal-title').textContent = escapeHtml(data.canonical_name || 'Entity #' + entityId);
                state.entityProfile = data;
                renderEntityTab('metrics');
            })
            .catch(function(e) {
                $('#entity-modal-body').innerHTML = '<div class="detail-empty">Failed to load</div>';
            });

        // Re-bind modal tabs
        document.querySelectorAll('#entity-modal-tabs .modal-tab').forEach(function(t) {
            t.onclick = function() {
                document.querySelectorAll('#entity-modal-tabs .modal-tab').forEach(function(x) { x.classList.remove('active'); });
                this.classList.add('active');
                renderEntityTab(this.dataset.etab);
            };
        });
    }

    function closeEntityModal() {
        $('#entity-overlay').classList.remove('open');
    }

    $('#entity-modal-close').addEventListener('click', closeEntityModal);
    $('#entity-overlay').addEventListener('click', function(e) {
        if (e.target === this) closeEntityModal();
    });

    function renderEntityTab(tab) {
        var d = state.entityProfile;
        if (!d) return;
        var body = $('#entity-modal-body');

        if (tab === 'metrics') {
            var risk = d.avg_risk != null ? d.avg_risk : (d.risk_score != null ? d.risk_score : '--');
            var riskCls = Number(risk) >= 60 ? 'risk-high' : (Number(risk) >= 30 ? 'risk-med' : 'risk-low');
            body.innerHTML =
                '<div class="detail-section"><h4>Metrics</h4><dl class="detail-meta">' +
                '<dt>Name</dt><dd>' + escapeHtml(d.canonical_name || '?') + '</dd>' +
                '<dt>Type</dt><dd>' + escapeHtml(d.entity_type || 'person') + '</dd>' +
                '<dt>Total Calls</dt><dd>' + (d.total_calls || 0) + '</dd>' +
                '<dt>Avg Risk</dt><dd><span class="risk ' + riskCls + '">' + risk + '</span></dd>' +
                '<dt>BS Index</dt><dd>' + (d.bs_index != null ? Number(d.bs_index).toFixed(2) : '--') + '</dd>' +
                '<dt>Emotional Pattern</dt><dd>' + escapeHtml(d.emotional_pattern || '--') + '</dd>' +
                (d.trust_score != null ? '<dt>Trust Score</dt><dd>' + Number(d.trust_score).toFixed(2) + '</dd>' : '') +
                '</dl></div>';
            if (d.aliases && d.aliases.length) {
                body.innerHTML += '<div class="detail-section"><h4>Aliases</h4><p style="font-size:12px;color:var(--text-secondary)">' + d.aliases.map(escapeHtml).join(', ') + '</p></div>';
            }
            if (d.summary) {
                body.innerHTML += '<div class="detail-section"><h4>Summary</h4><p style="font-size:13px;color:var(--text-secondary);line-height:1.6">' + escapeHtml(d.summary) + '</p></div>';
            }
            if (d.character_summary) {
                body.innerHTML += '<div class="detail-section"><h4>Character</h4><p style="font-size:13px;color:var(--text-secondary)">' + escapeHtml(d.character_summary) + '</p></div>';
            }
        } else if (tab === 'psychology') {
            var html = '<div class="detail-section"><h4>Psychology Profile</h4>';
            var hasData = false;
            if (d.temperament && Object.keys(d.temperament).length) {
                hasData = true;
                html += '<dl class="detail-meta">';
                if (d.temperament.type) html += '<dt>Temperament</dt><dd>' + escapeHtml(String(d.temperament.type)) + '</dd>';
                if (d.temperament.extraversion != null) html += '<dt>Extraversion</dt><dd>' + d.temperament.extraversion + '</dd>';
                if (d.temperament.neuroticism != null) html += '<dt>Neuroticism</dt><dd>' + d.temperament.neuroticism + '</dd>';
                html += '</dl>';
            }
            if (d.big_five && Object.keys(d.big_five).length) {
                hasData = true;
                html += '<h4 style="margin-top:12px">Big Five</h4><dl class="detail-meta">';
                ['openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism'].forEach(function(trait) {
                    if (d.big_five[trait] != null) html += '<dt>' + trait + '</dt><dd>' + Number(d.big_five[trait]).toFixed(2) + '</dd>';
                });
                html += '</dl>';
            }
            if (d.motivation && Object.keys(d.motivation).length) {
                hasData = true;
                html += '<h4 style="margin-top:12px">Motivation</h4><dl class="detail-meta">';
                if (d.motivation.primary) html += '<dt>Primary</dt><dd>' + escapeHtml(String(d.motivation.primary)) + '</dd>';
                if (d.motivation.secondary) html += '<dt>Secondary</dt><dd>' + escapeHtml(String(d.motivation.secondary)) + '</dd>';
                html += '</dl>';
            }
            if (!hasData) html += '<span class="detail-empty">No psychology data available</span>';
            html += '</div>';

            if (d.patterns && d.patterns.length) {
                html += '<div class="detail-section"><h4>Behavioral Patterns</h4>';
                d.patterns.forEach(function(p) {
                    html += '<div style="padding:4px 8px;margin-bottom:4px;background:rgba(255,255,255,.03);border-radius:4px;font-size:12px">' +
                        '<strong>' + escapeHtml(p.name || '?') + '</strong> ' +
                        (p.label ? '<span class="sr-tag entity">' + escapeHtml(p.label) + '</span>' : '') +
                        (p.severity != null ? ' (sev: ' + p.severity + ')' : '') +
                        '</div>';
                });
                html += '</div>';
            }

            if (d.contradictions && d.contradictions.length) {
                html += '<div class="detail-section"><h4>Contradictions</h4>';
                d.contradictions.forEach(function(c) {
                    html += '<div style="padding:4px 8px;margin-bottom:4px;background:rgba(255,0,0,.06);border-radius:4px;font-size:12px">' +
                        '<em>"' + escapeHtml(c.quote_1 || '') + '"</em> vs <em>"' + escapeHtml(c.quote_2 || '') + '"</em>' +
                        (c.severity ? ' (' + c.severity + ')' : '') +
                        '</div>';
                });
                html += '</div>';
            }
            body.innerHTML = html;
        } else if (tab === 'calls') {
            var calls = d.recent_calls || d.calls || [];
            var html = '<div class="detail-section"><h4>Recent Calls (' + calls.length + ')</h4>';
            if (calls.length === 0) {
                html += '<span class="detail-empty">No calls</span>';
            } else {
                html += '<div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Date</th><th>Type</th><th>Risk</th><th>Summary</th></tr></thead><tbody>';
                calls.slice(0, 20).forEach(function(c) {
                    var risk = c.risk_score != null ? c.risk_score : '--';
                    var riskCls = Number(risk) >= 60 ? 'risk-high' : (Number(risk) >= 30 ? 'risk-med' : 'risk-low');
                    html += '<tr class="call-row" data-call-id="' + c.call_id + '">' +
                        '<td>' + c.call_id + '</td>' +
                        '<td>' + (c.call_datetime ? new Date(c.call_datetime).toLocaleString() : '--') + '</td>' +
                        '<td>' + escapeHtml(c.call_type || c.direction || '--') + '</td>' +
                        '<td><span class="risk ' + riskCls + '">' + risk + '</span></td>' +
                        '<td>' + escapeHtml((c.summary || '').substring(0, 60)) + '</td>' +
                        '</tr>';
                });
                html += '</tbody></table></div>';
            }
            html += '</div>';

            if (d.open_promises && d.open_promises.length) {
                html += '<div class="detail-section"><h4>Open Promises</h4><ul class="detail-promises">';
                d.open_promises.forEach(function(p) {
                    html += '<li><span class="promise-who">' + escapeHtml(p.who || '?') + '</span> — ' +
                        escapeHtml(p.what || '?') +
                        (p.due ? '<span class="promise-due">due ' + p.due + '</span>' : '') +
                        '</li>';
                });
                html += '</ul></div>';
            }
            body.innerHTML = html;

            document.querySelectorAll('#entity-modal-body .call-row').forEach(function(row) {
                row.addEventListener('click', function() {
                    closeEntityModal();
                    switchTab('calls');
                    setTimeout(function() { loadCallDetail(row.dataset.callId); }, 200);
                });
            });
        }
    }

    // ── Entities Tab ───────────────────────────────────────────────────────
    var entExportBtn = $('#entities-export-book');
    if (entExportBtn) {
        entExportBtn.addEventListener('click', function() {
            window.location.href = '/api/export/book.md';  // Content-Disposition: attachment
            toast('Exporting biography…', '');
        });
    }

    function loadEntities() {
        loadPeople();
        fetch('/api/entities?limit=100')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                renderEntitiesTable(data.entities || []);
            })
            .catch(function(e) { console.error('Entities load failed:', e); });
    }

    // ── Личности: список людей + досье (Ф3 плана досье) ────────────────────
    state.peopleCache = [];

    function loadPeople() {
        fetch('/api/people?limit=1000')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                state.peopleCache = data.people || [];
                renderPeopleTable();
            })
            .catch(function(e) { console.error('People load failed:', e); });
    }

    function renderPeopleTable() {
        var tbody = $('#people-table tbody');
        if (!tbody) return;
        var q = (($('#people-search') || {}).value || '').trim().toLowerCase();
        var rows = state.peopleCache.filter(function(p) {
            if (!q) return true;
            return (p.name || '').toLowerCase().indexOf(q) >= 0 ||
                   (p.phone_e164 || '').indexOf(q) >= 0;
        });
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">Никого не найдено</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function(p) {
            var risk = p.global_risk != null ? p.global_risk : null;
            var riskCls = risk !== null ? (risk >= 60 ? 'risk-high' : (risk >= 30 ? 'risk-med' : 'risk-low')) : '';
            var bs = p.bs_index != null ? Number(p.bs_index).toFixed(0)
                   : (p.avg_bs_score != null ? Number(p.avg_bs_score).toFixed(0) : '--');
            var arch = p.archetype_label
                ? '<span class="sr-tag entity" style="border-color:' + clusterColor(p.cluster_idx) + '">' + escapeHtml(p.archetype_label) + '</span>'
                : '--';
            var last = p.last_call_date ? String(p.last_call_date).slice(0, 10) : '--';
            return '<tr class="call-row" data-contact-id="' + p.contact_id + '" title="Открыть досье">' +
                '<td>' + escapeHtml(p.name || '?') + '</td>' +
                '<td>' + arch + '</td>' +
                '<td>' + (risk !== null ? '<span class="risk ' + riskCls + '">' + risk + '</span>' : '--') + '</td>' +
                '<td>' + bs + '</td>' +
                '<td>' + (p.total_calls || 0) + '</td>' +
                '<td>' + last + '</td>' +
                '</tr>';
        }).join('');
        tbody.querySelectorAll('tr[data-contact-id]').forEach(function(row) {
            row.addEventListener('click', function() {
                openPersonDossier(this.dataset.contactId);
            });
        });
    }

    var peopleSearch = $('#people-search');
    if (peopleSearch) peopleSearch.addEventListener('input', renderPeopleTable);

    // ── Досье личности ──────────────────────────────────────────────────────
    function openPersonDossier(contactId) {
        var overlay = $('#person-overlay');
        if (!overlay) return;
        overlay.classList.add('open');
        $('#person-modal-title').textContent = 'Досье #' + contactId;
        $('#person-modal-body').innerHTML = '<div class="skeleton">Загрузка досье...</div>';
        fetch('/api/person/' + contactId)
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (d.not_found) {
                    $('#person-modal-body').innerHTML = '<div class="detail-empty">Контакт не найден</div>';
                    return;
                }
                renderDossier(d);
            })
            .catch(function() {
                $('#person-modal-body').innerHTML = '<div class="detail-empty">Не удалось загрузить досье</div>';
            });
    }

    function closePersonDossier() {
        $('#person-overlay').classList.remove('open');
    }
    $('#person-modal-close').addEventListener('click', closePersonDossier);
    $('#person-overlay').addEventListener('click', function(e) {
        if (e.target === this) closePersonDossier();
    });

    function dossierSec(title, inner) {
        return '<div class="detail-section"><h4>' + title + '</h4>' + inner + '</div>';
    }

    function dossierIdx(label, value, cls) {
        return '<div class="db-stat-card"><div class="db-stat-val' + (cls ? ' ' + cls : '') + '">' +
            value + '</div><div class="db-stat-lbl">' + label + '</div></div>';
    }

    function bsClass(bs, thr) {
        if (bs == null) return '';
        var n = Number(bs);
        if (thr && thr.green_max != null) {  // калиброванные пороги (bs_thresholds)
            if (n <= thr.green_max) return 'risk-low';
            if (thr.yellow_max != null && n <= thr.yellow_max) return 'risk-med';
            return 'risk-high';
        }
        return n >= 60 ? 'risk-high' : (n >= 30 ? 'risk-med' : 'risk-low');
    }

    var TREND_RU = { increasing: 'учащается', decreasing: 'затухает', stable: 'стабильно',
                     insufficient_data: 'мало данных', unknown: '—' };

    function renderDossier(d) {
        var c = d.contact || {};
        var name = c.display_name || c.guessed_name || c.phone_e164 || ('#' + c.contact_id);
        $('#person-modal-title').textContent = name;
        var idx = d.indices || {};
        var html = '';

        // Шапка: архетип, телефон, граф-связка
        var head = [];
        if (d.archetype && d.archetype.label) {
            head.push('<span class="sr-tag entity">' + escapeHtml(d.archetype.label) +
                (d.archetype.membership != null ? ' · ' + Math.round(d.archetype.membership * 100) + '%' : '') +
                '</span>');
        }
        if (c.phone_e164) head.push('<span style="color:var(--text-muted);font-size:12px">' + escapeHtml(c.phone_e164) + '</span>');
        if (d.entity) head.push('<span style="color:var(--text-muted);font-size:11px">граф: ' +
            escapeHtml(d.entity.canonical_name || '') + ' (' + escapeHtml(d.entity.link_method || '') + ')</span>');
        if (head.length) html += '<div class="detail-section">' + head.join(' &nbsp; ') + '</div>';

        // Индексы
        var bs = idx.bs_index != null ? idx.bs_index : idx.avg_bs_score;
        var riskCls = idx.global_risk != null
            ? (idx.global_risk >= 60 ? 'risk-high' : (idx.global_risk >= 30 ? 'risk-med' : 'risk-low')) : '';
        html += '<div class="detail-section"><div class="db-stats">' +
            dossierIdx('Риск', idx.global_risk != null ? idx.global_risk : '--', riskCls) +
            dossierIdx('BS-index', bs != null ? Number(bs).toFixed(0) : '--', bsClass(bs, d.bs_thresholds)) +
            (idx.avg_risk != null ? dossierIdx('Средний риск', Number(idx.avg_risk).toFixed(0), '') : '') +
            (idx.trust_score != null ? dossierIdx('Доверие', Number(idx.trust_score).toFixed(0), '') : '') +
            (idx.conflict_count != null ? dossierIdx('Конфликты', idx.conflict_count, '') : '') +
            '</div></div>';

        // Черты-фразы архетипа
        if (d.archetype && d.archetype.traits && d.archetype.traits.length) {
            html += dossierSec('Отличительное', d.archetype.traits.map(function(t) {
                return '<span class="sr-tag call-type" style="margin:0 4px 4px 0;display:inline-block">' + escapeHtml(t) + '</span>';
            }).join(''));
        }

        // Паттерны поведения
        if (d.patterns && d.patterns.length) {
            html += dossierSec('Паттерны поведения', d.patterns.map(function(p) {
                var sevCls = p.severity === 'high' ? 'risk-high'
                    : (p.severity === 'medium' ? 'risk-med'
                    : (p.severity === 'positive' ? 'risk-low' : ''));
                return '<div class="dossier-pattern">' +
                    '<span class="risk ' + sevCls + '">' + escapeHtml(p.severity || '') + '</span> ' +
                    '<strong>' + escapeHtml(p.name || '?') + '</strong>' +
                    (p.label ? ' — ' + escapeHtml(p.label) : '') + '</div>';
            }).join(''));
        }

        // Психотип
        if ((d.temperament && d.temperament.type) || (d.motivation && d.motivation.primary)) {
            var tm = '';
            if (d.temperament && d.temperament.type) tm += '<dt>Темперамент</dt><dd>' + escapeHtml(String(d.temperament.type)) + '</dd>';
            if (d.motivation && d.motivation.primary) tm += '<dt>Мотивация</dt><dd>' + escapeHtml(String(d.motivation.primary)) + '</dd>';
            html += dossierSec('Психотип', '<dl class="detail-meta">' + tm + '</dl>');
        }

        // Ритм общения
        if (d.temporal) {
            var t = d.temporal;
            var tHtml = '';
            if (t.avg_calls_per_week != null) tHtml += '<dt>Звонков в неделю</dt><dd>' + Number(t.avg_calls_per_week).toFixed(1) + '</dd>';
            if (t.frequency_trend) tHtml += '<dt>Тренд</dt><dd>' + (TREND_RU[t.frequency_trend] || t.frequency_trend) + '</dd>';
            if (t.contact_span_days != null) tHtml += '<dt>Знакомы</dt><dd>' + t.contact_span_days + ' дн.</dd>';
            if (c.last_call_date) tHtml += '<dt>Последний контакт</dt><dd>' + String(c.last_call_date).slice(0, 10) + '</dd>';
            if (tHtml) html += dossierSec('Ритм общения', '<dl class="detail-meta">' + tHtml + '</dl>');
        }

        // Факты-цитаты
        if (d.facts && d.facts.length) {
            html += dossierSec('Факты (дословные цитаты)', d.facts.map(function(f) {
                return '<div class="dossier-quote">«' + escapeHtml(f.quote || '') + '»' +
                    '<div class="dossier-quote-meta">' + escapeHtml(f.type || '') +
                    (f.date ? ' · ' + escapeHtml(f.date) : '') + '</div></div>';
            }).join(''));
        }

        // Противоречия
        if (d.contradictions && d.contradictions.length) {
            html += dossierSec('Противоречия', d.contradictions.map(function(x) {
                return '<div style="padding:4px 8px;margin-bottom:4px;background:rgba(255,0,0,.06);border-radius:4px;font-size:12px">' +
                    '<em>«' + escapeHtml(x.quote_1 || '') + '»</em> vs <em>«' + escapeHtml(x.quote_2 || '') + '»</em>' +
                    (x.severity ? ' (' + escapeHtml(String(x.severity)) + ')' : '') + '</div>';
            }).join(''));
        }

        // Обещания
        if (d.promises && d.promises.open && d.promises.open.length) {
            html += dossierSec('Открытые обещания', '<ul class="detail-promises">' +
                d.promises.open.map(function(p) {
                    return '<li><span class="promise-who">' + escapeHtml(p.who || '?') + '</span> — ' +
                        escapeHtml(p.what || '?') +
                        (p.due ? '<span class="promise-due">до ' + escapeHtml(p.due) + '</span>' : '') + '</li>';
                }).join('') + '</ul>');
        }

        // Личные факты (из карточки контакта)
        if (d.personal_facts && d.personal_facts.length) {
            html += dossierSec('Личное', '<ul class="detail-promises">' +
                d.personal_facts.map(function(f) {
                    var txt = typeof f === 'string' ? f : (f.fact || f.what || JSON.stringify(f));
                    return '<li>' + escapeHtml(txt) + '</li>';
                }).join('') + '</ul>');
        }

        // Связи
        var conns = (d.network && d.network.top_connections) ||
                    (d.social && d.social.top_connections) || [];
        if (conns.length) {
            html += dossierSec('Связи', conns.slice(0, 8).map(function(x) {
                var nm = typeof x === 'string' ? x : (x.name || x.canonical_name || '?');
                return '<span class="sr-tag entity" style="margin:0 4px 4px 0;display:inline-block">' + escapeHtml(nm) + '</span>';
            }).join(''));
        }

        // Динамика по годам
        if (d.evolution && d.evolution.length) {
            html += dossierSec('Динамика риска по годам', '<dl class="detail-meta">' +
                d.evolution.map(function(e) {
                    var yr = e.year || e.period || '?';
                    var rv = e.avg_risk != null ? Number(e.avg_risk).toFixed(0) : '--';
                    return '<dt>' + escapeHtml(String(yr)) + '</dt><dd>' + rv + '</dd>';
                }).join('') + '</dl>');
        }

        // Интерпретация (3 абзаца, persisted)
        html += dossierSec('Интерпретация', d.interpretation
            ? '<p style="font-size:13px;color:var(--text-secondary);line-height:1.6;white-space:pre-wrap">' + escapeHtml(d.interpretation) + '</p>'
            : '<span class="detail-empty">Недоступна — запусти profile-all --user me (LLM-окно на боксе)</span>');

        // Совет
        if (d.advice) {
            html += dossierSec('Совет', '<p style="font-size:13px;color:var(--text-secondary)">' + escapeHtml(d.advice) + '</p>');
        }

        // Последние звонки
        var calls = d.recent_calls || [];
        if (calls.length) {
            var cHtml = '<div class="table-wrap"><table class="data-table"><thead><tr><th>ID</th><th>Дата</th><th>Риск</th><th>Суть</th></tr></thead><tbody>';
            calls.slice(0, 10).forEach(function(x) {
                var r = x.risk_score != null ? x.risk_score : '--';
                var rc = Number(r) >= 60 ? 'risk-high' : (Number(r) >= 30 ? 'risk-med' : 'risk-low');
                cHtml += '<tr class="call-row" data-call-id="' + x.call_id + '">' +
                    '<td>' + x.call_id + '</td>' +
                    '<td>' + (x.call_datetime ? new Date(x.call_datetime).toLocaleDateString() : '--') + '</td>' +
                    '<td><span class="risk ' + rc + '">' + r + '</span></td>' +
                    '<td>' + escapeHtml((x.summary || '').substring(0, 70)) + '</td></tr>';
            });
            cHtml += '</tbody></table></div>';
            html += dossierSec('Последние звонки', cHtml);
        }

        // Кнопки-переходы
        var btns = '<button class="btn btn-outline btn-sm" id="dossier-ecg-btn" data-cid="' + (c.contact_id || '') + '">ЭКГ отношений →</button>';
        if (d.entity) {
            btns += ' <button class="btn btn-outline btn-sm" id="dossier-entity-btn" data-eid="' + d.entity.entity_id + '">Граф-персона →</button>';
        }
        html += '<div class="detail-section">' + btns + '</div>';

        var body = $('#person-modal-body');
        body.innerHTML = html;

        var ecgBtn = $('#dossier-ecg-btn');
        if (ecgBtn) ecgBtn.addEventListener('click', function() {
            var cid = this.dataset.cid;
            closePersonDossier();
            switchTab('insight');
            setTimeout(function() {
                var sel = $('#ecg-contact');
                if (sel) { sel.value = cid; loadEcg(cid); }
            }, 300);
        });
        var entBtn = $('#dossier-entity-btn');
        if (entBtn) entBtn.addEventListener('click', function() {
            closePersonDossier();
            openEntityModal(this.dataset.eid);
        });
        body.querySelectorAll('.call-row[data-call-id]').forEach(function(row) {
            row.addEventListener('click', function() {
                closePersonDossier();
                switchTab('calls');
                setTimeout(function() { loadCallDetail(row.dataset.callId); }, 200);
            });
        });
    }

    function renderEntitiesTable(entities) {
        var tbody = $('#entities-table tbody');
        if (entities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">No entities found</td></tr>';
            return;
        }
        tbody.innerHTML = entities.map(function(e) {
            var rawRisk = e.avg_risk != null ? e.avg_risk : (e.risk_score != null ? e.risk_score : null);
            var riskDisp = rawRisk !== null ? Number(rawRisk).toFixed(0) : '--';
            var riskCls = rawRisk !== null ? (Number(rawRisk) >= 60 ? 'risk-high' : (Number(rawRisk) >= 30 ? 'risk-med' : 'risk-low')) : '';
            // Persona id-space: prefer graph entity_id (modal calls /api/character/{entity_id}).
            var entityId = e.entity_id != null ? e.entity_id : e.contact_id;
            var calls = e.total_calls != null ? e.total_calls : (e.call_count || 0);
            return '<tr class="call-row" data-entity-id="' + entityId + '" title="Click for profile">' +
                '<td>' + escapeHtml(e.canonical_name || e.display_name || e.phone_e164 || '--') + '</td>' +
                '<td>' + escapeHtml(e.entity_type || 'person') + '</td>' +
                '<td>' + calls + '</td>' +
                '<td>' + (e.bs_index != null ? Number(e.bs_index).toFixed(2) : '--') + '</td>' +
                '<td>' + (rawRisk !== null ? '<span class="risk ' + riskCls + '">' + riskDisp + '</span>' : '--') + '</td>' +
                '<td>' + escapeHtml(e.character_label || '--') + '</td>' +
                '</tr>';
        }).join('');
        document.querySelectorAll('#entities-table tbody tr[data-entity-id]').forEach(function(row) {
            row.addEventListener('click', function() {
                openEntityModal(this.dataset.entityId);
            });
        });
    }

    // ── Insight Tab (Архетипы) — Phase 7 ─────────────────────────────────────
    // Reads precomputed archetype output (PCA-2D coords, clusters) + call
    // metadata. Computed offline by `archetypes-fit`; degrades to "нет данных"
    // when the model has not been fit. Не подписан на SSE-тики — статичен между
    // прогонами fit, перерисовывается только при заходе на вкладку.
    var CLUSTER_COLORS = ['#00D4C8', '#00A8FF', '#FFB800', '#FF5C7A', '#9B8CFF',
                          '#4ADE80', '#F472B6', '#38BDF8'];
    var insightCharts = {};  // id -> ECharts instance (disposed/recreated per load)

    function clusterColor(idx) {
        if (idx === null || idx === undefined || idx < 0) return '#4A5568';
        return CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
    }

    function initChart(id) {
        var el = $('#' + id);
        if (!el || typeof echarts === 'undefined') return null;
        if (insightCharts[id]) insightCharts[id].dispose();
        insightCharts[id] = echarts.init(el);
        return insightCharts[id];
    }

    function emptyChart(chart, msg) {
        chart.setOption({ title: { text: msg || 'нет данных', left: 'center',
            top: 'center', textStyle: { color: '#4A5568', fontSize: 13 } } }, true);
    }

    window.addEventListener('resize', function() {
        Object.keys(insightCharts).forEach(function(k) {
            if (insightCharts[k]) insightCharts[k].resize();
        });
    });

    function loadInsight() {
        if (typeof echarts === 'undefined') return;
        fetch('/api/insight/pca').then(function(r) { return r.json(); }).then(renderPca).catch(function() {});
        fetch('/api/insight/network?limit=40').then(function(r) { return r.json(); }).then(renderNetwork).catch(function() {});
        fetch('/api/insight/circadian').then(function(r) { return r.json(); }).then(renderCircadian).catch(function() {});
        loadEcgContacts();
    }

    function renderInsightLegend(clusters) {
        var el = $('#insight-legend');
        if (!el) return;
        if (!clusters || !clusters.length) {
            el.innerHTML = '<span class="empty-state">Нет модели архетипов. Запусти <code>archetypes-fit --user me</code>.</span>';
            return;
        }
        el.innerHTML = clusters.map(function(c) {
            return '<span style="display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;font-size:12px;color:var(--text-secondary)">' +
                '<span style="width:12px;height:12px;border-radius:3px;background:' + clusterColor(c.idx) + '"></span>' +
                escapeHtml(c.label || ('кластер ' + c.idx)) +
                ' <span style="color:var(--text-muted)">(' + c.size + ')</span></span>';
        }).join('');
    }

    function renderPca(data) {
        var stats = $('#insight-stats');
        if (stats) {
            stats.textContent = data.silhouette != null
                ? ('k=' + data.k + '  ·  silhouette ' + Number(data.silhouette).toFixed(2) +
                   '  ·  ' + (data.points ? data.points.length : 0) + ' контактов')
                : '';
        }
        renderInsightLegend(data.clusters);
        var chart = initChart('chart-pca');
        if (!chart) return;
        if (!data.points || !data.points.length) { emptyChart(chart); return; }

        var byCluster = {};
        data.points.forEach(function(p) {
            (byCluster[p.cluster] = byCluster[p.cluster] || []).push(p);
        });
        var series = Object.keys(byCluster).map(function(k) {
            var idx = parseInt(k, 10);
            var lbl = (data.clusters[idx] && data.clusters[idx].label) || ('кластер ' + idx);
            return {
                name: lbl, type: 'scatter', symbolSize: 11,
                itemStyle: { color: clusterColor(idx), opacity: 0.78 },
                data: byCluster[k].map(function(p) {
                    return { value: [p.x, p.y], name: p.name, _label: p.label,
                             _conf: p.confidence, _calls: p.calls, _mem: p.membership,
                             _cid: p.contact_id };
                })
            };
        });
        if (data.clusters && data.clusters.length) {
            series.push({
                name: 'центры', type: 'scatter', symbol: 'diamond', symbolSize: 22,
                itemStyle: { color: 'rgba(255,255,255,0.12)', borderColor: '#fff', borderWidth: 1 },
                data: data.clusters.map(function(c) { return { value: [c.cx, c.cy], name: c.label }; }),
                tooltip: { formatter: function(o) { return escapeHtml(o.name || ''); } }
            });
        }
        chart.setOption({
            grid: { top: 16, right: 16, bottom: 26, left: 38 },
            tooltip: { trigger: 'item', formatter: function(o) {
                var d = o.data || {};
                if (d._label === undefined) return escapeHtml(d.name || '');
                return '<b>' + escapeHtml(d.name || '?') + '</b><br/>' + escapeHtml(d._label || '') +
                       '<br/>близость ' + Math.round((d._mem || 0) * 100) + '% · ' +
                       escapeHtml(d._conf || '') + ' · ' + (d._calls || 0) + ' зв.';
            } },
            xAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#16202e' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#16202e' } }, axisLabel: { color: '#64748b', fontSize: 10 } },
            series: series
        }, true);
        // Клик по точке-контакту → досье (Ф3)
        chart.off('click');
        chart.on('click', function(params) {
            var d = params.data || {};
            if (d._cid) openPersonDossier(d._cid);
        });
    }

    function renderNetwork(data) {
        var chart = initChart('chart-network');
        if (!chart) return;
        var nodes = data.nodes || [];
        if (!nodes.length) { emptyChart(chart); return; }
        var maxCalls = 1;
        nodes.forEach(function(n) { if (n.calls > maxCalls) maxCalls = n.calls; });
        var gnodes = [{
            id: 'owner', name: data.owner_label || 'Ты', symbolSize: 40,
            itemStyle: { color: '#FFFFFF' }, label: { show: true, color: '#0b1220', fontWeight: 600 }, _owner: true
        }];
        var links = [];
        nodes.forEach(function(n) {
            var id = 'c' + n.contact_id;
            var frac = n.calls / maxCalls;
            gnodes.push({
                id: id, name: n.name, symbolSize: 10 + 28 * frac,
                itemStyle: { color: clusterColor(n.cluster) },
                _calls: n.calls, _risk: n.risk, _label: n.label
            });
            links.push({ source: 'owner', target: id, value: n.calls,
                lineStyle: { width: 1 + 3 * frac, opacity: 0.3, color: '#334155', curveness: 0.05 } });
        });
        chart.setOption({
            tooltip: { formatter: function(o) {
                if (o.dataType === 'edge') return '';
                var d = o.data || {};
                if (d._owner) return escapeHtml(d.name);
                return '<b>' + escapeHtml(d.name || '?') + '</b><br/>' +
                       (d._label ? escapeHtml(d._label) + '<br/>' : '') +
                       (d._calls || 0) + ' зв.' + (d._risk != null ? ' · риск ' + d._risk : '');
            } },
            series: [{
                type: 'graph', layout: 'force', roam: true, draggable: true,
                force: { repulsion: 150, edgeLength: [40, 130], gravity: 0.09 },
                label: { show: false },
                emphasis: { label: { show: true, color: '#e2e8f0' } },
                data: gnodes, links: links
            }]
        }, true);
        // Клик по узлу-контакту → досье (Ф3); id узла = 'c{contact_id}'
        chart.off('click');
        chart.on('click', function(params) {
            if (params.dataType !== 'node') return;
            var id = String((params.data || {}).id || '');
            if (id.charAt(0) === 'c') openPersonDossier(id.slice(1));
        });
    }

    function renderCircadian(data) {
        var chart = initChart('chart-circadian');
        if (!chart) return;
        var cells = data.cells || [];
        var days = data.days || ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
        if (!cells.length) { emptyChart(chart); return; }
        var hours = [];
        for (var h = 0; h < 24; h++) hours.push(String(h));
        chart.setOption({
            tooltip: { position: 'top', formatter: function(o) {
                return days[o.value[1]] + ' ' + o.value[0] + ':00 — ' + o.value[2] + ' зв.';
            } },
            grid: { top: 10, right: 16, bottom: 58, left: 36 },
            xAxis: { type: 'category', data: hours, splitArea: { show: true }, axisLabel: { color: '#64748b', fontSize: 9 } },
            yAxis: { type: 'category', data: days, splitArea: { show: true }, axisLabel: { color: '#64748b', fontSize: 10 } },
            visualMap: { min: 0, max: data.max || 1, calculable: false, orient: 'horizontal',
                left: 'center', bottom: 8,
                inRange: { color: ['#0b1220', '#00566b', '#00A8FF', '#00D4C8'] },
                textStyle: { color: '#64748b', fontSize: 9 } },
            series: [{ type: 'heatmap', data: cells,
                emphasis: { itemStyle: { borderColor: '#fff', borderWidth: 1 } } }]
        }, true);
    }

    function renderEcg(data) {
        var chart = initChart('chart-ecg');
        if (!chart) return;
        var series = data.series || [];
        if (!series.length) { emptyChart(chart); return; }
        var periods = series.map(function(s) { return s.period; });
        var calls = series.map(function(s) { return s.calls; });
        var risk = series.map(function(s) { return s.risk; });
        chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: ['активность', 'риск'], bottom: 0, textStyle: { color: '#8B95A5', fontSize: 10 } },
            grid: { top: 14, right: 44, bottom: 38, left: 40 },
            xAxis: { type: 'category', data: periods, axisLabel: { color: '#64748b', fontSize: 9 }, axisLine: { lineStyle: { color: '#1e293b' } } },
            yAxis: [
                { type: 'value', name: 'зв.', splitLine: { lineStyle: { color: '#16202e' } }, axisLabel: { color: '#64748b', fontSize: 9 } },
                { type: 'value', name: 'риск', min: 0, max: 100, position: 'right', splitLine: { show: false }, axisLabel: { color: '#64748b', fontSize: 9 } }
            ],
            series: [
                { name: 'активность', type: 'line', smooth: true, symbol: 'none', data: calls,
                  lineStyle: { color: '#00D4C8', width: 2 },
                  areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: 'rgba(0,212,200,0.25)' }, { offset: 1, color: 'rgba(0,212,200,0)' }]) } },
                { name: 'риск', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 1, data: risk,
                  connectNulls: true, lineStyle: { color: '#FF5C7A', width: 1.5, type: 'dashed' }, itemStyle: { color: '#FF5C7A' } }
            ]
        }, true);
    }

    function loadEcg(contactId) {
        fetch('/api/insight/ecg?contact_id=' + (contactId || 0))
            .then(function(r) { return r.json(); }).then(renderEcg).catch(function() {});
    }

    function loadEcgContacts() {
        var sel = $('#ecg-contact');
        if (!sel) { loadEcg(0); return; }
        if (!sel._bound) {
            sel._bound = true;
            sel.addEventListener('change', function() { loadEcg(this.value || 0); });
        }
        fetch('/api/insight/contacts?limit=80')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var items = data.contacts || [];
                var html = '<option value="0">Все контакты</option>';
                items.forEach(function(c) {
                    var nm = c.display_name || c.guessed_name || c.phone_e164 || ('#' + c.contact_id);
                    html += '<option value="' + c.contact_id + '">' + escapeHtml(nm) +
                            ' (' + (c.call_count || 0) + ')</option>';
                });
                sel.innerHTML = html;
            })
            .catch(function() {})
            .then(function() { loadEcg(sel.value || 0); });
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

                if (data.db_stats && Object.keys(data.db_stats).length) {
                    var stats = data.db_stats;
                    var statsHtml = '<div class="db-stats">';
                    var labels = {
                        calls: 'Calls', contacts: 'Contacts', entities: 'Entities',
                        entity_metrics: 'Metrics', analyses: 'Analyses',
                        transcripts: 'Transcripts', promises: 'Promises',
                        events: 'Events', bio_portraits: 'Portraits',
                        db_size_mb: 'DB Size (MB)',
                    };
                    Object.keys(stats).forEach(function(k) {
                        var val = stats[k];
                        var lbl = labels[k] || k;
                        if (k === 'db_size_mb') val = Number(val).toFixed(1);
                        statsHtml += '<div class="db-stat-card"><div class="db-stat-val">' + val + '</div><div class="db-stat-lbl">' + lbl + '</div></div>';
                    });
                    statsHtml += '</div>';
                    $('#sys-db').innerHTML += statsHtml;
                }

                $('#footer-api').textContent = 'API v' + data.version + ' ● healthy';
                $('#footer-db').textContent = 'DB: ' + (data.db_path || '--').split('\\').slice(-2).join('\\');
            })
            .catch(function(e) { console.error('System load failed:', e); });
    }

    // System action buttons
    function bindSystemActions() {
        $$('.sys-action-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var action = this.dataset.action;
                var endpoint = '/api/tools/' + action;
                btn.disabled = true;
                btn.textContent = 'Running...';
                fetch(endpoint, { method: 'POST' })
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        toast(data.message || (action + ' completed'), 'ok');
                        btn.disabled = false;
                        btn.textContent = btn.textContent.replace('Running...', btn.textContent.split(' ')[0]);
                        loadSystem();
                    })
                    .catch(function(e) {
                        toast(action + ' failed: ' + e.message, 'error');
                        btn.disabled = false;
                        btn.textContent = btn.textContent.replace('Running...', btn.textContent.split(' ')[0]);
                    });
            });
        });
    }

    function loadLogs(level) {
        var url = '/api/system/logs?lines=200';
        if (level) url += '&level=' + encodeURIComponent(level);
        fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var viewer = $('#log-viewer');
                viewer.textContent = data.lines.join('\n') || '(no log entries)';
            })
            .catch(function(e) { console.error('Logs load failed:', e); });
    }

    $('#logs-reload').addEventListener('click', function() { loadLogs($('#log-filter').value); });
    $('#log-filter').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') loadLogs(this.value);
    });

    // ── Command Palette ────────────────────────────────────────────────────
    var commands = [
        { name: 'Go to Overview', shortcut: '1', action: function() { switchTab('overview'); } },
        { name: 'Go to Calls', shortcut: '2', action: function() { switchTab('calls'); } },
        { name: 'Go to Search', shortcut: '3', action: function() { switchTab('search'); } },
        { name: 'Go to Entities', shortcut: '4', action: function() { switchTab('entities'); } },
        { name: 'Go to Архетипы', shortcut: '6', action: function() { switchTab('insight'); } },
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
        else if (e.key === '6') switchTab('insight');
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
    bindSystemActions();
    loadLogs('');

})();
