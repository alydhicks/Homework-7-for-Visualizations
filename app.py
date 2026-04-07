import os

import requests
from collections import deque
from datetime import datetime, timezone
from threading import Thread, Lock
import time

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go


API_KEY = "ef6664386c0d72025026d0a8af45e04a" # Directly assign the API key


class OpenWeatherBufferStream:
    def __init__(
        self,
        api_key: str,
        lat: float,
        lon: float,
        buffer_size: int = 100,
        units: str = "metric",
        poll_interval: int = 60,   # seconds; adjust as needed
        timeout: int = 10
    ):
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.units = units
        self.poll_interval = poll_interval
        self.timeout = timeout

        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        self.buffer = deque(maxlen=buffer_size)
        self.session = requests.Session()

        self.last_fetch_time = None
        self.last_api_timestamp = None
        self.lock = Lock()

    def build_params(self):
        return {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": self.units
        }

    def fetch_data(self):
        try:
            response = self.session.get(
                self.base_url,
                params=self.build_params(),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] API request failed: {e}")
            return None

    def parse_and_validate(self, data):
        try:
            required_fields = ["weather", "main", "wind", "dt", "name", "sys"]
            missing = [field for field in required_fields if field not in data]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")

            if not isinstance(data["weather"], list) or len(data["weather"]) == 0:
                raise ValueError("'weather' must be a non-empty list")

            parsed = {
                "city": data["name"],
                "country": data["sys"].get("country"),
                "api_timestamp_unix": data["dt"],
                "api_timestamp_utc": datetime.fromtimestamp(
                    data["dt"], tz=timezone.utc
                ),
                "retrieved_at_utc": datetime.now(timezone.utc),
                "temperature": data["main"].get("temp"),
                "feels_like": data["main"].get("feels_like"),
                "humidity": data["main"].get("humidity"),
                "pressure": data["main"].get("pressure"),
                "weather_main": data["weather"][0].get("main"),
                "weather_description": data["weather"][0].get("description"),
                "wind_speed": data["wind"].get("speed"),
                "wind_deg": data["wind"].get("deg"),
                "clouds_percent": data.get("clouds", {}).get("all"),
                "visibility": data.get("visibility")
            }

            if parsed["temperature"] is None:
                raise ValueError("Temperature missing")
            if parsed["humidity"] is None:
                raise ValueError("Humidity missing")

            return parsed

        except (ValueError, TypeError) as e:
            print(f"[ERROR] Data validation failed: {e}")
            return None

    def update_buffer(self, record):
        with self.lock:
            self.buffer.append(record)
            self.last_fetch_time = datetime.now(timezone.utc)
            self.last_api_timestamp = record["api_timestamp_unix"]

    def get_buffer_data(self):
        with self.lock:
            return list(self.buffer)

    def stream(self):
        print("[INFO] Starting OpenWeather polling...")
        while True:
            raw_data = self.fetch_data()
            if raw_data is not None:
                parsed = self.parse_and_validate(raw_data)
                if parsed is not None:
                    self.update_buffer(parsed)
                    print(
                        f"[DATA] {parsed['city']} | "
                        f"{parsed['temperature']}° | "
                        f"{parsed['weather_main']} | "
                        f"{parsed['api_timestamp_utc'].isoformat()}"
                    )
            time.sleep(self.poll_interval)


# -----------------------------
# Configuration
# -----------------------------
API_KEY = "ef6664386c0d72025026d0a8af45e04a"
LAT = 32.3643
LON = -88.7037

weather_stream = OpenWeatherBufferStream(
    api_key=API_KEY,
    lat=LAT,
    lon=LON,
    buffer_size=100,
    units="metric",
    poll_interval=60
)

# Start data collection in background thread
thread = Thread(target=weather_stream.stream, daemon=True)
thread.start()


# build app
app = dash.Dash(__name__)
server = app.server


# -----------------------------
# Dash App
# -----------------------------
app = dash.Dash(__name__)

app.layout = html.Div(
    style={"backgroundColor": "#f4f7fb", "padding": "20px", "fontFamily": "Arial"},
    children=[
        html.H1(
            "OpenWeather Live Dashboard",
            style={"textAlign": "center", "color": "#1f3b73"}
        ),

        html.Div(
            id="status-text",
            style={
                "textAlign": "center",
                "fontSize": "18px",
                "marginBottom": "20px",
                "color": "#2c3e50"
            }
        ),

        dcc.Graph(id="time-series-chart"),
        dcc.Graph(id="current-state-chart"),

        dcc.Interval(
            id="interval-component",
            interval=60 * 1000,  # 60 seconds in milliseconds
            n_intervals=0
        )
    ]
)


@app.callback(
    Output("status-text", "children"),
    Output("time-series-chart", "figure"),
    Output("current-state-chart", "figure"),
    Input("interval-component", "n_intervals")
)
def update_dashboard(n):
    data = weather_stream.get_buffer_data()

    if not data:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            title="Waiting for data...",
            template="plotly_white"
        )
        return "Collecting weather data...", empty_fig, empty_fig

    times = [entry["retrieved_at_utc"] for entry in data]
    temps = [entry["temperature"] for entry in data]
    humidity = [entry["humidity"] for entry in data]
    wind_speed = [entry["wind_speed"] for entry in data]

    latest = data[-1]

    # --------------------------------
    # 1. Time-series line chart
    # --------------------------------
    line_fig = go.Figure()

    line_fig.add_trace(go.Scatter(
        x=times,
        y=temps,
        mode="lines+markers",
        name="Temperature (°C)",
        line=dict(color="red", width=3),
        marker=dict(size=7),
        hovertemplate=(
            "Time: %{x}<br>"
            "Temperature: %{y} °C<br>"
            "<extra></extra>"
        )
    ))

    line_fig.add_trace(go.Scatter(
        x=times,
        y=humidity,
        mode="lines+markers",
        name="Humidity (%)",
        line=dict(color="blue", width=3, dash="dash"),
        marker=dict(size=7),
        yaxis="y2",
        hovertemplate=(
            "Time: %{x}<br>"
            "Humidity: %{y}%<br>"
            "<extra></extra>"
        )
    ))

    line_fig.update_layout(
        title="Weather Trends Over Time",
        xaxis=dict(
            title="Timestamp",
            showgrid=True,
            rangeslider=dict(visible=True)
        ),
        yaxis=dict(
            title="Temperature (°C)",
            titlefont=dict(color="red"),
            tickfont=dict(color="red")
        ),
        yaxis2=dict(
            title="Humidity (%)",
            titlefont=dict(color="blue"),
            tickfont=dict(color="blue"),
            overlaying="y",
            side="right"
        ),
        template="plotly_white",
        hovermode="x unified",
        legend=dict(x=0.01, y=0.99),
        height=500
    )

    # --------------------------------
    # 2. Current-state bar chart
    # --------------------------------
    current_fig = go.Figure()

    current_fig.add_trace(go.Bar(
        x=["Temperature (°C)", "Feels Like (°C)", "Humidity (%)", "Wind Speed", "Pressure"],
        y=[
            latest["temperature"],
            latest["feels_like"],
            latest["humidity"],
            latest["wind_speed"] if latest["wind_speed"] is not None else 0,
            latest["pressure"]
        ],
        marker=dict(
            color=["red", "orange", "blue", "green", "purple"]
        ),
        hovertemplate="%{x}: %{y}<extra></extra>"
    ))

    current_fig.update_layout(
        title="Current Weather State",
        xaxis_title="Metric",
        yaxis_title="Value",
        template="plotly_white",
        height=500
    )

    status = (
        f"Latest update: {latest['retrieved_at_utc'].strftime('%Y-%m-%d %H:%M:%S UTC')} | "
        f"{latest['city']}, {latest['country']} | "
        f"{latest['weather_main']} ({latest['weather_description']})"
    )

    return status, line_fig, current_fig


if __name__ == "__main__":
    app.run(debug=True)

    server = app.server
