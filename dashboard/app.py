"""
Plotly Dash Dashboard
Environmental Monitoring Platform - Real-time visualization
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import dash
from dash import dcc, html, Input, Output, State, callback, clientside_callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000")
WS_BASE_URL = os.getenv("WS_BASE_URL", "ws://backend:8000/ws")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL_MS", "5000"))  # 5 seconds

# Zone configuration
ZONES = [
    {"id": "prod-01", "name": "Production Line 1", "type": "production", "relays": [1, 2]},
    {"id": "prod-02", "name": "Production Line 2", "type": "production", "relays": [1, 2]},
    {"id": "prod-03", "name": "Production Line 3", "type": "production", "relays": [1, 2]},
    {"id": "store-01", "name": "Storage Area 1", "type": "storage", "relays": [1, 2]},
    {"id": "store-02", "name": "Storage Area 2", "type": "storage", "relays": [1, 2]},
    {"id": "tech-01", "name": "Technical Room 1", "type": "technical", "relays": [1, 2]},
    {"id": "tech-02", "name": "Technical Room 2", "type": "technical", "relays": [1, 2]},
]

PARAMETERS = {
    "temperature": {"name": "Temperature", "unit": "°C", "color": "#FF6B6B", "min": -10, "max": 50},
    "humidity": {"name": "Humidity", "unit": "%", "color": "#4ECDC4", "min": 0, "max": 100},
    "noise": {"name": "Noise", "unit": "dB", "color": "#FFD93D", "min": 30, "max": 120},
    "air_quality": {"name": "Air Quality", "unit": "AQI", "color": "#6BCB77", "min": 0, "max": 500},
    "pm25": {"name": "PM2.5", "unit": "µg/m³", "color": "#FF8E72", "min": 0, "max": 150},
    "pm10": {"name": "PM10", "unit": "µg/m³", "color": "#A8D0E6", "min": 0, "max": 200},
    "voltage": {"name": "Voltage", "unit": "V", "color": "#C06C84", "min": 200, "max": 250},
}

ALERT_LEVELS = {
    "info": {"color": "#3498DB", "label": "Info", "priority": 1},
    "warning": {"color": "#F39C12", "label": "Warning", "priority": 2},
    "critical": {"color": "#E74C3C", "label": "Critical", "priority": 3},
    "predictive": {"color": "#9B59B6", "label": "Predictive", "priority": 4},
}

# Initialize Dash app
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
    title="Environmental Monitoring Platform",
    update_title=None,
)

server = app.server

# Health check endpoint for Docker
@server.route('/health')
def health_check():
    return {"status": "healthy", "service": "dashboard"}, 200

# Layout
app.layout = dbc.Container(
    fluid=True,
    className="p-0",
    children=[
        # Stores for data
        dcc.Store(id="auth-store", storage_type="session"),
        dcc.Store(id="zones-store"),
        dcc.Store(id="measurements-store"),
        dcc.Store(id="alerts-store"),
        dcc.Store(id="devices-store"),
        dcc.Store(id="websocket-store"),
        
        # Interval for polling
        dcc.Interval(id="refresh-interval", interval=REFRESH_INTERVAL, n_intervals=0),
        dcc.Interval(id="ws-reconnect-interval", interval=30000, n_intervals=0),
        
        # Login Modal
        dbc.Modal(
            id="login-modal",
            is_open=True,
            backdrop="static",
            keyboard=False,
            size="md",
            children=[
                dbc.ModalHeader(dbc.ModalTitle("Environmental Monitoring Platform")),
                dbc.ModalBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Label("Username", width=12),
                            dbc.Col([
                                dbc.Input(id="login-username", type="text", placeholder="Enter username", required=True),
                            ], width=12),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Password", width=12),
                            dbc.Col([
                                dbc.Input(id="login-password", type="password", placeholder="Enter password", required=True),
                            ], width=12),
                        ], className="mb-3"),
                        dbc.Alert(id="login-error", color="danger", is_open=False, dismissable=True),
                        dbc.Button("Login", id="login-button", color="primary", className="w-100", n_clicks=0),
                    ]),
                ]),
            ],
        ),
        
        # Main Layout (hidden until login)
        html.Div(id="main-layout", style={"display": "none"}, children=[
            # Header
            dbc.Navbar(
                dark=True,
                color="primary",
                className="mb-3",
                children=[
                    dbc.Container([
                        dbc.NavbarBrand([
                            html.I(className="fas fa-industry me-2"),
                            "Environmental Monitoring Platform"
                        ], href="#", className="fw-bold"),
                        dbc.Nav([
                            dbc.NavItem(dbc.NavLink("Dashboard", href="#", id="nav-dashboard", active=True)),
                            dbc.NavItem(dbc.NavLink("Alerts", href="#", id="nav-alerts")),
                            dbc.NavItem(dbc.NavLink("Reports", href="#", id="nav-reports")),
                            dbc.NavItem(dbc.NavLink("AI Insights", href="#", id="nav-ai")),
                            dbc.NavItem(dbc.NavLink("Settings", href="#", id="nav-settings")),
                        ], className="ms-auto", navbar=True),
                        dbc.DropdownMenu(
                            label=html.Span([
                                html.I(className="fas fa-user me-1"),
                                "User"
                            ]),
                            children=[
                                dbc.DropdownMenuItem("Profile", id="menu-profile"),
                                dbc.DropdownMenuItem("Notifications", id="menu-notifications"),
                                dbc.DropdownMenuItem(divider=True),
                                dbc.DropdownMenuItem("Logout", id="menu-logout", href="#"),
                            ],
                            nav=True,
                            in_navbar=True,
                        ),
                    ]),
                ],
            ),
            
            # Main Content
            dbc.Container(fluid=True, id="page-content"),
            
            # Footer
            html.Footer(
                className="text-center text-muted py-3 border-top",
                children=[
                    "Environmental Monitoring Platform © 2026 | ",
                    html.Span(id="connection-status", className="ms-2"),
                    " | ",
                    html.Span(id="last-update", className="ms-2"),
                ],
            ),
        ]),
        
        # Toast notifications
        dbc.Toast(
            id="notification-toast",
            header="Notification",
            is_open=False,
            dismissable=True,
            icon="primary",
            duration=5000,
            style={"position": "fixed", "top": 70, "right": 20, "zIndex": 9999, "minWidth": 300},
        ),
    ],
)

# ============================================
# Authentication Callbacks
# ============================================

@callback(
    Output("auth-store", "data"),
    Output("login-modal", "is_open"),
    Output("main-layout", "style"),
    Output("login-error", "children"),
    Output("login-error", "is_open"),
    Input("login-button", "n_clicks"),
    State("login-username", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def handle_login(n_clicks, username, password):
    if not n_clicks or not username or not password:
        return dash.no_update, True, {"display": "none"}, "", False
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            data={"username": username, "password": password},
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            auth_data = {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "username": username,
            }
            return auth_data, False, {"display": "block"}, "", False
        else:
            error = response.json().get("detail", "Login failed")
            return dash.no_update, True, {"display": "none"}, error, True
    except Exception as e:
        return dash.no_update, True, {"display": "none"}, f"Connection error: {str(e)}", True


@callback(
    Output("page-content", "children"),
    Input("auth-store", "data"),
    Input("nav-dashboard", "n_clicks"),
    Input("nav-alerts", "n_clicks"),
    Input("nav-reports", "n_clicks"),
    Input("nav-ai", "n_clicks"),
    Input("nav-settings", "n_clicks"),
    prevent_initial_call=True,
)
def render_page(auth_data, *args):
    if not auth_data:
        return html.Div()
    
    ctx = dash.callback_context
    trigger = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else "nav-dashboard"
    
    if trigger == "nav-alerts":
        return render_alerts_page()
    elif trigger == "nav-reports":
        return render_reports_page()
    elif trigger == "nav-ai":
        return render_ai_page()
    elif trigger == "nav-settings":
        return render_settings_page()
    else:
        return render_dashboard_page()


# ============================================
# Page Renderers
# ============================================

def render_dashboard_page():
    return html.Div([
        # Zone Overview Cards
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("Zone Overview", className="mb-0"),
                    ]),
                    dbc.CardBody([
                        html.Div(id="zone-cards"),
                    ]),
                ]),
            ], width=12, lg=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("Active Alerts", className="mb-0"),
                    ]),
                    dbc.CardBody([
                        html.Div(id="active-alerts-summary"),
                    ]),
                ]),
            ], width=12, lg=4),
        ], className="mb-3"),
        
        # Real-time Charts
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        dbc.Row([
                            dbc.Col(html.H5("Real-time Measurements", className="mb-0")),
                            dbc.Col([
                                dbc.Select(
                                    id="chart-parameter-select",
                                    options=[{"label": v["name"], "value": k} for k, v in PARAMETERS.items()],
                                    value="temperature",
                                    style={"width": "200px"},
                                ),
                            ], width="auto", className="text-end"),
                        ], className="align-items-center"),
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id="realtime-chart", config={"displayModeBar": False}),
                    ]),
                ]),
            ], width=12, lg=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Device Status", className="mb-0")),
                    dbc.CardBody([
                        html.Div(id="device-status-list"),
                    ]),
                ]),
            ], width=12, lg=4),
        ], className="mb-3"),
        
        # Zone Detail Charts
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        dbc.Row([
                            dbc.Col(html.H5("Zone Details", className="mb-0")),
                            dbc.Col([
                                dbc.Select(
                                    id="zone-detail-select",
                                    options=[{"label": z["name"], "value": z["id"]} for z in ZONES],
                                    value="prod-01",
                                    style={"width": "200px"},
                                ),
                            ], width="auto", className="text-end"),
                        ], className="align-items-center"),
                    ]),
                    dbc.CardBody([
                        html.Div(id="zone-detail-charts"),
                    ]),
                ]),
            ], width=12),
        ]),
    ])


def render_alerts_page():
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        dbc.Row([
                            dbc.Col(html.H5("Alert History", className="mb-0")),
                            dbc.Col([
                                dbc.ButtonGroup([
                                    dbc.Button("Acknowledge All", id="ack-all-btn", color="warning", size="sm", outline=True),
                                    dbc.Button("Export CSV", id="export-alerts-btn", color="secondary", size="sm", outline=True),
                                ]),
                            ], width="auto", className="text-end"),
                        ], className="align-items-center"),
                    ]),
                    dbc.CardBody([
                        html.Div(id="alerts-table"),
                    ]),
                ]),
            ], width=12),
        ]),
    ])


def render_reports_page():
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Generate Report", className="mb-0")),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Report Type"),
                                dbc.Select(
                                    id="report-type-select",
                                    options=[
                                        {"label": "Hourly", "value": "hourly"},
                                        {"label": "Daily", "value": "daily"},
                                        {"label": "Weekly", "value": "weekly"},
                                        {"label": "Monthly", "value": "monthly"},
                                        {"label": "Alert Summary", "value": "alert_summary"},
                                        {"label": "AI Weekly", "value": "ai_weekly"},
                                    ],
                                    value="daily",
                                ),
                            ], width=3),
                            dbc.Col([
                                dbc.Label("Format"),
                                dbc.Select(
                                    id="report-format-select",
                                    options=[
                                        {"label": "CSV", "value": "csv"},
                                        {"label": "PDF", "value": "pdf"},
                                        {"label": "JSON", "value": "json"},
                                    ],
                                    value="csv",
                                ),
                            ], width=3),
                            dbc.Col([
                                dbc.Label("Zone"),
                                dbc.Select(
                                    id="report-zone-select",
                                    options=[{"label": z["name"], "value": z["id"]} for z in ZONES],
                                    value="prod-01",
                                ),
                            ], width=3),
                            dbc.Col([
                                dbc.Label("Date Range"),
                                dcc.DatePickerRange(
                                    id="report-date-range",
                                    start_date=(datetime.now() - timedelta(days=7)).date(),
                                    end_date=datetime.now().date(),
                                    display_format="YYYY-MM-DD",
                                ),
                            ], width=3),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("Generate Report", id="generate-report-btn", color="primary", className="w-100"),
                            ], width=3),
                            dbc.Col([
                                html.Div(id="report-status"),
                            ], width=9),
                        ]),
                    ]),
                ]),
            ], width=12, lg=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Report History", className="mb-0")),
                    dbc.CardBody([
                        html.Div(id="reports-table"),
                    ]),
                ]),
            ], width=12, lg=6),
        ]),
    ])


def render_ai_page():
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        dbc.Row([
                            dbc.Col(html.H5("Zone Risk Scores", className="mb-0")),
                            dbc.Col([
                                dbc.Button("Refresh", id="refresh-risk-btn", color="primary", size="sm", outline=True),
                            ], width="auto", className="text-end"),
                        ], className="align-items-center"),
                    ]),
                    dbc.CardBody([
                        html.Div(id="risk-scores"),
                    ]),
                ]),
            ], width=12, lg=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("AI Predictions", className="mb-0")),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Zone"),
                                dbc.Select(
                                    id="ai-zone-select",
                                    options=[{"label": z["name"], "value": z["id"]} for z in ZONES],
                                    value="prod-01",
                                ),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Horizon (minutes)"),
                                dbc.Input(id="ai-horizon", type="number", value=60, min=5, max=1440, step=5),
                            ], width=4),
                            dbc.Col([
                                dbc.Label(" "),
                                dbc.Button("Predict", id="ai-predict-btn", color="primary", className="w-100"),
                            ], width=4),
                        ], className="mb-3"),
                        html.Div(id="ai-predictions"),
                    ]),
                ]),
            ], width=12, lg=6),
        ], className="mb-3"),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Weekly AI Report", className="mb-0")),
                    dbc.CardBody([
                        html.Div(id="ai-weekly-report"),
                    ]),
                ]),
            ], width=12),
        ]),
    ])


def render_settings_page():
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Alert Rules", className="mb-0")),
                    dbc.CardBody([
                        html.Div(id="alert-rules-table"),
                    ]),
                ]),
            ], width=12, lg=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Relay Control", className="mb-0")),
                    dbc.CardBody([
                        html.Div(id="relay-control-panel"),
                    ]),
                ]),
            ], width=12, lg=4),
        ]),
    ])


# ============================================
# Data Fetching Callbacks
# ============================================

def get_headers(auth_data):
    return {"Authorization": f"Bearer {auth_data['access_token']}"}


@callback(
    Output("zones-store", "data"),
    Output("devices-store", "data"),
    Output("connection-status", "children"),
    Output("last-update", "children"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
)
def fetch_static_data(n_intervals, auth_data):
    if not auth_data:
        return dash.no_update, dash.no_update, "Not connected", ""
    
    headers = get_headers(auth_data)
    zones_data = []
    devices_data = []
    status_text = "Disconnected"
    
    try:
        # Fetch zones
        resp = requests.get(f"{API_BASE_URL}/zones", headers=headers, timeout=5)
        if resp.status_code == 200:
            zones_data = resp.json()
        
        # Fetch devices
        resp = requests.get(f"{API_BASE_URL}/devices", headers=headers, timeout=5)
        if resp.status_code == 200:
            devices_data = resp.json()
        
        # Health check
        resp = requests.get(f"{API_BASE_URL}/health", timeout=3)
        if resp.status_code == 200:
            status_text = "Connected"
        else:
            status_text = "Degraded"
    except Exception:
        status_text = "Disconnected"
    
    return zones_data, devices_data, status_text, datetime.now().strftime("%H:%M:%S")


@callback(
    Output("measurements-store", "data"),
    Output("alerts-store", "data"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
    State("zones-store", "data"),
)
def fetch_dynamic_data(n_intervals, auth_data, zones_data):
    if not auth_data or not zones_data:
        return dash.no_update, dash.no_update
    
    headers = get_headers(auth_data)
    measurements = {}
    alerts = []
    
    try:
        # Fetch latest measurements for all zones
        for zone in zones_data:
            zone_id = zone["zone_id"]
            for param in PARAMETERS.keys():
                resp = requests.get(
                    f"{API_BASE_URL}/measurements/latest",
                    params={"zone_id": zone_id},
                    headers=headers,
                    timeout=5,
                )
                if resp.status_code == 200:
                    measurements.setdefault(zone_id, []).extend(resp.json())
        
        # Fetch active alerts
        resp = requests.get(
            f"{API_BASE_URL}/alerts/active",
            headers=headers,
            timeout=5,
        )
        if resp.status_code == 200:
            alerts = resp.json()
    except Exception:
        pass
    
    return measurements, alerts


# ============================================
# Dashboard Update Callbacks
# ============================================

@callback(
    Output("zone-cards", "children"),
    Input("measurements-store", "data"),
    Input("alerts-store", "data"),
    State("zones-store", "data"),
)
def update_zone_cards(measurements, alerts, zones_data):
    if not zones_data:
        return html.Div("Loading...")
    
    cards = []
    for zone in zones_data:
        zone_id = zone["zone_id"]
        zone_measurements = measurements.get(zone_id, [])
        zone_alerts = [a for a in alerts if a.get("zone_id") == zone_id]
        
        # Determine status
        critical_count = sum(1 for a in zone_alerts if a.get("level") == "critical")
        warning_count = sum(1 for a in zone_alerts if a.get("level") == "warning")
        
        if critical_count > 0:
            status_color = "danger"
            status_text = f"{critical_count} Critical"
        elif warning_count > 0:
            status_color = "warning"
            status_text = f"{warning_count} Warning"
        else:
            status_color = "success"
            status_text = "Normal"
        
        # Get latest values
        temp_val = next((m for m in zone_measurements if m.get("parameter") == "temperature"), {})
        hum_val = next((m for m in zone_measurements if m.get("parameter") == "humidity"), {})
        
        cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Strong(zone["name"]),
                        dbc.Badge(status_text, color=status_color, className="ms-2 float-end"),
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Small("Temperature", className="text-muted"),
                                html.H4(f"{temp_val.get('value', 'N/A')}°C", className="mb-1"),
                            ], width=6),
                            dbc.Col([
                                html.Small("Humidity", className="text-muted"),
                                html.H4(f"{hum_val.get('value', 'N/A')}%", className="mb-1"),
                            ], width=6),
                        ]),
                        html.Hr(className="my-2"),
                        dbc.ButtonGroup([
                            dbc.Button("Details", id={"type": "zone-detail-btn", "index": zone_id}, color="primary", size="sm", outline=True),
                            dbc.Button("Alerts", id={"type": "zone-alerts-btn", "index": zone_id}, color="warning", size="sm", outline=True),
                        ], className="w-100"),
                    ]),
                ], className="h-100"),
            ], width=12, md=6, lg=4)
        )
    
    return cards


@callback(
    Output("realtime-chart", "figure"),
    Input("measurements-store", "data"),
    Input("chart-parameter-select", "value"),
    State("zones-store", "data"),
)
def update_realtime_chart(measurements, parameter, zones_data):
    if not measurements or not zones_data:
        return go.Figure()
    
    fig = go.Figure()
    param_info = PARAMETERS[parameter]
    
    for zone in zones_data:
        zone_id = zone["zone_id"]
        zone_measurements = measurements.get(zone_id, [])
        param_data = next((m for m in zone_measurements if m.get("parameter") == parameter), None)
        
        if param_data:
            fig.add_trace(go.Bar(
                x=[zone["name"]],
                y=[param_data.get("value", 0)],
                name=zone["name"],
                marker_color=param_info["color"],
                text=[f"{param_data.get('value', 0):.1f}"],
                textposition="auto",
            ))
    
    fig.update_layout(
        title=f"{param_info['name']} by Zone",
        yaxis_title=f"{param_info['name']} ({param_info['unit']})",
        showlegend=False,
        height=350,
        margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    
    # Add threshold lines if we have alert rules
    # This would need alert rules data - simplified for now
    
    return fig


@callback(
    Output("device-status-list", "children"),
    Input("devices-store", "data"),
)
def update_device_status(devices_data):
    if not devices_data:
        return html.Div("Loading...")
    
    items = []
    for device in devices_data:
        status = device.get("status", "offline")
        badge_color = "success" if status == "online" else "secondary" if status == "offline" else "warning"
        
        items.append(
            dbc.ListGroupItem([
                dbc.Row([
                    dbc.Col([
                        html.Strong(device.get("device_id", "Unknown")),
                        html.Br(),
                        html.Small(device.get("zone_id", ""), className="text-muted"),
                    ]),
                    dbc.Col([
                        dbc.Badge(status.title(), color=badge_color, className="float-end"),
                    ], width="auto"),
                ]),
            ])
        )
    
    return dbc.ListGroup(items, flush=True)


@callback(
    Output("zone-detail-charts", "children"),
    Input("measurements-store", "data"),
    Input("zone-detail-select", "value"),
    State("zones-store", "data"),
)
def update_zone_detail_charts(measurements, zone_id, zones_data):
    if not measurements or not zone_id:
        return html.Div("Select a zone")
    
    zone_measurements = measurements.get(zone_id, [])
    if not zone_measurements:
        return html.Div("No data available for this zone")
    
    charts = []
    for param_key, param_info in PARAMETERS.items():
        param_data = next((m for m in zone_measurements if m.get("parameter") == param_key), None)
        if param_data:
            # Create gauge chart
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=param_data.get("value", 0),
                title={"text": f"{param_info['name']} ({param_info['unit']})"},
                gauge={
                    "axis": {"range": [param_info["min"], param_info["max"]]},
                    "bar": {"color": param_info["color"]},
                    "steps": [
                        {"range": [param_info["min"], param_info["max"] * 0.5], "color": "lightgray"},
                        {"range": [param_info["max"] * 0.5, param_info["max"] * 0.8], "color": "gray"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": param_info["max"] * 0.9,
                    },
                },
            ))
            fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20))
            
            charts.append(
                dbc.Col([
                    dcc.Graph(figure=fig, config={"displayModeBar": False}),
                ], width=12, md=6, lg=4)
            )
    
    return dbc.Row(charts, className="g-2")


@callback(
    Output("active-alerts-summary", "children"),
    Input("alerts-store", "data"),
)
def update_active_alerts_summary(alerts):
    if not alerts:
        return dbc.Alert("No active alerts", color="success", className="mb-0")
    
    # Group by level
    critical = [a for a in alerts if a.get("level") == "critical"]
    warning = [a for a in alerts if a.get("level") == "warning"]
    predictive = [a for a in alerts if a.get("level") == "predictive"]
    info = [a for a in alerts if a.get("level") == "info"]
    
    items = []
    for alert_list, level in [(critical, "critical"), (warning, "warning"), (predictive, "predictive"), (info, "info")]:
        for alert in alert_list:
            level_info = ALERT_LEVELS[level]
            items.append(
                dbc.ListGroupItem([
                    dbc.Row([
                        dbc.Col([
                            html.Strong(f"{alert.get('zone_id')} - {alert.get('parameter', '').replace('_', ' ').title()}"),
                            html.Br(),
                            html.Small(f"Value: {alert.get('value'):.1f} {alert.get('unit')} (Threshold: {alert.get('threshold'):.1f} {alert.get('unit')})", className="text-muted"),
                        ]),
                        dbc.Col([
                            dbc.Badge(level_info["label"], color=level_info["color"].replace("#", ""), className="float-end"),
                        ], width="auto"),
                    ]),
                ], className="py-2")
            )
    
    if not items:
        return dbc.Alert("No active alerts", color="success", className="mb-0")
    
    return dbc.ListGroup(items, flush=True)


# ============================================
# Alerts Page Callbacks
# ============================================

@callback(
    Output("alerts-table", "children"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
)
def update_alerts_table(n_intervals, auth_data):
    if not auth_data:
        return html.Div()
    
    headers = get_headers(auth_data)
    try:
        resp = requests.get(f"{API_BASE_URL}/alerts", headers=headers, timeout=5)
        if resp.status_code == 200:
            alerts = resp.json()
        else:
            return html.Div("Failed to load alerts")
    except Exception:
        return html.Div("Connection error")
    
    if not alerts:
        return dbc.Alert("No alerts found", color="info")
    
    # Create table
    rows = []
    for alert in alerts[:100]:  # Limit to 100
        level = alert.get("level", "info")
        level_info = ALERT_LEVELS[level]
        status = alert.get("status", "open")
        
        rows.append(html.Tr([
            html.Td(alert.get("created_at", "")[:19].replace("T", " ")),
            html.Td(alert.get("zone_id", "")),
            html.Td(alert.get("parameter", "").replace("_", " ").title()),
            html.Td(dbc.Badge(level_info["label"], color=level_info["color"].replace("#", ""))),
            html.Td(dbc.Badge(status.title(), color="success" if status == "resolved" else "warning" if status == "acknowledged" else "danger")),
            html.Td(f"{alert.get('value', 0):.1f} {alert.get('unit', '')}"),
            html.Td(f"{alert.get('threshold', 0):.1f} {alert.get('unit', '')}"),
            html.Td([
                dbc.Button("Ack", id={"type": "ack-alert-btn", "index": alert.get("id")}, size="sm", color="warning", outline=True, className="me-1"),
                dbc.Button("Resolve", id={"type": "resolve-alert-btn", "index": alert.get("id")}, size="sm", color="success", outline=True),
            ]),
        ]))
    
    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Time"), html.Th("Zone"), html.Th("Parameter"),
            html.Th("Level"), html.Th("Status"), html.Th("Value"),
            html.Th("Threshold"), html.Th("Actions"),
        ])),
        html.Tbody(rows),
    ], bordered=True, hover=True, responsive=True, striped=True)


# ============================================
# Reports Page Callbacks
# ============================================

@callback(
    Output("report-status", "children"),
    Output("reports-table", "children"),
    Input("generate-report-btn", "n_clicks"),
    State("report-type-select", "value"),
    State("report-format-select", "value"),
    State("report-zone-select", "value"),
    State("report-date-range", "start_date"),
    State("report-date-range", "end_date"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def generate_report(n_clicks, report_type, report_format, zone_id, start_date, end_date, auth_data):
    if not auth_data:
        return "Please login", dash.no_update
    
    headers = get_headers(auth_data)
    try:
        resp = requests.post(
            f"{API_BASE_URL}/reports",
            json={
                "report_type": report_type,
                "format": report_format,
                "zone_id": zone_id,
                "start": start_date,
                "end": end_date,
            },
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 201:
            report = resp.json()
            status = dbc.Alert(f"Report generation started (ID: {report['id']})", color="success")
        else:
            status = dbc.Alert(f"Failed: {resp.json().get('detail', 'Unknown error')}", color="danger")
    except Exception as e:
        status = dbc.Alert(f"Error: {str(e)}", color="danger")
    
    # Refresh reports list
    try:
        resp = requests.get(f"{API_BASE_URL}/reports", headers=headers, timeout=5)
        if resp.status_code == 200:
            reports = resp.json()
        else:
            reports = []
    except Exception:
        reports = []
    
    if not reports:
        table = dbc.Alert("No reports generated yet", color="info")
    else:
        rows = []
        for report in reports:
            rows.append(html.Tr([
                html.Td(report.get("id", "")[:8]),
                html.Td(report.get("report_type", "")),
                html.Td(report.get("format", "")),
                html.Td(report.get("zone_id", "") or "All"),
                html.Td(report.get("status", "")),
                html.Td(report.get("generated_at", "")[:19].replace("T", " ")),
                html.Td([
                    dbc.Button("Download", id={"type": "download-report-btn", "index": report.get("id")}, size="sm", color="primary", outline=True),
                ]),
            ]))
        table = dbc.Table([
            html.Thead(html.Tr([html.Th("ID"), html.Th("Type"), html.Th("Format"), html.Th("Zone"), html.Th("Status"), html.Th("Generated"), html.Th("Action")])),
            html.Tbody(rows),
        ], bordered=True, hover=True, responsive=True, striped=True)
    
    return status, table


# ============================================
# AI Page Callbacks
# ============================================

@callback(
    Output("risk-scores", "children"),
    Input("refresh-risk-btn", "n_clicks"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
)
def update_risk_scores(n_clicks, n_intervals, auth_data):
    if not auth_data:
        return html.Div()
    
    headers = get_headers(auth_data)
    risk_data = {}
    
    try:
        for zone in ZONES:
            resp = requests.get(f"{API_BASE_URL}/ai/risk/{zone['id']}", headers=headers, timeout=5)
            if resp.status_code == 200:
                risk_data[zone['id']] = resp.json()
    except Exception:
        pass
    
    if not risk_data:
        return dbc.Alert("AI service unavailable", color="warning")
    
    cards = []
    for zone_id, data in risk_data.items():
        zone = next((z for z in ZONES if z["id"] == zone_id), None)
        if not zone:
            continue
        
        score = data.get("score", 0)
        level = data.get("level", "low")
        factors = data.get("factors", {})
        
        if level == "critical":
            color = "danger"
        elif level == "high":
            color = "warning"
        elif level == "medium":
            color = "info"
        else:
            color = "success"
        
        cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4(zone["name"], className="mb-2"),
                        html.H1(f"{score}/100", className=f"text-{color} mb-2"),
                        dbc.Badge(level.title(), color=color, className="mb-2"),
                        html.Hr(),
                        html.Small("Factors:", className="text-muted d-block"),
                        html.Ul([
                            html.Li(f"{k}: {v}") for k, v in factors.items()
                        ], className="mb-0 small"),
                    ]),
                ], className="h-100"),
            ], width=12, md=6, lg=4)
        )
    
    return dbc.Row(cards)


@callback(
    Output("ai-predictions", "children"),
    Input("ai-predict-btn", "n_clicks"),
    State("ai-zone-select", "value"),
    State("ai-horizon", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def get_ai_predictions(n_clicks, zone_id, horizon, auth_data):
    if not auth_data:
        return html.Div()
    
    headers = get_headers(auth_data)
    try:
        resp = requests.post(
            f"{API_BASE_URL}/ai/predict",
            json={"zone_id": zone_id, "horizon_minutes": horizon},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
        else:
            return dbc.Alert(f"Failed: {resp.json().get('detail', 'Unknown error')}", color="danger")
    except Exception as e:
        return dbc.Alert(f"Error: {str(e)}", color="danger")
    
    if not data.get("predictions"):
        return dbc.Alert("No predictions available", color="info")
    
    rows = []
    for pred in data["predictions"]:
        rows.append(html.Tr([
            html.Td(pred.get("parameter", "").replace("_", " ").title()),
            html.Td(f"{pred.get('predicted_value', 0):.1f} {pred.get('unit', '')}"),
            html.Td(f"{pred.get('confidence', 0)*100:.0f}%"),
            html.Td(pred.get("breach_risk", "low").title()),
            html.Td(pred.get("time_to_breach", "N/A")),
        ]))
    
    return dbc.Table([
        html.Thead(html.Tr([html.Th("Parameter"), html.Th("Predicted"), html.Th("Confidence"), html.Th("Breach Risk"), html.Th("Time to Breach")])),
        html.Tbody(rows),
    ], bordered=True, hover=True, responsive=True, striped=True)


# ============================================
# Settings Page Callbacks
# ============================================

@callback(
    Output("alert-rules-table", "children"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
)
def update_alert_rules_table(n_intervals, auth_data):
    if not auth_data:
        return html.Div()
    
    headers = get_headers(auth_data)
    try:
        resp = requests.get(f"{API_BASE_URL}/alert-rules", headers=headers, timeout=5)
        if resp.status_code == 200:
            rules = resp.json()
        else:
            return html.Div("Failed to load rules")
    except Exception:
        return html.Div("Connection error")
    
    if not rules:
        return dbc.Alert("No alert rules configured", color="info")
    
    rows = []
    for rule in rules:
        rows.append(html.Tr([
            html.Td(rule.get("zone_id", "")),
            html.Td(rule.get("parameter", "").replace("_", " ").title()),
            html.Td(f"{rule.get('warning_min', 'N/A')} - {rule.get('warning_max', 'N/A')}" if rule.get('warning_min') else "N/A"),
            html.Td(f"{rule.get('critical_min', 'N/A')} - {rule.get('critical_max', 'N/A')}" if rule.get('critical_min') else "N/A"),
            html.Td(f"{rule.get('min_duration_sec', 0)}s"),
            html.Td(dbc.Badge("Enabled" if rule.get("enabled") else "Disabled", color="success" if rule.get("enabled") else "secondary")),
            html.Td([
                dbc.Button("Edit", id={"type": "edit-rule-btn", "index": f"{rule.get('zone_id')}:{rule.get('parameter')}"}, size="sm", color="primary", outline=True),
            ]),
        ]))
    
    return dbc.Table([
        html.Thead(html.Tr([html.Th("Zone"), html.Th("Parameter"), html.Th("Warning Range"), html.Th("Critical Range"), html.Th("Min Duration"), html.Th("Status"), html.Th("Action")])),
        html.Tbody(rows),
    ], bordered=True, hover=True, responsive=True, striped=True)


@callback(
    Output("relay-control-panel", "children"),
    Input("refresh-interval", "n_intervals"),
    State("auth-store", "data"),
)
def update_relay_control(n_intervals, auth_data):
    if not auth_data:
        return html.Div()
    
    panels = []
    for zone in ZONES:
        relays = []
        for relay_id in zone["relays"]:
            relays.append(
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H6(f"Relay {relay_id}", className="mb-2"),
                            dbc.ButtonGroup([
                                dbc.Button("ON", id={"type": "relay-btn", "index": f"{zone['id']}:{relay_id}:on"}, color="success", size="sm", outline=True),
                                dbc.Button("OFF", id={"type": "relay-btn", "index": f"{zone['id']}:{relay_id}:off"}, color="danger", size="sm", outline=True),
                                dbc.Button("Toggle", id={"type": "relay-btn", "index": f"{zone['id']}:{relay_id}:toggle"}, color="warning", size="sm", outline=True),
                            ], className="w-100"),
                        ]),
                    ]),
                ], width=6)
            )
        
        panels.append(
            dbc.Card([
                dbc.CardHeader(html.H6(zone["name"])),
                dbc.CardBody([
                    dbc.Row(relays, className="g-2"),
                ]),
            ], className="mb-2")
        )
    
    return panels


# ============================================
# WebSocket Integration (Client-side)
# ============================================

app.clientside_callback(
    """
    function(n_intervals, auth_data) {
        if (!auth_data || !auth_data.access_token) {
            return '';
        }
        // WebSocket connection would be established here
        // For now, we rely on polling via refresh-interval
        return '';
    }
    """,
    Output("websocket-store", "data"),
    Input("ws-reconnect-interval", "n_intervals"),
    State("auth-store", "data"),
)


# ============================================
# Download Report Callback
# ============================================

@callback(
    Output("notification-toast", "children"),
    Output("notification-toast", "is_open"),
    Output("notification-toast", "header"),
    Output("notification-toast", "icon"),
    Input({"type": "download-report-btn", "index": dash.ALL}, "n_clicks"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def download_report(n_clicks_list, auth_data):
    if not auth_data or not any(n_clicks_list):
        return dash.no_update, False, "", "primary"
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, False, "", "primary"
    
    report_id = ctx.triggered[0]["prop_id"].split('"index":"')[1].split('"')[0]
    headers = get_headers(auth_data)
    
    try:
        resp = requests.get(f"{API_BASE_URL}/reports/{report_id}/download", headers=headers, timeout=10)
        if resp.status_code == 200:
            # In a real app, we'd trigger browser download
            return f"Report {report_id[:8]} downloaded", True, "Download Ready", "success"
        else:
            return f"Download failed: {resp.json().get('detail', 'Error')}", True, "Error", "danger"
    except Exception as e:
        return f"Error: {str(e)}", True, "Error", "danger"


# ============================================
# Relay Control Callback
# ============================================

@callback(
    Output("notification-toast", "children", allow_duplicate=True),
    Output("notification-toast", "is_open", allow_duplicate=True),
    Output("notification-toast", "header", allow_duplicate=True),
    Output("notification-toast", "icon", allow_duplicate=True),
    Input({"type": "relay-btn", "index": dash.ALL}, "n_clicks"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def control_relay(n_clicks_list, auth_data):
    if not auth_data or not any(n_clicks_list):
        return dash.no_update, False, "", "primary"
    
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, False, "", "primary"
    
    # Parse index: zone_id:relay_id:command
    index = ctx.triggered[0]["prop_id"].split('"index":"')[1].split('"')[0]
    zone_id, relay_id, command = index.split(":")
    
    headers = get_headers(auth_data)
    try:
        resp = requests.post(
            f"{API_BASE_URL}/relay/{zone_id}/{relay_id}",
            params={"command": command},
            headers=headers,
            timeout=5,
        )
        if resp.status_code == 200:
            return f"Relay {relay_id} in {zone_id} set to {command}", True, "Success", "success"
        else:
            return f"Failed: {resp.json().get('detail', 'Error')}", True, "Error", "danger"
    except Exception as e:
        return f"Error: {str(e)}", True, "Error", "danger"


# ============================================
# Main
# ============================================

if __name__ == "__main__":
    app.run_server(
        host="0.0.0.0",
        port=8050,
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )