import requests
from collections import deque
from datetime import datetime

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go


# -----------------------------
# Config
# -----------------------------
API_KEY = "ef6664386c0d72025026d0a8af45e04a"
CITY = "Meridian"
URL = "https://api.openweathermap.org/data/2.5/weather"

buffer = deque(maxlen=50)


# -----------------------------
# Fetch + Parse
# -----------------------------
def fetch_weather():
    params = {
        "q": CITY,
        "appid": API_KEY,
        "units": "imperial"
    }

    try:
        response = requests.get(URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        parsed = {
            "time": datetime.now(),
            "temp": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"]
        }

        buffer.append(parsed)

    except Exception as e:
        print("Error:", e)


# -----------------------------
# Dash App
# -----------------------------
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("🌤 Real-Time Weather Dashboard"),

    # Auto update every 10 sec
    dcc.Interval(id="interval", interval=10 * 1000, n_intervals=0),

    # Time-series chart
    dcc.Graph(id="temp-line-chart"),

    # Current state chart
    dcc.Graph(id="current-bar-chart")
])


# -----------------------------
# Update Callback
# -----------------------------
@app.callback(
    [Output("temp-line-chart", "figure"),
     Output("current-bar-chart", "figure")],
    [Input("interval", "n_intervals")]
)
def update_graph(n):
    fetch_weather()

    if not buffer:
        return {}, {}

    times = [x["time"] for x in buffer]
    temps = [x["temp"] for x in buffer]
    humidity = buffer[-1]["humidity"]
    pressure = buffer[-1]["pressure"]
    current_temp = buffer[-1]["temp"]

    # -----------------------------
    # 1. Time-series Line Chart
    # -----------------------------
    line_fig = go.Figure()

    line_fig.add_trace(go.Scatter(
        x=times,
        y=temps,
        mode='lines+markers',
        name='Temperature',
        line=dict(color='red'),
        hovertemplate="Time: %{x}<br>Temp: %{y}°F"
    ))

    line_fig.update_layout(
        title="Temperature Over Time",
        xaxis_title="Time",
        yaxis_title="Temperature (°F)",
        hovermode="x unified"
    )

    # -----------------------------
    # 2. Current State Bar Chart
    # -----------------------------
    bar_fig = go.Figure()

    bar_fig.add_trace(go.Bar(
        x=["Temperature", "Humidity", "Pressure"],
        y=[current_temp, humidity, pressure],
        marker=dict(color=["red", "blue", "green"]),
        hovertemplate="%{x}: %{y}"
    ))

    bar_fig.update_layout(
        title="Current Weather Conditions",
        yaxis_title="Value"
    )

    return line_fig, bar_fig


# -----------------------------
# Run App
# -----------------------------
app = dash.Dash(__name__)
server = app.server  # 👈 REQUIRED for deployment

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
