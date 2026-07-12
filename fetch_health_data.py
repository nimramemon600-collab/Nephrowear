"""
NephroWear Study — Automatic Health Data Fetcher
Runs daily via GitHub Actions to pull P3 data from Google Health API
and update p3_data.json which the dashboard reads on load.
"""

import os, json, requests
from datetime import datetime, timedelta, timezone

# ── Credentials from GitHub Secrets ──────────────────────
CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

BASE_URL = "https://health.googleapis.com/v1"

def get_access_token():
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type":    "refresh_token"
    })
    resp.raise_for_status()
    print("✓ Access token obtained")
    return resp.json()["access_token"]

def fetch_sleep(token, days=30):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    resp = requests.get(f"{BASE_URL}/users/-/sleepSessions",
        headers={"Authorization": f"Bearer {token}"},
        params={"startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endTime":   end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    if resp.status_code == 200:
        sessions = resp.json().get("sleepSessions", [])
        print(f"✓ Fetched {len(sessions)} sleep sessions")
        return sessions
    print(f"✗ Sleep failed: {resp.status_code} {resp.text[:200]}")
    return []

def fetch_health_metrics(token, days=30):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    resp = requests.get(f"{BASE_URL}/users/-/healthMetrics",
        headers={"Authorization": f"Bearer {token}"},
        params={"startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endTime":   end.strftime("%Y-%m-%dT%H:%M:%SZ")})
    if resp.status_code == 200:
        print("✓ Fetched health metrics")
        return resp.json()
    print(f"✗ Metrics failed: {resp.status_code} {resp.text[:200]}")
    return {}

def process_sleep(sessions):
    daily = {}
    for s in sessions:
        try:
            start_time = s.get("startTime", "")
            date = start_time[:10]
            score = s.get("sleepScore", {}).get("overallSleepScore", None)
            light = deep = rem = awake = 0
            for stage in s.get("sleepStages", []):
                t = stage.get("type", "")
                mins = stage.get("durationMinutes", 0)
                if "LIGHT" in t:   light  += mins
                elif "DEEP" in t:  deep   += mins
                elif "REM" in t:   rem    += mins
                elif "AWAKE" in t: awake  += mins
            if date not in daily or (score and daily[date]["score"] and score > daily[date]["score"]):
                daily[date] = {"date": date, "score": round(score,1) if score else None,
                    "light": round(light,1), "deep": round(deep,1),
                    "rem": round(rem,1), "awake": round(awake,1),
                    "total_sleep_hrs": round((light+deep+rem)/60, 2),
                    "start_time": start_time[11:16], "end_time": s.get("endTime","")[11:16]}
        except Exception as e:
            print(f"  Warning: {e}")
    return dict(sorted(daily.items()))

def process_metrics(metrics):
    result = {"resting_hr": {}, "hrv": {}}
    for entry in metrics.get("restingHeartRate", {}).get("data", []):
        try:
            date = entry.get("time","")[:10]
            val = entry.get("value",{}).get("fpVal", None)
            if val: result["resting_hr"][date] = round(val, 1)
        except: pass
    for entry in metrics.get("hrvRmssd", {}).get("data", []):
        try:
            date = entry.get("time","")[:10]
            val = entry.get("value",{}).get("fpVal", None)
            if val: result["hrv"][date] = round(val, 1)
        except: pass
    print(f"✓ HR days: {len(result['resting_hr'])}, HRV days: {len(result['hrv'])}")
    return result

def main():
    print("=" * 50)
    print(f"NephroWear Auto-Update — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)
    try:
        token        = get_access_token()
        sleep_data   = process_sleep(fetch_sleep(token))
        metrics_data = process_metrics(fetch_health_metrics(token))
        output = {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "participant": "P3", "study_start": "2026-07-06",
            "sleep": sleep_data, "resting_hr": metrics_data["resting_hr"],
            "hrv": metrics_data["hrv"]
        }
        with open("p3_data.json", "w") as f:
            json.dump(output, f, indent=2)
        print(f"✅ SUCCESS — {len(sleep_data)} sleep days, {len(metrics_data['resting_hr'])} HR days")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback; traceback.print_exc()
        with open("p3_data.json", "w") as f:
            json.dump({"last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "error": str(e), "sleep": {}, "resting_hr": {}, "hrv": {}}, f)

if __name__ == "__main__":
    main()
