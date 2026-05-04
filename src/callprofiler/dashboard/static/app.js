// Dashboard Frontend Logic

// Event type labels
const EVENT_LABELS = {
    'call_created': '📞 Новый звонок',
    'transcription_complete': '📝 Транскрипция готова',
    'analysis_complete': '🧠 Анализ завершён',
    'entity_updated': '👤 Обновлён профиль'
};

// Entity type icons
const ENTITY_ICONS = {
    'PERSON': '👤',
    'COMPANY': '🏢',
    'PLACE': '📍',
    'PROJECT': '📋',
    'EVENT': '📅'
};

// Temperament labels
const TEMPERAMENT_LABELS = {
    'choleric': 'Холерик',
    'sanguine': 'Сангвиник',
    'phlegmatic': 'Флегматик',
    'melancholic': 'Меланхолик'
};

// Big Five labels
const BIG_FIVE_LABELS = {
    'openness': 'Открытость опыту',
    'conscientiousness': 'Добросовестность',
    'extraversion': 'Экстраверсия',
    'agreeableness': 'Доброжелательность',
    'neuroticism': 'Нейротизм'
};

// Motivation labels
const MOTIVATION_LABELS = {
    'achievement': 'Достижение',
    'power': 'Власть',
    'affiliation': 'Принадлежность',
    'security': 'Безопасность'
};

// State
let eventSource = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadHistory();
    connectSSE();

    // Modal close
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('entity-modal').addEventListener('click', (e) => {
        if (e.target.id === 'entity-modal') closeModal();
    });
});

// Connect to SSE stream
function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/events/stream');

    eventSource.onopen = () => {
        console.log('SSE connected');
        reconnectAttempts = 0;
        updateConnectionStatus('connected');
    };

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            addLiveEvent(data);
        } catch (e) {
            console.error('Failed to parse SSE event:', e);
        }
    };

    eventSource.onerror = () => {
        console.error('SSE connection error');
        eventSource.close();
        updateConnectionStatus('disconnected');

        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnecting... (attempt ${reconnectAttempts})`);
                updateConnectionStatus('connecting');
                connectSSE();
            }, 3000 * reconnectAttempts);
        } else {
            console.error('Max reconnect attempts reached, falling back to polling');
            startPolling();
        }
    };
}

// Fallback polling
function startPolling() {
    setInterval(() => {
        loadHistory();
        loadStats();
    }, 5000);
}

// Update connection status indicator
function updateConnectionStatus(status) {
    const liveEventsHeader = document.querySelector('aside h2');
    const indicator = liveEventsHeader.querySelector('.connection-status') || document.createElement('span');
    indicator.className = `connection-status ${status}`;
    if (!liveEventsHeader.querySelector('.connection-status')) {
        liveEventsHeader.prepend(indicator);
    }
}

// Add live event to stream (newest at top)
function addLiveEvent(event) {
    const container = document.getElementById('live-events');

    // Remove "connecting" message if present
    if (container.querySelector('.animate-pulse')) {
        container.innerHTML = '';
    }

    const eventCard = document.createElement('div');
    eventCard.className = 'event-card-compact';

    const timestamp = new Date(event.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const label = EVENT_LABELS[event.event_type] || event.event_type;

    let content = `
        <div class="flex items-start gap-2">
            <div class="event-icon">${getEventIcon(event.event_type)}</div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2 mb-1">
                    <span class="text-xs font-semibold text-primary truncate">${getEventLabel(event.event_type)}</span>
                    <span class="text-xs text-muted whitespace-nowrap">${timestamp}</span>
                </div>
    `;

    if (event.data.contact_label) {
        content += `<div class="text-xs text-secondary truncate mb-1">${event.data.contact_label}</div>`;
    }

    // Add more informative details
    const details = [];
    if (event.data.direction) {
        details.push(event.data.direction === 'incoming' ? '📥' : '📤');
    }
    if (event.data.call_type) {
        details.push(event.data.call_type);
    }
    if (event.data.risk_score !== undefined) {
        const riskEmoji = event.data.risk_score < 30 ? '🟢' : event.data.risk_score < 70 ? '🟡' : '🔴';
        details.push(`${riskEmoji} ${event.data.risk_score}`);
    }
    if (details.length > 0) {
        content += `<div class="text-xs text-muted">${details.join(' · ')}</div>`;
    }

    if (event.data.summary) {
        content += `<div class="text-xs text-secondary mt-1 line-clamp-2">${truncate(event.data.summary, 100)}</div>`;
    }

    content += `</div></div>`;
    eventCard.innerHTML = content;

    // Insert at top (newest first)
    container.insertBefore(eventCard, container.firstChild);

    // Keep only last 30 events
    while (container.children.length > 30) {
        container.removeChild(container.lastChild);
    }

    // Auto-refresh history on ANY event (call status changed)
    setTimeout(loadHistory, 800);
}

// Get event icon
function getEventIcon(eventType) {
    const icons = {
        'call_created': '📞',
        'transcription_complete': '📝',
        'analysis_complete': '🧠',
        'entity_updated': '👤'
    };
    return icons[eventType] || '📋';
}

// Get event label (short)
function getEventLabel(eventType) {
    const labels = {
        'call_created': 'Новый звонок',
        'transcription_complete': 'Транскрипция',
        'analysis_complete': 'Анализ готов',
        'entity_updated': 'Профиль обновлён'
    };
    return labels[eventType] || eventType;
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('stat-calls').textContent = stats.total_calls || 0;
        document.getElementById('stat-entities').textContent = stats.total_entities || 0;
        document.getElementById('stat-portraits').textContent = stats.total_portraits || 0;

        if (stats.avg_risk !== null) {
            const avgRisk = Math.round(stats.avg_risk);
            const riskClass = avgRisk < 30 ? 'text-success' :
                             avgRisk < 70 ? 'text-warning' : 'text-danger';
            document.getElementById('stat-risk').innerHTML = `<span class="${riskClass}">${avgRisk}</span>`;
        } else {
            document.getElementById('stat-risk').textContent = '—';
        }
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

// Load call history
async function loadHistory() {
    try {
        const response = await fetch('/api/history?limit=50');
        const calls = await response.json();

        const container = document.getElementById('history-list');
        container.innerHTML = '';

        if (calls.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-12">История пуста</div>';
            return;
        }

        calls.forEach(call => {
            const card = createCallCard(call);
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Failed to load history:', e);
        document.getElementById('history-list').innerHTML =
            '<div class="text-center text-danger py-12">Ошибка загрузки истории</div>';
    }
}

// Create call card element (compact premium design)
function createCallCard(call) {
    const card = document.createElement('div');
    card.className = 'call-card';

    const datetime = call.call_datetime ?
        new Date(call.call_datetime).toLocaleString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }) :
        'Дата неизвестна';

    const directionIcon = call.direction === 'incoming' ? '📥' : '📤';
    const duration = call.duration_sec ? formatDuration(call.duration_sec) : '—';

    const statusClass = `status-${call.status}`;
    const statusLabel = {
        'pending': 'Ожидание',
        'transcribed': 'Расшифрован',
        'analyzed': 'Проанализирован',
        'error': 'Ошибка'
    }[call.status] || call.status;

    let riskBadge = '';
    if (call.risk_score !== null && call.risk_score !== undefined) {
        const riskEmoji = call.risk_score < 30 ? '🟢' : call.risk_score < 70 ? '🟡' : '🔴';
        const riskClass = call.risk_score < 30 ? 'risk-low' :
                         call.risk_score < 70 ? 'risk-medium' : 'risk-high';
        riskBadge = `<span class="risk-badge ${riskClass}">${riskEmoji} ${call.risk_score}</span>`;
    }

    // Build metadata line with more info
    const metadata = [];
    metadata.push(`${directionIcon} ${call.direction === 'incoming' ? 'Входящий' : 'Исходящий'}`);
    metadata.push(`⏱️ ${duration}`);
    if (call.call_type) {
        const typeIcons = {
            'business': '💼',
            'personal': '👤',
            'support': '🛠️',
            'sales': '💰'
        };
        const typeIcon = typeIcons[call.call_type] || '📋';
        metadata.push(`${typeIcon} ${call.call_type}`);
    }

    card.innerHTML = `
        <div class="flex items-start justify-between mb-2">
            <div class="flex-1 min-w-0">
                <div class="text-base font-semibold text-primary mb-1 truncate">${call.contact_label}</div>
                <div class="text-xs text-muted">${datetime}</div>
            </div>
            <div class="flex items-center gap-2 ml-3">
                ${riskBadge}
                <span class="status-badge ${statusClass}">${statusLabel}</span>
            </div>
        </div>
        <div class="flex items-center gap-3 text-xs text-secondary mb-2">
            ${metadata.join(' · ')}
        </div>
        ${call.summary ? `<div class="text-xs text-secondary leading-relaxed line-clamp-2">${truncate(call.summary, 180)}</div>` : ''}
    `;

    // Click to open entity profile (if entity exists)
    if (call.contact_label && call.status === 'analyzed') {
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
            searchAndOpenEntity(call.contact_label);
        });
    }

    return card;
}

// Search entity by name and open profile
async function searchAndOpenEntity(name) {
    // For now, just show a message
    // In production, would need an API endpoint to search entities by name
    console.log('Search entity:', name);
}

// Open entity profile modal
async function openEntityProfile(entityId) {
    const modal = document.getElementById('entity-modal');
    const content = document.getElementById('modal-content');

    modal.classList.remove('hidden');
    content.innerHTML = '<div class="text-center text-muted py-12"><div class="animate-pulse">Загрузка профиля...</div></div>';

    try {
        const response = await fetch(`/api/entity/${entityId}`);
        const profile = await response.json();

        if (profile.error) {
            content.innerHTML = `<div class="text-center text-danger py-12">${profile.error}</div>`;
            return;
        }

        content.innerHTML = renderEntityProfile(profile);
    } catch (e) {
        console.error('Failed to load entity profile:', e);
        content.innerHTML = '<div class="text-center text-danger py-12">Ошибка загрузки профиля</div>';
    }
}

// Render entity profile
function renderEntityProfile(profile) {
    const icon = ENTITY_ICONS[profile.entity_type] || '❓';

    let html = `
        <div class="mb-6">
            <div class="flex items-center gap-3 mb-2">
                <span class="text-4xl">${icon}</span>
                <div>
                    <h3 class="text-2xl font-bold text-primary">${profile.canonical_name}</h3>
                    <p class="text-sm text-muted">${profile.entity_type}</p>
                </div>
            </div>
            ${profile.aliases.length > 1 ? `<div class="text-sm text-secondary mt-2">Также: ${profile.aliases.filter(a => a !== profile.canonical_name).join(', ')}</div>` : ''}
        </div>
    `;

    // Entity Metrics
    if (profile.bs_index !== null || profile.avg_risk !== null) {
        html += '<div class="profile-section"><h3>📊 Метрики</h3><div class="metric-grid">';

        if (profile.bs_index !== null) {
            html += `<div class="metric-item"><div class="metric-label">BS-Index</div><div class="metric-value">${profile.bs_index.toFixed(1)}</div></div>`;
        }
        if (profile.avg_risk !== null) {
            const riskColor = profile.avg_risk < 30 ? 'text-success' : profile.avg_risk < 70 ? 'text-warning' : 'text-danger';
            html += `<div class="metric-item"><div class="metric-label">Средний риск</div><div class="metric-value ${riskColor}">${profile.avg_risk.toFixed(1)}</div></div>`;
        }
        if (profile.total_calls !== null) {
            html += `<div class="metric-item"><div class="metric-label">Звонков</div><div class="metric-value">${profile.total_calls}</div></div>`;
        }
        if (profile.trust_score !== null) {
            html += `<div class="metric-item"><div class="metric-label">Доверие</div><div class="metric-value">${profile.trust_score.toFixed(2)}</div></div>`;
        }
        if (profile.volatility !== null) {
            html += `<div class="metric-item"><div class="metric-label">Волатильность</div><div class="metric-value">${profile.volatility.toFixed(2)}</div></div>`;
        }
        if (profile.conflict_count !== null) {
            html += `<div class="metric-item"><div class="metric-label">Конфликтов</div><div class="metric-value">${profile.conflict_count}</div></div>`;
        }

        html += '</div></div>';
    }

    // Temperament
    if (profile.temperament) {
        const temp = profile.temperament;
        const tempLabel = TEMPERAMENT_LABELS[temp.type] || temp.type;
        html += `
            <div class="profile-section">
                <h3>🎭 Темперамент</h3>
                <div class="bg-tertiary p-4 rounded border border-border">
                    <div class="text-lg font-semibold text-accent-primary mb-2">${tempLabel}</div>
                    <div class="text-sm text-secondary">
                        Энергия: ${temp.energy || '—'} | Реактивность: ${temp.reactivity || '—'}
                        ${temp.calls_per_week ? ` | ~${temp.calls_per_week.toFixed(1)} бесед/нед` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    // Big Five
    if (profile.big_five) {
        html += '<div class="profile-section"><h3>🧠 Big Five (OCEAN)</h3>';
        for (const [key, value] of Object.entries(profile.big_five)) {
            const label = BIG_FIVE_LABELS[key] || key;
            const percent = (value * 100).toFixed(0);
            html += `
                <div class="big-five-bar">
                    <div class="big-five-label">${label}</div>
                    <div class="big-five-track">
                        <div class="big-five-fill" style="width: ${percent}%"></div>
                    </div>
                    <div class="big-five-value">${value.toFixed(1)}</div>
                </div>
            `;
        }
        html += '</div>';
    }

    // Motivation
    if (profile.motivation) {
        const mot = profile.motivation;
        const primaryLabel = MOTIVATION_LABELS[mot.primary] || mot.primary;
        html += `
            <div class="profile-section">
                <h3>🎯 Мотивация (McClelland)</h3>
                <div class="bg-tertiary p-4 rounded border border-border">
                    <div class="text-sm text-muted mb-2">Доминанта</div>
                    <div class="text-lg font-semibold text-accent-primary mb-3">${primaryLabel}</div>
                    ${mot.drivers && mot.drivers.length > 0 ? `
                        <div class="text-sm text-muted mb-2">Драйверы</div>
                        <div class="flex flex-wrap gap-2">
                            ${mot.drivers.map(d => `<span class="trait-tag">${MOTIVATION_LABELS[d.driver] || d.driver}: ${d.score.toFixed(2)}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    // Biography Portrait
    if (profile.prose || profile.traits.length > 0) {
        html += '<div class="profile-section"><h3>📖 Биографический портрет</h3>';

        if (profile.relationship) {
            html += `<div class="text-sm text-secondary mb-3"><strong>Отношение:</strong> ${profile.relationship}</div>`;
        }

        if (profile.traits.length > 0) {
            html += '<div class="mb-3">';
            profile.traits.forEach(trait => {
                html += `<span class="trait-tag">${trait}</span>`;
            });
            html += '</div>';
        }

        if (profile.prose) {
            html += `<div class="text-sm text-secondary leading-relaxed whitespace-pre-wrap">${profile.prose}</div>`;
        }

        html += '</div>';
    }

    return html;
}

// Close modal
function closeModal() {
    document.getElementById('entity-modal').classList.add('hidden');
}

// Utility: truncate text
function truncate(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '…' : text;
}

// Utility: format duration
function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}
