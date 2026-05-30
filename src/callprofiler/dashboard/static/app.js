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

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    var tabs = $$('#tab-nav .tab');
    var panels = $$('.tab-panel');
    var sseDot = $('#sse-dot');
    var clock = $('#clock');

    // ── URL State (deep-linking: ?tab=calls&status=error&days=7) ───────────
    function readUrlState() {
        var params = new URLSearchParams(location.search);
        return {
            tab: params.get('tab') || location.hash.replace('#', '') || 'overview',
            status: params.get('status') || '',
            days: params.get('days') || '0',
        };
    }

    function writeUrlState() {
        var params = new URLSearchParams();
        params.set('tab', state.activeTab);
        if (state.activeTab === 'calls') {
            var sf = ($('#calls-status-filter') || {}).value || '';
            var df = ($('#calls-days-filter') || {}).value || '0';
            if (sf) params.set('status', sf);
            if (df && df !== '0') params.set('days', df);
        }
        history.replaceState(null, '', location.pathname + '?' + params.toString());
    }

    // ── Tab Switching ──────────────────────────────────────────────────────
    function switchTab(name) {
        state.activeTab = name;
        tabs.forEach(function(t) { t.classList.toggle('active', t.dataset.tab === name); });
        panels.forEach(function(p) { p.classList.toggle('active', p.id === 'panel-' + name); });
        writeUrlState();
        if (name === 'overview') loadOverview();
        else if (name === 'calls') loadCalls();
        else if (name === 'entities') loadEntities();
        else if (name === 'system') loadSystem();
    }

    tabs.forEach(function(t) {
        t.addEventListener('click', function() { switchTab(this.dataset.tab); });
    });

    // Restore tab + filters from URL (query params take precedence over hash)
    var initUrl = readUrlState();
    if ($('#calls-status-filter') && initUrl.status) $('#calls-status-filter').value = initUrl.status;
    if ($('#calls-days-filter') && initUrl.days && initUrl.days !== '0') $('#calls-days-filter').value = initUrl.days;
    if (initUrl.tab && $('#panel-' + initUrl.tab)) switchTab(initUrl.tab);

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
                } else if (data.type === 'calls_changed') {
                    // Pipeline wrote new/updated calls — refresh live if visible.
                    if (state.activeTab === 'calls') loadCalls(state.callsPage);
                    else if (state.activeTab === 'overview') loadOverview();
                    toast('Pipeline activity — calls updated', 'ok');
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
        var steps = ['new', 'normalizing', 'transcribing', 'diarizing', 'analyzing', 'done', 'error'];
        var labels = ['New', 'Norm', 'Transcribe', 'Diarize', 'Analyze', 'Done', 'Errors'];
        var stepper = $('#pipeline-stepper');
        stepper.classList.remove('skeleton');
        var html = '';
        steps.forEach(function(s, i) {
            var count = by_stage[s] || 0;
            var cls = 'pipe-dot';
            if (s === 'error' && count > 0) cls += ' error';
            else if (count > 0 && (s === 'done' || s === 'analyzing')) cls += ' active';
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
        var daysFilter = parseInt(($('#calls-days-filter') || {}).value || '0');
        if (state.activeTab === 'calls') writeUrlState();
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

        var audioHtml = '<div class="detail-section"><h4>Audio</h4>' +
            '<audio id="call-audio" class="call-audio" controls preload="none" ' +
            'src="/api/calls/' + d.call_id + '/audio"></audio>' +
            '<div class="audio-hint">Click a transcript line to seek</div></div>';

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
            flagsHtml + audioHtml + segsHtml + promHtml;

        // Click a transcript segment → seek the audio player to its start.
        document.querySelectorAll('#detail-content .segment-item').forEach(function(seg) {
            seg.addEventListener('click', function() {
                var audio = document.getElementById('call-audio');
                if (!audio) return;
                var ms = parseInt(this.dataset.start || '0', 10);
                audio.currentTime = ms / 1000;
                audio.play().catch(function() { /* autoplay/blocked or no file */ });
            });
        });
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
        var sf = ($('#calls-status-filter') || {}).value || '';
        var df = parseInt(($('#calls-days-filter') || {}).value || '0', 10);
        var parts = [];
        if (sf) parts.push('status=' + encodeURIComponent(sf));
        if (df > 0) parts.push('days=' + df);
        var url = '/api/calls/export' + (parts.length ? '?' + parts.join('&') : '');
        window.location.href = url;
        toast('Exporting CSV…', 'ok');
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
            var rawRisk = e.avg_risk != null ? e.avg_risk : (e.risk_score != null ? e.risk_score : null);
            var riskDisp = rawRisk !== null ? Number(rawRisk).toFixed(0) : '--';
            var riskCls = rawRisk !== null ? (Number(rawRisk) >= 60 ? 'risk-high' : (Number(rawRisk) >= 30 ? 'risk-med' : 'risk-low')) : '';
            var entityId = e.contact_id || e.entity_id;
            return '<tr class="call-row" data-entity-id="' + entityId + '" title="Click for profile">' +
                '<td>' + escapeHtml(e.display_name || e.phone_e164 || '--') + '</td>' +
                '<td>' + escapeHtml(e.entity_type || 'person') + '</td>' +
                '<td>' + (e.call_count || 0) + '</td>' +
                '<td>' + (e.bs_index != null ? Number(e.bs_index).toFixed(2) : '--') + '</td>' +
                '<td>' + (rawRisk !== null ? '<span class="risk ' + riskCls + '">' + riskDisp + '</span>' : '--') + '</td>' +
                '<td>' + (e.last_seen || '--') + '</td>' +
                '</tr>';
        }).join('');
        document.querySelectorAll('#entities-table tbody tr[data-entity-id]').forEach(function(row) {
            row.addEventListener('click', function() {
                openEntityModal(this.dataset.entityId);
            });
        });
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
    bindSystemActions();
    loadLogs('');

})();
