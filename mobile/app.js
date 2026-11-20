/**
 * Environmental Monitoring PWA - Main Application
 * Vanilla JS with Chart.js for visualizations
 */

// ============================================
// Configuration & State
// ============================================

const CONFIG = {
    API_BASE_URL: 'http://backend:8000',
    WS_BASE_URL: 'ws://backend:8000/ws',
    REFRESH_INTERVAL: 10000, // 10 seconds
    CHART_MAX_POINTS: 60,
};

const PARAMETERS = {
    temperature: { name: 'Temperature', unit: '°C', color: '#FF6B6B', min: -10, max: 50 },
    humidity: { name: 'Humidity', unit: '%', color: '#4ECDC4', min: 0, max: 100 },
    noise: { name: 'Noise', unit: 'dB', color: '#FFD93D', min: 30, max: 120 },
    air_quality: { name: 'Air Quality', unit: 'AQI', color: '#6BCB77', min: 0, max: 500 },
    pm25: { name: 'PM2.5', unit: 'µg/m³', color: '#FF8E72', min: 0, max: 150 },
    pm10: { name: 'PM10', unit: 'µg/m³', color: '#A8D0E6', min: 0, max: 200 },
    voltage: { name: 'Voltage', unit: 'V', color: '#C06C84', min: 200, max: 250 },
};

const ZONES = [
    { id: 'prod-01', name: 'Production Line 1', type: 'production', relays: [1, 2] },
    { id: 'prod-02', name: 'Production Line 2', type: 'production', relays: [1, 2] },
    { id: 'prod-03', name: 'Production Line 3', type: 'production', relays: [1, 2] },
    { id: 'store-01', name: 'Storage Area 1', type: 'storage', relays: [1, 2] },
    { id: 'store-02', name: 'Storage Area 2', type: 'storage', relays: [1, 2] },
    { id: 'tech-01', name: 'Technical Room 1', type: 'technical', relays: [1, 2] },
    { id: 'tech-02', name: 'Technical Room 2', type: 'technical', relays: [1, 2] },
];

const ALERT_LEVELS = {
    info: { label: 'Info', color: '#3498DB', priority: 1 },
    warning: { label: 'Warning', color: '#F39C12', priority: 2 },
    critical: { label: 'Critical', color: '#E74C3C', priority: 3 },
    predictive: { label: 'Predictive', color: '#9B59B6', priority: 4 },
};

const ALERT_STATUSES = {
    open: { label: 'Open', class: 'badge-open' },
    acknowledged: { label: 'Acknowledged', class: 'badge-acknowledged' },
    resolved: { label: 'Resolved', class: 'badge-resolved' },
};

// Application State
const state = {
    auth: null,
    zones: [],
    devices: [],
    measurements: {},
    alerts: [],
    activeAlerts: [],
    riskScores: {},
    predictions: null,
    aiWeeklyReport: null,
    alertRules: [],
    reports: [],
    selectedZone: 'prod-01',
    selectedParameter: 'temperature',
    chartInstances: {},
    ws: null,
    refreshTimer: null,
    reconnectTimer: null,
};

// ============================================
// DOM Elements Cache
// ============================================

const elements = {};

// Initialize element references
function initElements() {
    // Screens
    elements.loginScreen = document.getElementById('login-screen');
    elements.appScreen = document.getElementById('app-screen');
    elements.loginForm = document.getElementById('login-form');
    elements.loginError = document.getElementById('login-error');
    elements.loginBtn = document.getElementById('login-btn');
    
    // Header
    elements.pageTitle = document.getElementById('page-title');
    elements.menuToggle = document.getElementById('menu-toggle');
    elements.notificationsBtn = document.getElementById('notifications-btn');
    elements.userMenuBtn = document.getElementById('user-menu-btn');
    elements.notificationBadge = document.getElementById('notification-badge');
    elements.alertsBadge = document.getElementById('alerts-badge');
    elements.bottomAlertsBadge = document.getElementById('bottom-alerts-badge');
    
    // Side Menu
    elements.sideMenu = document.getElementById('side-menu');
    elements.menuOverlay = document.getElementById('menu-overlay');
    elements.closeMenu = document.getElementById('close-menu');
    elements.userName = document.getElementById('user-name');
    elements.userRole = document.getElementById('user-role');
    elements.userAvatar = document.getElementById('user-avatar');
    elements.logoutBtn = document.getElementById('logout-btn');
    elements.modalLogoutBtn = document.getElementById('modal-logout-btn');
    
    // Navigation
    elements.menuItems = document.querySelectorAll('.menu-item[data-page]');
    elements.navItems = document.querySelectorAll('.nav-item[data-page]');
    elements.pages = document.querySelectorAll('.page');
    
    // More Modal
    elements.moreModal = document.getElementById('more-modal');
    elements.closeMoreModal = document.getElementById('close-more-modal');
    
    // Notification Modal
    elements.notificationModal = document.getElementById('notification-modal');
    elements.closeNotificationModal = document.getElementById('close-notification-modal');
    elements.notificationList = document.getElementById('notification-list');
    
    // Confirm Modal
    elements.confirmModal = document.getElementById('confirm-modal');
    elements.confirmTitle = document.getElementById('confirm-title');
    elements.confirmMessage = document.getElementById('confirm-message');
    elements.confirmOk = document.getElementById('confirm-ok');
    elements.confirmCancel = document.getElementById('confirm-cancel');
    
    // Relay Modal
    elements.relayModal = document.getElementById('relay-modal');
    elements.relayModalTitle = document.getElementById('relay-modal-title');
    elements.relayOptions = document.getElementById('relay-options');
    elements.closeRelayModal = document.getElementById('close-relay-modal');
    
    // Toast
    elements.toastContainer = document.getElementById('toast-container');
    
    // Dashboard
    elements.zoneGrid = document.getElementById('zone-grid');
    elements.realtimeChart = document.getElementById('realtime-chart');
    elements.chartParameter = document.getElementById('chart-parameter');
    elements.activeAlertsList = document.getElementById('active-alerts-list');
    elements.dashboardLastUpdate = document.getElementById('dashboard-last-update');
    
    // Zones Page
    elements.zoneSelect = document.getElementById('zone-select');
    elements.zoneDetail = document.getElementById('zone-detail');
    
    // Alerts Page
    elements.alertsTableBody = document.querySelector('#alerts-table tbody');
    elements.alertLevelFilter = document.getElementById('alert-level-filter');
    elements.alertStatusFilter = document.getElementById('alert-status-filter');
    
    // Reports Page
    elements.reportType = document.getElementById('report-type');
    elements.reportFormat = document.getElementById('report-format');
    elements.reportZone = document.getElementById('report-zone');
    elements.reportStartDate = document.getElementById('report-start-date');
    elements.reportEndDate = document.getElementById('report-end-date');
    elements.generateReportBtn = document.getElementById('generate-report-btn');
    elements.reportGenerationStatus = document.getElementById('report-generation-status');
    elements.reportsTableBody = document.querySelector('#reports-table tbody');
    
    // AI Page
    elements.riskGrid = document.getElementById('risk-grid');
    elements.refreshRiskBtn = document.getElementById('refresh-risk-btn');
    elements.predictZone = document.getElementById('predict-zone');
    elements.predictHorizon = document.getElementById('predict-horizon');
    elements.predictBtn = document.getElementById('predict-btn');
    elements.predictionsResult = document.getElementById('predictions-result');
    elements.aiWeeklyReport = document.getElementById('ai-weekly-report');
    
    // Settings Page
    elements.rulesTableBody = document.querySelector('#rules-table tbody');
    elements.relayControl = document.getElementById('relay-control');
}

// ============================================
// Utility Functions
// ============================================

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatTimeAgo(isoString) {
    if (!isoString) return '-';
    const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function getAlertLevelClass(level) {
    return `badge-${level}`;
}

function getAlertStatusClass(status) {
    return ALERT_STATUSES[status]?.class || 'badge-open';
}

function showToast(title, message, type = 'info', duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${type === 'success' ? '<polyline points="20 6 9 17 4 12"></polyline>' : ''}
                ${type === 'warning' ? '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>' : ''}
                ${type === 'danger' ? '<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>' : ''}
                ${type === 'info' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>' : ''}
            </svg>
        </div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" aria-label="Dismiss">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    `;
    
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showConfirm(title, message) {
    return new Promise((resolve) => {
        elements.confirmTitle.textContent = title;
        elements.confirmMessage.textContent = message;
        elements.confirmModal.classList.add('open');
        
        const cleanup = () => {
            elements.confirmModal.classList.remove('open');
            elements.confirmOk.removeEventListener('click', onOk);
            elements.confirmCancel.removeEventListener('click', onCancel);
            elements.confirmModal.querySelector('.modal-backdrop').removeEventListener('click', onCancel);
        };
        
        const onOk = () => { cleanup(); resolve(true); };
        const onCancel = () => { cleanup(); resolve(false); };
        
        elements.confirmOk.addEventListener('click', onOk);
        elements.confirmCancel.addEventListener('click', onCancel);
        elements.confirmModal.querySelector('.modal-backdrop').addEventListener('click', onCancel);
    });
}

function openModal(modal) {
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal(modal) {
    modal.classList.remove('open');
    document.body.style.overflow = '';
}

// ============================================
// API Functions
// ============================================

async function apiRequest(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    
    if (state.auth?.access_token) {
        headers['Authorization'] = `Bearer ${state.auth.access_token}`;
    }
    
    const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
    });
    
    if (response.status === 401) {
        // Token expired, try to refresh
        const refreshed = await refreshToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${state.auth.access_token}`;
            return fetch(`${CONFIG.API_BASE_URL}${endpoint}`, { ...options, headers });
        } else {
            logout();
            throw new Error('Session expired');
        }
    }
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    
    return response.json();
}

async function refreshToken() {
    if (!state.auth?.refresh_token) return false;
    
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: state.auth.refresh_token }),
        });
        
        if (response.ok) {
            const data = await response.json();
            state.auth.access_token = data.access_token;
            state.auth.refresh_token = data.refresh_token;
            saveAuth();
            return true;
        }
    } catch (e) {
        console.error('Token refresh failed:', e);
    }
    return false;
}

async function login(username, password) {
    const response = await fetch(`${CONFIG.API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(error.detail || 'Login failed');
    }
    
    const data = await response.json();
    state.auth = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        username,
    };
    saveAuth();
    return data;
}

function saveAuth() {
    sessionStorage.setItem('auth', JSON.stringify(state.auth));
}

function loadAuth() {
    const saved = sessionStorage.getItem('auth');
    if (saved) {
        state.auth = JSON.parse(saved);
    }
}

function clearAuth() {
    state.auth = null;
    sessionStorage.removeItem('auth');
}

function logout() {
    clearAuth();
    stopAutoRefresh();
    closeWebSocket();
    showScreen('login');
}

// ============================================
// Screen Management
// ============================================

function showScreen(screenName) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    if (screenName === 'login') {
        elements.loginScreen.classList.add('active');
    } else if (screenName === 'app') {
        elements.appScreen.classList.add('active');
    }
}

function showPage(pageName) {
    elements.pages.forEach(p => p.classList.remove('active'));
    const page = document.getElementById(`page-${pageName}`);
    if (page) page.classList.add('active');
    
    // Update nav active states
    document.querySelectorAll('.menu-item[data-page], .nav-item[data-page]').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });
    
    elements.pageTitle.textContent = pageName.charAt(0).toUpperCase() + pageName.slice(1);
    
    // Close menus
    closeSideMenu();
    closeMoreModal();
    
    // Load page data
    loadPageData(pageName);
}

function closeSideMenu() {
    elements.sideMenu.classList.remove('open');
    elements.menuOverlay.classList.remove('open');
}

function closeMoreModal() {
    closeModal(elements.moreModal);
}

function closeNotificationModal() {
    closeModal(elements.notificationModal);
}

// ============================================
// Data Loading
// ============================================

async function loadPageData(pageName) {
    try {
        switch (pageName) {
            case 'dashboard':
                await loadDashboardData();
                break;
            case 'zones':
                await loadZonesPageData();
                break;
            case 'alerts':
                await loadAlertsPageData();
                break;
            case 'reports':
                await loadReportsPageData();
                break;
            case 'ai':
                await loadAIPageData();
                break;
            case 'settings':
                await loadSettingsPageData();
                break;
        }
    } catch (error) {
        console.error(`Failed to load ${pageName}:`, error);
        showToast('Error', `Failed to load ${pageName}`, 'danger');
    }
}

async function loadAllData() {
    await Promise.all([
        fetchZones(),
        fetchDevices(),
        fetchMeasurements(),
        fetchAlerts(),
        fetchAlertRules(),
        fetchReports(),
        fetchRiskScores(),
    ]);
}

async function fetchZones() {
    state.zones = await apiRequest('/zones');
    populateZoneSelects();
    return state.zones;
}

async function fetchDevices() {
    state.devices = await apiRequest('/devices');
    return state.devices;
}

async function fetchMeasurements() {
    const promises = state.zones.map(zone => 
        apiRequest(`/measurements/latest?zone_id=${zone.id}`)
            .then(data => { state.measurements[zone.id] = data; })
            .catch(() => { state.measurements[zone.id] = []; })
    );
    await Promise.all(promises);
    return state.measurements;
}

async function fetchAlerts() {
    const [allAlerts, activeAlerts] = await Promise.all([
        apiRequest('/alerts?limit=200'),
        apiRequest('/alerts/active'),
    ]);
    state.alerts = allAlerts;
    state.activeAlerts = activeAlerts;
    updateAlertBadges();
    return { allAlerts, activeAlerts };
}

async function fetchAlertRules() {
    state.alertRules = await apiRequest('/alert-rules');
    return state.alertRules;
}

async function fetchReports() {
    state.reports = await apiRequest('/reports');
    return state.reports;
}

async function fetchRiskScores() {
    const promises = state.zones.map(zone =>
        apiRequest(`/ai/risk/${zone.id}`)
            .then(data => { state.riskScores[zone.id] = data; })
            .catch(() => { state.riskScores[zone.id] = null; })
    );
    await Promise.all(promises);
    return state.riskScores;
}

async function loadDashboardData() {
    await Promise.all([fetchMeasurements(), fetchAlerts()]);
    renderZoneCards();
    renderRealtimeChart();
    renderActiveAlerts();
    elements.dashboardLastUpdate.textContent = formatTimeAgo(new Date().toISOString());
}

async function loadZonesPageData() {
    if (state.zones.length === 0) await fetchZones();
    if (Object.keys(state.measurements).length === 0) await fetchMeasurements();
    renderZoneDetail(state.selectedZone);
}

async function loadAlertsPageData() {
    await fetchAlerts();
    renderAlertsTable();
}

async function loadReportsPageData() {
    await fetchReports();
    renderReportsTable();
    populateReportZoneSelect();
    setDefaultDateRange();
}

async function loadAIPageData() {
    await fetchRiskScores();
    renderRiskScores();
    populatePredictZoneSelect();
}

async function loadSettingsPageData() {
    await fetchAlertRules();
    renderAlertRulesTable();
    renderRelayControl();
}

function populateZoneSelects() {
    const options = state.zones.map(z => `<option value="${z.id}">${z.name}</option>`).join('');
    elements.zoneSelect.innerHTML = options;
    elements.reportZone.innerHTML = '<option value="">All Zones</option>' + options;
    elements.predictZone.innerHTML = options;
    
    if (!state.selectedZone || !state.zones.find(z => z.id === state.selectedZone)) {
        state.selectedZone = state.zones[0]?.id || 'prod-01';
    }
    elements.zoneSelect.value = state.selectedZone;
    elements.predictZone.value = state.selectedZone;
}

function populateReportZoneSelect() {
    const options = state.zones.map(z => `<option value="${z.id}">${z.name}</option>`).join('');
    elements.reportZone.innerHTML = '<option value="">All Zones</option>' + options;
}

function populatePredictZoneSelect() {
    const options = state.zones.map(z => `<option value="${z.id}">${z.name}</option>`).join('');
    elements.predictZone.innerHTML = options;
}

function setDefaultDateRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 7);
    elements.reportStartDate.value = start.toISOString().split('T')[0];
    elements.reportEndDate.value = end.toISOString().split('T')[0];
}

// ============================================
// Rendering Functions
// ============================================

function renderZoneCards() {
    elements.zoneGrid.innerHTML = '';
    
    state.zones.forEach(zone => {
        const measurements = state.measurements[zone.id] || [];
        const zoneAlerts = state.activeAlerts.filter(a => a.zone_id === zone.id);
        
        const criticalCount = zoneAlerts.filter(a => a.level === 'critical').length;
        const warningCount = zoneAlerts.filter(a => a.level === 'warning').length;
        
        let statusClass = 'normal';
        let statusText = 'Normal';
        if (criticalCount > 0) { statusClass = 'critical'; statusText = `${criticalCount} Critical`; }
        else if (warningCount > 0) { statusClass = 'warning'; statusText = `${warningCount} Warning`; }
        
        const temp = measurements.find(m => m.parameter === 'temperature');
        const hum = measurements.find(m => m.parameter === 'humidity');
        
        const card = document.createElement('div');
        card.className = 'zone-card';
        card.innerHTML = `
            <div class="zone-card-header">
                <span class="zone-card-title">${zone.name}</span>
                <span class="zone-card-status ${statusClass}">${statusText}</span>
            </div>
            <div class="zone-card-metrics">
                <div class="zone-metric">
                    <div class="zone-metric-label">Temperature</div>
                    <div class="zone-metric-value">${temp ? temp.value.toFixed(1) : 'N/A'}</div>
                </div>
                <div class="zone-metric">
                    <div class="zone-metric-label">Humidity</div>
                    <div class="zone-metric-value">${hum ? hum.value.toFixed(1) : 'N/A'}</div>
                </div>
            </div>
            <div class="zone-card-actions">
                <button class="btn btn-primary btn-sm btn-outline" onclick="showPage('zones'); setTimeout(() => selectZone('${zone.id}'), 100)">Details</button>
                <button class="btn btn-warning btn-sm btn-outline" onclick="showPage('alerts')">Alerts</button>
            </div>
        `;
        elements.zoneGrid.appendChild(card);
    });
}

function selectZone(zoneId) {
    state.selectedZone = zoneId;
    elements.zoneSelect.value = zoneId;
    renderZoneDetail(zoneId);
}

function renderZoneDetail(zoneId) {
    const zone = state.zones.find(z => z.id === zoneId);
    const measurements = state.measurements[zoneId] || [];
    const alerts = state.activeAlerts.filter(a => a.zone_id === zoneId);
    
    if (!zone) return;
    
    let html = `<div class="zone-detail-header"><h3>${zone.name}</h3><span class="text-muted">${zone.type}</span></div>`;
    
    // Metric cards
    Object.entries(PARAMETERS).forEach(([key, info]) => {
        const m = measurements.find(x => x.parameter === key);
        const zoneAlerts = alerts.filter(a => a.parameter === key);
        const critical = zoneAlerts.some(a => a.level === 'critical');
        const warning = zoneAlerts.some(a => a.level === 'warning');
        let cardClass = 'normal';
        if (critical) cardClass = 'critical';
        else if (warning) cardClass = 'warning';
        
        html += `
            <div class="zone-detail-card ${cardClass}">
                <div class="zone-detail-label">${info.name}</div>
                <div class="zone-detail-value">${m ? m.value.toFixed(1) : 'N/A'}<span class="zone-detail-unit">${info.unit}</span></div>
            </div>
        `;
    });
    
    elements.zoneDetail.innerHTML = html;
}

function renderRealtimeChart() {
    const ctx = elements.realtimeChart.getContext('2d');
    const paramKey = elements.chartParameter.value;
    const paramInfo = PARAMETERS[paramKey];
    
    const labels = state.zones.map(z => z.name);
    const data = state.zones.map(z => {
        const m = (state.measurements[z.id] || []).find(x => x.parameter === paramKey);
        return m ? m.value : null;
    });
    const colors = state.zones.map((_, i) => {
        const m = (state.measurements[state.zones[i].id] || []).find(x => x.parameter === paramKey);
        return m ? paramInfo.color : '#DEE2E6';
    });
    
    if (state.chartInstances.realtime) {
        state.chartInstances.realtime.destroy();
    }
    
    state.chartInstances.realtime = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: `${paramInfo.name} (${paramInfo.unit})`,
                data,
                backgroundColor: colors,
                borderColor: colors.map(c => c.replace('0.8', '1')),
                borderWidth: 1,
                borderRadius: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw !== null ? ctx.raw.toFixed(1) : 'N/A'} ${paramInfo.unit}`,
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: false,
                    min: paramInfo.min,
                    max: paramInfo.max,
                    grid: { color: 'rgba(0,0,0,0.05)' },
                },
                x: { grid: { display: false } },
            },
            animation: { duration: 500 },
        },
    });
}

function renderActiveAlerts() {
    if (state.activeAlerts.length === 0) {
        elements.activeAlertsList.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <h3>No Active Alerts</h3>
                <p>All zones are operating normally</p>
            </div>
        `;
        return;
    }
    
    // Sort by priority: critical > warning > predictive > info
    const sorted = [...state.activeAlerts].sort((a, b) => 
        (ALERT_LEVELS[b.level]?.priority || 0) - (ALERT_LEVELS[a.level]?.priority || 0)
    );
    
    elements.activeAlertsList.innerHTML = sorted.map(alert => {
        const levelInfo = ALERT_LEVELS[alert.level] || ALERT_LEVELS.info;
        return `
            <div class="alert-item ${alert.level}">
                <div class="alert-icon" style="background: ${levelInfo.color}20; color: ${levelInfo.color};">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        ${alert.level === 'critical' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>' : ''}
                        ${alert.level === 'warning' ? '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>' : ''}
                        ${alert.level === 'predictive' ? '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="12" r="3"></circle>' : ''}
                        ${alert.level === 'info' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>' : ''}
                    </svg>
                </div>
                <div class="alert-content">
                    <div class="alert-title">${alert.zone_id} - ${alert.parameter.replace('_', ' ')}</div>
                    <div class="alert-meta">
                        <span class="alert-value">${alert.value.toFixed(1)} ${alert.unit}</span>
                        <span>Threshold: ${alert.threshold.toFixed(1)} ${alert.unit}</span>
                        <span>${formatTimeAgo(alert.created_at)}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function renderAlertsTable() {
    const levelFilter = elements.alertLevelFilter.value;
    const statusFilter = elements.alertStatusFilter.value;
    
    let filtered = state.alerts;
    if (levelFilter) filtered = filtered.filter(a => a.level === levelFilter);
    if (statusFilter) filtered = filtered.filter(a => a.status === statusFilter);
    
    elements.alertsTableBody.innerHTML = filtered.slice(0, 100).map(alert => {
        const levelInfo = ALERT_LEVELS[alert.level] || ALERT_LEVELS.info;
        const statusInfo = ALERT_STATUSES[alert.status] || ALERT_STATUSES.open;
        
        return `
            <tr>
                <td>${formatDateTime(alert.created_at)}</td>
                <td>${alert.zone_id}</td>
                <td>${alert.parameter.replace('_', ' ')}</td>
                <td><span class="badge ${getAlertLevelClass(alert.level)}" style="background: ${levelInfo.color}20; color: ${levelInfo.color};">${levelInfo.label}</span></td>
                <td><span class="badge ${getAlertStatusClass(alert.status)}">${statusInfo.label}</span></td>
                <td>${alert.value.toFixed(1)} ${alert.unit}</td>
                <td>
                    ${alert.status === 'open' ? `
                        <button class="btn btn-warning btn-sm btn-outline" onclick="acknowledgeAlert('${alert.id}')">Ack</button>
                    ` : ''}
                    ${alert.status !== 'resolved' ? `
                        <button class="btn btn-success btn-sm btn-outline" onclick="resolveAlert('${alert.id}')">Resolve</button>
                    ` : ''}
                </td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="7" class="text-center text-muted py-4">No alerts found</td></tr>';
}

function renderReportsTable() {
    elements.reportsTableBody.innerHTML = state.reports.map(report => `
        <tr>
            <td>${report.id?.slice(0, 8) || '-'}</td>
            <td>${report.report_type}</td>
            <td>${report.format}</td>
            <td>${report.zone_id || 'All'}</td>
            <td><span class="badge ${getReportStatusClass(report.status)}">${report.status}</span></td>
            <td>${formatDateTime(report.generated_at)}</td>
            <td>
                ${report.status === 'completed' ? `
                    <button class="btn btn-primary btn-sm btn-outline" onclick="downloadReport('${report.id}')">Download</button>
                ` : ''}
            </td>
        </tr>
    `).join('') || '<tr><td colspan="7" class="text-center text-muted py-4">No reports generated</td></tr>';
}

function getReportStatusClass(status) {
    const classes = {
        completed: 'badge-success',
        pending: 'badge-warning',
        generating: 'badge-info',
        failed: 'badge-critical',
    };
    return classes[status] || 'badge-info';
}

function renderRiskScores() {
    elements.riskGrid.innerHTML = '';
    
    state.zones.forEach(zone => {
        const risk = state.riskScores[zone.id];
        if (!risk) return;
        
        const score = risk.score || 0;
        const level = risk.level || 'low';
        const factors = risk.factors || {};
        
        let levelClass = 'low';
        if (level === 'critical') levelClass = 'critical';
        else if (level === 'high') levelClass = 'high';
        else if (level === 'medium') levelClass = 'medium';
        
        const card = document.createElement('div');
        card.className = 'risk-card';
        card.innerHTML = `
            <div class="risk-zone">${zone.name}</div>
            <div class="risk-score ${levelClass}">
                <span class="risk-value">${score}</span>
            </div>
            <div class="risk-label">${level}</div>
            <div class="risk-factors">
                ${Object.entries(factors).map(([k, v]) => `<div>${k}: ${v}</div>`).join('')}
            </div>
        `;
        elements.riskGrid.appendChild(card);
    });
}

function renderAlertRulesTable() {
    elements.rulesTableBody.innerHTML = state.alertRules.map(rule => `
        <tr>
            <td>${rule.zone_id}</td>
            <td>${rule.parameter.replace('_', ' ')}</td>
            <td>${rule.warning_min !== null ? `${rule.warning_min} - ${rule.warning_max}` : 'N/A'}</td>
            <td>${rule.critical_min !== null ? `${rule.critical_min} - ${rule.critical_max}` : 'N/A'}</td>
            <td>${rule.min_duration_sec}s</td>
            <td><span class="badge ${rule.enabled ? 'badge-success' : 'badge-secondary'}">${rule.enabled ? 'Enabled' : 'Disabled'}</span></td>
        </tr>
    `).join('') || '<tr><td colspan="6" class="text-center text-muted py-4">No alert rules configured</td></tr>';
}

function renderRelayControl() {
    elements.relayControl.innerHTML = '';
    
    state.zones.forEach(zone => {
        const card = document.createElement('div');
        card.className = 'relay-card';
        
        let relaysHtml = '';
        zone.relays.forEach(relayId => {
            const device = state.devices.find(d => d.zone_id === zone.id && d.device_id === `relay-${relayId}`);
            const isOn = device?.status === 'online'; // Simplified
            
            relaysHtml += `
                <div class="relay-option">
                    <div class="relay-option-info">
                        <span class="relay-option-name">Relay ${relayId}</span>
                        <span class="relay-option-zone">${zone.name}</span>
                    </div>
                    <div>
                        <span class="relay-indicator ${isOn ? 'on' : ''}"></span>
                        <button class="btn btn-sm ${isOn ? 'btn-danger' : 'btn-success'} btn-outline" 
                                onclick="controlRelay('${zone.id}', ${relayId}, '${isOn ? 'off' : 'on'}')">
                            ${isOn ? 'Turn OFF' : 'Turn ON'}
                        </button>
                    </div>
                </div>
            `;
        });
        
        card.innerHTML = `
            <div class="relay-card-header">
                <span class="relay-card-title">${zone.name}</span>
            </div>
            ${relaysHtml}
        `;
        elements.relayControl.appendChild(card);
    });
}

// ============================================
// Actions
// ============================================

async function acknowledgeAlert(alertId) {
    try {
        await apiRequest(`/alerts/${alertId}/acknowledge`, { method: 'POST' });
        showToast('Success', 'Alert acknowledged', 'success');
        await fetchAlerts();
        renderAlertsTable();
        renderActiveAlerts();
        updateAlertBadges();
    } catch (error) {
        showToast('Error', error.message, 'danger');
    }
}

async function resolveAlert(alertId) {
    const confirmed = await showConfirm('Resolve Alert', 'Are you sure you want to resolve this alert?');
    if (!confirmed) return;
    
    try {
        await apiRequest(`/alerts/${alertId}/resolve`, { 
            method: 'POST',
            body: JSON.stringify({ resolution_notes: 'Resolved via mobile app' }),
        });
        showToast('Success', 'Alert resolved', 'success');
        await fetchAlerts();
        renderAlertsTable();
        renderActiveAlerts();
        updateAlertBadges();
    } catch (error) {
        showToast('Error', error.message, 'danger');
    }
}

async function generateReport() {
    const reportType = elements.reportType.value;
    const format = elements.reportFormat.value;
    const zoneId = elements.reportZone.value || null;
    const start = elements.reportStartDate.value;
    const end = elements.reportEndDate.value;
    
    if (!start || !end) {
        showToast('Error', 'Please select date range', 'warning');
        return;
    }
    
    elements.generateReportBtn.disabled = true;
    elements.generateReportBtn.innerHTML = '<span class="btn-loader"><div class="spinner"></div></span> Generating...';
    
    try {
        const report = await apiRequest('/reports', {
            method: 'POST',
            body: JSON.stringify({ report_type: reportType, format, zone_id: zoneId, start, end }),
        });
        
        elements.reportGenerationStatus.innerHTML = `
            <div class="alert alert-success">
                Report generation started (ID: ${report.id.slice(0, 8)}). Check history for completion.
            </div>
        `;
        
        await fetchReports();
        renderReportsTable();
    } catch (error) {
        showToast('Error', error.message, 'danger');
    } finally {
        elements.generateReportBtn.disabled = false;
        elements.generateReportBtn.innerHTML = '<span class="btn-text">Generate Report</span>';
    }
}

async function downloadReport(reportId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/reports/${reportId}/download`, {
            headers: { 'Authorization': `Bearer ${state.auth.access_token}` },
        });
        
        if (!response.ok) throw new Error('Download failed');
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report-${reportId.slice(0, 8)}.${elements.reportFormat.value}`;
        a.click();
        URL.revokeObjectURL(url);
        
        showToast('Success', 'Report downloaded', 'success');
    } catch (error) {
        showToast('Error', error.message, 'danger');
    }
}

async function getPredictions() {
    const zoneId = elements.predictZone.value;
    const horizon = parseInt(elements.predictHorizon.value) || 60;
    
    elements.predictBtn.disabled = true;
    elements.predictBtn.innerHTML = '<span class="btn-loader"><div class="spinner"></div></span> Predicting...';
    
    try {
        const data = await apiRequest('/ai/predict', {
            method: 'POST',
            body: JSON.stringify({ zone_id: zoneId, horizon_minutes: horizon }),
        });
        
        state.predictions = data;
        renderPredictions(data);
    } catch (error) {
        showToast('Error', error.message, 'danger');
    } finally {
        elements.predictBtn.disabled = false;
        elements.predictBtn.innerHTML = '<span class="btn-text">Get Predictions</span>';
    }
}

function renderPredictions(data) {
    if (!data.predictions || data.predictions.length === 0) {
        elements.predictionsResult.innerHTML = '<div class="empty-state"><p>No predictions available</p></div>';
        return;
    }
    
    elements.predictionsResult.innerHTML = `
        <div class="table-container">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Predicted Value</th>
                        <th>Confidence</th>
                        <th>Breach Risk</th>
                        <th>Time to Breach</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.predictions.map(p => `
                        <tr>
                            <td>${p.parameter.replace('_', ' ')}</td>
                            <td>${p.predicted_value.toFixed(1)} ${p.unit}</td>
                            <td>${(p.confidence * 100).toFixed(0)}%</td>
                            <td><span class="badge badge-${p.breach_risk}">${p.breach_risk}</span></td>
                            <td>${p.time_to_breach || 'N/A'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function controlRelay(zoneId, relayId, command) {
    try {
        await apiRequest(`/relay/${zoneId}/${relayId}`, {
            method: 'POST',
            body: JSON.stringify({ command }),
        });
        showToast('Success', `Relay ${relayId} turned ${command}`, 'success');
        await loadSettingsPageData(); // Refresh relay states
    } catch (error) {
        showToast('Error', error.message, 'danger');
    }
}

async function refreshRiskScores() {
    await fetchRiskScores();
    renderRiskScores();
    showToast('Success', 'Risk scores refreshed', 'success');
}

function updateAlertBadges() {
    const criticalCount = state.activeAlerts.filter(a => a.level === 'critical').length;
    const totalCount = state.activeAlerts.length;
    
    const badgeText = criticalCount > 0 ? criticalCount : totalCount;
    elements.notificationBadge.textContent = badgeText > 99 ? '99+' : badgeText;
    elements.alertsBadge.textContent = badgeText > 99 ? '99+' : badgeText;
    elements.bottomAlertsBadge.textContent = badgeText > 99 ? '99+' : badgeText;
    
    elements.notificationBadge.style.display = totalCount > 0 ? 'flex' : 'none';
    elements.alertsBadge.style.display = totalCount > 0 ? 'flex' : 'none';
    elements.bottomAlertsBadge.style.display = totalCount > 0 ? 'flex' : 'none';
}

// ============================================
// WebSocket
// ============================================

function connectWebSocket() {
    if (!state.auth?.access_token) return;
    
    try {
        state.ws = new WebSocket(`${CONFIG.WS_BASE_URL}?token=${state.auth.access_token}`);
        
        state.ws.onopen = () => {
            console.log('WebSocket connected');
            // Subscribe to all zones
            state.zones.forEach(zone => {
                state.ws.send(JSON.stringify({
                    type: 'subscribe',
                    channels: [
                        `measurements:${zone.id}`,
                        `alerts:${zone.id}`,
                        `devices:${zone.id}`,
                    ],
                }));
            });
        };
        
        state.ws.onmessage = (event) => {
            handleWebSocketMessage(JSON.parse(event.data));
        };
        
        state.ws.onclose = () => {
            console.log('WebSocket disconnected');
            scheduleReconnect();
        };
        
        state.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (error) {
        console.error('WebSocket connection failed:', error);
        scheduleReconnect();
    }
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'measurement':
            updateMeasurement(message.data);
            break;
        case 'alert':
            handleNewAlert(message.data);
            break;
        case 'alert_update':
            handleAlertUpdate(message);
            break;
        case 'device_status':
            handleDeviceStatus(message);
            break;
        case 'risk_score':
            handleRiskScore(message);
            break;
        case 'ai_prediction':
            handleAIPrediction(message);
            break;
    }
}

function updateMeasurement(data) {
    const zoneId = data.zone_id;
    const param = data.parameter;
    
    if (!state.measurements[zoneId]) state.measurements[zoneId] = [];
    
    const idx = state.measurements[zoneId].findIndex(m => m.parameter === param);
    if (idx >= 0) {
        state.measurements[zoneId][idx] = data;
    } else {
        state.measurements[zoneId].push(data);
    }
    
    // Update UI if on dashboard or zone page
    if (document.getElementById('page-dashboard')?.classList.contains('active')) {
        renderZoneCards();
        if (elements.chartParameter.value === param) renderRealtimeChart();
    }
    if (document.getElementById('page-zones')?.classList.contains('active') && state.selectedZone === zoneId) {
        renderZoneDetail(zoneId);
    }
}

function handleNewAlert(alert) {
    state.activeAlerts.unshift(alert);
    state.alerts.unshift(alert);
    
    // Show notification
    const levelInfo = ALERT_LEVELS[alert.level] || ALERT_LEVELS.info;
    showToast(
        `${levelInfo.label} Alert: ${alert.zone_id}`,
        `${alert.parameter.replace('_', ' ')}: ${alert.value.toFixed(1)} ${alert.unit} (threshold: ${alert.threshold.toFixed(1)} ${alert.unit})`,
        alert.level === 'critical' ? 'danger' : alert.level === 'warning' ? 'warning' : 'info'
    );
    
    updateAlertBadges();
    renderActiveAlerts();
    if (document.getElementById('page-alerts')?.classList.contains('active')) {
        renderAlertsTable();
    }
}

function handleAlertUpdate(data) {
    const idx = state.activeAlerts.findIndex(a => a.id === data.alert_id);
    if (idx >= 0) {
        if (data.status === 'resolved' || data.status === 'acknowledged') {
            state.activeAlerts.splice(idx, 1);
        } else {
            state.activeAlerts[idx].status = data.status;
        }
    }
    
    const allIdx = state.alerts.findIndex(a => a.id === data.alert_id);
    if (allIdx >= 0) {
        state.alerts[allIdx].status = data.status;
        if (data.acknowledged_by) state.alerts[allIdx].acknowledged_by = data.acknowledged_by;
        if (data.acknowledged_at) state.alerts[allIdx].acknowledged_at = data.acknowledged_at;
    }
    
    updateAlertBadges();
    renderActiveAlerts();
    if (document.getElementById('page-alerts')?.classList.contains('active')) {
        renderAlertsTable();
    }
}

function handleDeviceStatus(data) {
    const deviceIdx = state.devices.findIndex(d => d.device_id === data.device_id);
    if (deviceIdx >= 0) {
        state.devices[deviceIdx].status = data.status;
        state.devices[deviceIdx].last_seen = data.timestamp;
    }
    
    if (document.getElementById('page-settings')?.classList.contains('active')) {
        renderRelayControl();
    }
}

function handleRiskScore(data) {
    state.riskScores[data.zone_id] = data;
    if (document.getElementById('page-ai')?.classList.contains('active')) {
        renderRiskScores();
    }
}

function handleAIPrediction(data) {
    // Could update predictions display
    console.log('AI Prediction:', data);
}

function closeWebSocket() {
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }
    if (state.reconnectTimer) {
        clearTimeout(state.reconnectTimer);
        state.reconnectTimer = null;
    }
}

function scheduleReconnect() {
    if (state.reconnectTimer) return;
    state.reconnectTimer = setTimeout(() => {
        state.reconnectTimer = null;
        connectWebSocket();
    }, 5000);
}

// ============================================
// Auto Refresh
// ============================================

function startAutoRefresh() {
    stopAutoRefresh();
    state.refreshTimer = setInterval(async () => {
        try {
            await Promise.all([
                fetchMeasurements(),
                fetchAlerts(),
            ]);
            
            // Update current page
            const activePage = document.querySelector('.page.active')?.id?.replace('page-', '');
            if (activePage) {
                await loadPageData(activePage);
            }
        } catch (error) {
            console.error('Auto refresh failed:', error);
        }
    }, CONFIG.REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

// ============================================
// Event Listeners
// ============================================

function setupEventListeners() {
    // Login
    elements.loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        
        elements.loginBtn.classList.add('loading');
        elements.loginError.classList.add('hidden');
        
        try {
            await login(username, password);
            showToast('Welcome', `Logged in as ${username}`, 'success');
            initApp();
        } catch (error) {
            elements.loginError.textContent = error.message;
            elements.loginError.classList.remove('hidden');
            showToast('Error', error.message, 'danger');
        } finally {
            elements.loginBtn.classList.remove('loading');
        }
    });
    
    // Navigation
    document.querySelectorAll('[data-page]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const page = el.dataset.page;
            if (page === 'more') {
                openModal(elements.moreModal);
            } else {
                showPage(page);
            }
        });
    });
    
    // Menu toggles
    elements.menuToggle.addEventListener('click', () => {
        elements.sideMenu.classList.add('open');
        elements.menuOverlay.classList.add('open');
    });
    
    elements.closeMenu.addEventListener('click', closeSideMenu);
    elements.menuOverlay.addEventListener('click', closeSideMenu);
    
    elements.userMenuBtn.addEventListener('click', () => openModal(elements.moreModal));
    elements.notificationsBtn.addEventListener('click', () => {
        openModal(elements.notificationModal);
        renderNotificationList();
    });
    
    elements.closeMoreModal.addEventListener('click', closeMoreModal);
    elements.closeNotificationModal.addEventListener('click', closeNotificationModal);
    
    elements.moreModal.querySelector('.modal-backdrop').addEventListener('click', closeMoreModal);
    elements.notificationModal.querySelector('.modal-backdrop').addEventListener('click', closeNotificationModal);
    
    // Logout
    elements.logoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        logout();
    });
    elements.modalLogoutBtn.addEventListener('click', (e) => {
        e.preventDefault();
        logout();
    });
    
    // Zone select
    elements.zoneSelect.addEventListener('change', (e) => {
        state.selectedZone = e.target.value;
        renderZoneDetail(state.selectedZone);
    });
    
    // Chart parameter
    elements.chartParameter.addEventListener('change', renderRealtimeChart);
    
    // Alert filters
    elements.alertLevelFilter.addEventListener('change', renderAlertsTable);
    elements.alertStatusFilter.addEventListener('change', renderAlertsTable);
    
    // Report generation
    elements.generateReportBtn.addEventListener('click', generateReport);
    
    // AI predictions
    elements.predictBtn.addEventListener('click', getPredictions);
    elements.refreshRiskBtn.addEventListener('click', refreshRiskScores);
    
    // Close modals on escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSideMenu();
            closeMoreModal();
            closeNotificationModal();
            closeModal(elements.confirmModal);
            closeModal(elements.relayModal);
        }
    });
}

function renderNotificationList() {
    // Combine recent alerts and system notifications
    const notifications = [
        ...state.activeAlerts.slice(0, 10).map(a => ({
            type: 'alert',
            level: a.level,
            title: `${a.zone_id} - ${a.parameter.replace('_', ' ')}`,
            message: `Value: ${a.value.toFixed(1)} ${a.unit} (threshold: ${a.threshold.toFixed(1)} ${a.unit})`,
            time: a.created_at,
        })),
    ].sort((a, b) => new Date(b.time) - new Date(a.time));
    
    elements.notificationList.innerHTML = notifications.map(n => `
        <div class="notification-item">
            <div class="notification-icon ${n.level}">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    ${n.level === 'critical' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>' : ''}
                    ${n.level === 'warning' ? '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>' : ''}
                    ${n.level === 'info' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>' : ''}
                </svg>
            </div>
            <div class="notification-content">
                <div class="notification-title">${n.title}</div>
                <div class="notification-message">${n.message}</div>
                <div class="notification-time">${formatTimeAgo(n.time)}</div>
            </div>
        </div>
    `).join('') || '<div class="empty-state"><p>No notifications</p></div>';
}

// ============================================
// Initialization
// ============================================

async function initApp() {
    loadAuth();
    
    if (!state.auth) {
        showScreen('login');
        return;
    }
    
    // Set user info
    elements.userName.textContent = state.auth.username;
    elements.userRole.textContent = 'Administrator'; // Would come from token
    elements.userAvatar.textContent = state.auth.username.charAt(0).toUpperCase();
    
    showScreen('app');
    
    try {
        await loadAllData();
        connectWebSocket();
        startAutoRefresh();
        showPage('dashboard');
    } catch (error) {
        console.error('App initialization failed:', error);
        showToast('Error', 'Failed to initialize app', 'danger');
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    setupEventListeners();
    initApp();
});

// Handle visibility change
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && state.auth) {
        // Refresh when tab becomes visible
        loadAllData().catch(console.error);
    }
});

// Handle online/offline
window.addEventListener('online', () => {
    if (state.auth) {
        connectWebSocket();
        loadAllData().catch(console.error);
    }
});

window.addEventListener('offline', () => {
    closeWebSocket();
    showToast('Offline', 'You are offline. Some features may not work.', 'warning', 10000);
});

// Make functions globally accessible for inline handlers
window.showPage = showPage;
window.selectZone = selectZone;
window.acknowledgeAlert = acknowledgeAlert;
window.resolveAlert = resolveAlert;
window.downloadReport = downloadReport;
window.controlRelay = controlRelay;