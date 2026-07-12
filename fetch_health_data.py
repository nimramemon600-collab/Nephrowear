"""
NephroWear Study — Automatic Health Data Fetcher v3
Corrected Google Health API v4 endpoints and request formats
"""

import os, json, requests
from datetime import datetime, timedelta, timezone

CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

BASE = "https://health.googleapis.com/v4/users/me/dataTypes"

def get_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"
    })
    r.raise_for_status()
    print("✓ Access token obtained")
    return r.json()["access_token"]

def fetch_list(token, data_type, filter_expr):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{data_type}/dataPoints:list"
    params = {"filter": filter_expr, "pageSize": "1000"}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        points = r.json().get("dataPoints", [])
        print(f"✓ {data_type}: {len(points)} points")
        return points
    print(f"✗ {data_type} failed: {r.status_code} — {r.text[:400]}")
    return []

def fetch_daily_rollup(token, data_type, start, end):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{data_type}/dataPoints:dailyRollUp"
    body = {"range": {"startTime": f"{start}T00:00:00Z", "endTime": f"{end}T23:59:59Z"}}
    r = requests.post(url, headers=headers, json=body)
    if r.status_code == 200:
        points = r.json().get("rollupDataPoints", [])
        print(f"✓ {data_type}: {len(points)} days")
        return points
    print(f"✗ {data_type} rollup failed: {r.status_code} — {r.text[:400]}")
    return []

def process_sleep(points):
    daily = {}
    for p in points:
        sleep = p.get("sleep", {})
        interval = sleep.get("interval", {})
        start_str = interval.get("startTime", "")
        if not start_str: continue
        date = start_str[:10]
        stages = sleep.get("stages", [])
        light = deep = rem = awake = 0
        for stage in stages:
            stype = stage.get("type", "")
            try:
                s = datetime.fromisoformat(stage["startTime"].replace("Z","+00:00"))
                e = datetime.fromisoformat(stage["endTime"].replace("Z","+00:00"))
                mins = (e - s).total_seconds() / 60
            except: continue
            if stype == "LIGHT":    light  += mins
            elif stype == "DEEP":   deep   += mins
            elif stype == "REM":    rem    += mins
            elif stype == "AWAKE":  awake  += mins
        summary = sleep.get("summary", {})
        score = summary.get("sleepScore", {}).get("overallSleepScore", None)
        total = light + deep + rem
        if date not in daily or (score and (daily[date].get("score") or 0) < score):
            daily[date] = {"date": date, "score": round(score,1) if score else None,
                "light": round(light,1), "deep": round(deep,1),
                "rem": round(rem,1), "awake": round(awake,1),
                "total_sleep_hrs": round(total/60,2),
                "start_time": start_str[11:16], "end_time": interval.get("endTime","")[11:16]}
    return dict(sorted(daily.items()))

def process_rhr(points):
    result = {}
    for p in points:
        rhr = p.get("dailyRestingHeartRate", {})
        civil = rhr.get("civilTime", {}).get("date", {})
        date = f"{civil.get('year')}-{civil.get('month',0):02d}-{civil.get('day',0):02d}" if civil else None
        if date:
            val = rhr.get("beatsPerMinute")
            if val: result[date] = round(float(val),1)
    return result

def process_hrv(points):
    result = {}
    for p in points:
        hrv = p.get("dailyHeartRateVariability", {})
        civil = hrv.get("civilTime", {}).get("date", {})
        date = f"{civil.get('year')}-{civil.get('month',0):02d}-{civil.get('day',0):02d}" if civil else None
        if date:
            rmssd = hrv.get("rmssd")
            if rmssd: result[date] = round(float(rmssd),1)
    return result

def main():
    print("=" * 50)
    print(f"NephroWear Auto-Update v3 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")
    sleep_filter = (f'sleep.interval.start_time >= "{start}T00:00:00Z" '
                    f'AND sleep.interval.start_time <= "{end}T23:59:59Z"')
    try:
        token      = get_token()
        sleep_pts  = fetch_list(token, "sleep", sleep_filter)
        rhr_pts    = fetch_daily_rollup(token, "daily-resting-heart-rate", start, end)
        hrv_pts    = fetch_daily_rollup(token, "daily-heart-rate-variability", start, end)
        sleep_data = process_sleep(sleep_pts)
        rhr_data   = process_rhr(rhr_pts)
        hrv_data   = process_hrv(hrv_pts)
        output = {"last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                  "participant": "P3", "study_start": "2026-07-06",
                  "sleep": sleep_data, "resting_hr": rhr_data, "hrv": hrv_data}
        with open("p3_data.json", "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n✅ SUCCESS — Sleep:{len(sleep_data)} RHR:{len(rhr_data)} HRV:{len(hrv_data)}")
        if sleep_data: print(f"   Latest: {list(sleep_data.keys())[-1]}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback; traceback.print_exc()
        with open("p3_data.json", "w") as f:
            json.dump({"last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "error": str(e), "sleep": {}, "resting_hr": {}, "hrv": {}}, f)

if __name__ == "__main__":
    main()
