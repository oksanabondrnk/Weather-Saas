from flask import Flask, request, jsonify
from datetime import datetime, timezone
import requests
import os

app = Flask(__name__)

SECURITY_TOKEN      = os.getenv("SECURITY_TOKEN", "")
VISUAL_CROSSING_KEY = os.getenv("VISUAL_CROSSING_KEY", "")
AI_KEY              = os.getenv("AI_KEY", "")

def validate_request(data):
    for field in ["token", "requester_name", "location", "date"]:
        if field not in data:
            return f"Missing required field: '{field}'"
    if data["token"] != SECURITY_TOKEN:
        return "Invalid security token"
    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError:
        return "Field 'date' must be in YYYY-MM-DD format"
    return None

def fetch_weather(location, date):
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{requests.utils.quote(location)}/{date}/{date}"
    params = {"unitGroup": "metric", "key": VISUAL_CROSSING_KEY, "contentType": "json", "include": "hours,days"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    raw = resp.json()
    day = raw["days"][0]
    hours = [{"time": h.get("datetime"), "temp_c": h.get("temp"), "feels_like_c": h.get("feelslike"), "wind_kph": h.get("windspeed"), "humidity": h.get("humidity"), "conditions": h.get("conditions")} for h in day.get("hours", [])]
    return {"temp_c": day.get("temp"), "temp_max_c": day.get("tempmax"), "temp_min_c": day.get("tempmin"), "feels_like_c": day.get("feelslike"), "wind_kph": day.get("windspeed"), "wind_gust_kph": day.get("windgust"), "pressure_mb": day.get("pressure"), "humidity": day.get("humidity"), "precip_mm": day.get("precip"), "precip_prob": day.get("precipprob"), "snow_cm": day.get("snow"), "cloud_cover": day.get("cloudcover"), "visibility_km": day.get("visibility"), "uv_index": day.get("uvindex"), "sunrise": day.get("sunrise"), "sunset": day.get("sunset"), "conditions": day.get("conditions"), "description": day.get("description"), "hourly": hours}

def ask_ai(weather, location, date):
    if not AI_KEY:
        return "AI recommendations unavailable (no API key configured)."
    prompt = f"Weather for {location} on {date}: {weather['temp_c']}C (feels like {weather['feels_like_c']}C), wind {weather['wind_kph']} kph, humidity {weather['humidity']}%, conditions: {weather['conditions']}. Give outfit recommendations and tips. Be concise and friendly."
    headers = {"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"}
    body = {"model": "stepfun/step-3.5-flash:free", "messages": [{"role": "user", "content": prompt}]}
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})

@app.route("/weather", methods=["POST"])
def weather():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400
    err = validate_request(data)
    if err:
        return jsonify({"error": err}), 401 if "token" in err.lower() else 400
    try:
        weather_data = fetch_weather(data["location"], data["date"])
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to reach weather service: {e}"}), 502
    return jsonify({"requester_name": data["requester_name"], "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "location": data["location"], "date": data["date"], "weather": weather_data})

@app.route("/weather/ai", methods=["POST"])
def weather_ai():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400
    err = validate_request(data)
    if err:
        return jsonify({"error": err}), 401 if "token" in err.lower() else 400
    try:
        weather_data = fetch_weather(data["location"], data["date"])
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to reach weather service: {e}"}), 502
    try:
        ai_advice = ask_ai(weather_data, data["location"], data["date"])
    except requests.RequestException as e:
        return jsonify({"error": f"Failed to reach AI service: {e}"}), 502
    return jsonify({"requester_name": data["requester_name"], "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "location": data["location"], "date": data["date"], "weather": weather_data, "outfit_recommendation": ai_advice})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
