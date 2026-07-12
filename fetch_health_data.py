"""
NephroWear Study — Automatic Health Data Fetcher v2
Uses correct Google Health API v4 endpoints
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

def fetch_data(token, data_type, filter_expr):
    """Fetch data points using correct v4 API with filter"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{data_type}/dataPoints:list"
    params = {"filter": filter_expr, "pageSize": "1000"}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        points = r.json().get("dataPoints", [])
        print(f"✓ {data_type}: {len(points)} points")
        return points
    else:
        print(f"✗ {data_type} failed: {r.status_code} — {r.text[:300]}")
        return []

def fetch_daily_rollup(token, data_type, start_date, end_date):
    """Fetch daily rollup (for resting HR, HRV)"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{data_type}/dataPoints:dailyRollUp"
    body = {
        "range": {
            "startDate": {"year": int(start_date[:4]), "month": int(start_date[5:7]), "day": int(start_date[8:10])},
            "endDate":   {"year": int(end_date[:4]),   "month": int(end_date[5:7]),   "day": int(end_date[8:10])}
        }
    }
    r = requests.post(url, headers=headers, json=body)
    if r.status_code == 200:
        points = r.json().get("rollupDataPoints", [])
        print(f"✓ {data_type} daily rollup: {len(points)} days")
        return points
    else:
        print(f"✗ {data_type} rollup failed: {r.status_code} — {r.text[:300]}")
        return []

def process_sleep(points):
    """Process sleep data points into daily summaries"""
    daily = {}
    for p in points:
        sleep = p.get("sleep", {})
        interval = sleep.get("interval", {})
        start_str = interval.get("startTime", "")
        if not start_str:
            continue

        date = start_str[:10]
        stages = sleep.get("stages", [])

        light = deep = rem = awake = 0
        for stage in stages:
            stype = stage.get("type", "")
            s = datetime.fromisoformat(stage["startTime"].replace("Z","+00:00"))
            e = datetime.fromisoformat(stage["endTime"].replace("Z","+00:00"))
            mins = (e - s).total_seconds() / 60
            if stype == "LIGHT":   light  += mins
            elif stype == "DEEP":  deep   += mins
            elif stype == "REM":   rem    += mins
            elif stype == "AWAKE": awake  += mins

        summary = sleep.get("summary", {})
        score = summary.get("sleepScore", {}).get("overallSleepScore", None)
        total = light + deep + rem

        if date not in daily or (score and (daily[date].get("score") or 0) < score):
            daily[date] = {
                "date": date,
                "score": round(score, 1) if score else None,
                "light": round(light, 1), "deep": round(deep, 1),
                "rem": round(rem, 1), "awake": round(awake, 1),
                "total_sleep_hrs": round(total / 60, 2),
                "start_time": start_str[11:16],
                "end_time": interval.get("endTime", "")[11:16]
            }
    return dict(sorted(daily.items()))

def process_rhr(points):
    """Process daily resting heart rate rollup"""
    result = {}
    for p in points:
        rhr = p.get("dailyRestingHeartRate", {})
        civil = rhr.get("civilTime", {}).get("date", {})
        if civil:
            date = f"{civil['year']}-{civil['month']:02d}-{civil['day']:02d}"
            val = rhr.get("beatsPerMinute")
            if val:
                result[date] = round(val, 1)
    return result

def process_hrv(points):
    """Process daily HRV rollup"""
    result = {}
    for p in points:
        hrv = p.get("dailyHeartRateVariability", {})
        civil = hrv.get("civilTime", {}).get("date", {})
        if civil:
            date = f"{civil['year']}-{civil['month']:02d}-{civil['day']:02d}"
            rmssd = hrv.get("rmssd")
            if rmssd:
                result[date] = round(rmssd, 1)
    return result

def main():
    print("=" * 50)
    print(f"NephroWear Auto-Update v2 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)

    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")

    # Date filter for list endpoint
    filter_expr = (
        f'sleep.interval.start_time >= "{start}T00:00:00Z" '
        f'AND sleep.interval.start_time < "{end}T23:59:59Z"'
    )

    try:
        token = get_token()

        # Fetch all data
        sleep_points = fetch_data(token, "sleep", filter_expr)
        rhr_points   = fetch_daily_rollup(token, "daily-resting-heart-rate", start, end)
        hrv_points   = fetch_daily_rollup(token, "daily-heart-rate-variability", start, end)

        # Process
        sleep_data = process_sleep(sleep_points)
        rhr_data   = process_rhr(rhr_points)
        hrv_data   = process_hrv(hrv_points)

        output = {
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "participant": "P3", "study_start": "2026-07-06",
            "sleep": sleep_data,
            "resting_hr": rhr_data,
            "hrv": hrv_data
        }

        with open("p3_data.json", "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ SUCCESS")
        print(f"   Sleep days:  {len(sleep_data)}")
        print(f"   RHR days:    {len(rhr_data)}")
        print(f"   HRV days:    {len(hrv_data)}")
        if sleep_data:
            print(f"   Latest night: {list(sleep_data.keys())[-1]}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback; traceback.print_exc()
        with open("p3_data.json", "w") as f:
            json.dump({"last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "error": str(e), "sleep": {}, "resting_hr": {}, "hrv": {}}, f)

if __name__ == "__main__":
    main()
