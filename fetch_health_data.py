"""
NephroWear Study — Health Data Fetcher v5
Uses correct endpoints: GET without filter, date-filter in Python
Sleep uses :reconcile to auto-deduplicate across devices
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

def fetch_all(token, endpoint, page_size=1000):
    """Fetch all data points from an endpoint, handle pagination"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{endpoint}"
    points, page_token = [], None
    while True:
        params = {"pageSize": str(page_size)}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != 200:
            print(f"✗ {endpoint} failed: {r.status_code} — {r.text[:300]}")
            return []
        data = r.json()
        pts = data.get("dataPoints", [])
        points.extend(pts)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    print(f"✓ {endpoint}: {len(points)} total points")
    return points

def process_sleep(points, start_date, end_date):
    """Process sleep data — reconcile already deduplicates"""
    daily = {}
    for p in points:
        sleep = p.get("sleep", {})
        interval = sleep.get("interval", {})
        start_str = interval.get("startTime", "")
        if not start_str:
            continue

        # Filter by date range
        date = start_str[:10]
        if date < start_date or date > end_date:
            continue

        stages = sleep.get("stages", [])
        light = deep = rem = awake = 0
        for stage in stages:
            stype = stage.get("type", "")
            try:
                s = datetime.fromisoformat(stage["startTime"].replace("Z","+00:00"))
                e = datetime.fromisoformat(stage["endTime"].replace("Z","+00:00"))
                mins = (e - s).total_seconds() / 60
                if stype == "LIGHT":   light  += mins
                elif stype == "DEEP":  deep   += mins
                elif stype == "REM":   rem    += mins
                elif stype == "AWAKE": awake  += mins
            except: continue

        summary = sleep.get("summary", {})
        score = summary.get("sleepScore", {}).get("overallSleepScore", None)
        total = light + deep + rem

        # Keep best-score session per day
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

def process_rhr(points, start_date, end_date):
    """Process daily resting heart rate"""
    result = {}
    for p in points:
        rhr = p.get("dailyRestingHeartRate", {})
        # Try civil time date
        civil = rhr.get("civilTime", {}).get("date", {})
        if civil:
            date = f"{civil.get('year')}-{civil.get('month',1):02d}-{civil.get('day',1):02d}"
        else:
            # Try physical time
            pt = rhr.get("physicalTime", "")
            date = pt[:10] if pt else ""
        if date and start_date <= date <= end_date:
            val = rhr.get("beatsPerMinute")
            if val:
                result[date] = round(float(val), 1)
    return result

def process_hrv(points, start_date, end_date):
    """Process daily HRV"""
    result = {}
    for p in points:
        hrv = p.get("dailyHeartRateVariability", {})
        civil = hrv.get("civilTime", {}).get("date", {})
        if civil:
            date = f"{civil.get('year')}-{civil.get('month',1):02d}-{civil.get('day',1):02d}"
        else:
            pt = hrv.get("physicalTime", "")
            date = pt[:10] if pt else ""
        if date and start_date <= date <= end_date:
            rmssd = hrv.get("rmssd")
            if rmssd:
                result[date] = round(float(rmssd), 1)
    return result

def main():
    now        = datetime.now(timezone.utc)
    end_date   = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    print("=" * 55)
    print(f"NephroWear v5 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Fetching {start_date} → {end_date}")
    print("=" * 55)

    try:
        token = get_token()

        # Sleep — use reconcile to auto-deduplicate across devices
        sleep_pts = fetch_all(token, "sleep/dataPoints:reconcile")
        # RHR and HRV — use base endpoint
        rhr_pts   = fetch_all(token, "daily-resting-heart-rate/dataPoints")
        hrv_pts   = fetch_all(token, "daily-heart-rate-variability/dataPoints")

        # Process — filter by date in Python
        sleep_data = process_sleep(sleep_pts, start_date, end_date)
        rhr_data   = process_rhr(rhr_pts, start_date, end_date)
        hrv_data   = process_hrv(hrv_pts, start_date, end_date)

        output = {
            "last_updated":  now.strftime("%Y-%m-%d %H:%M UTC"),
            "participant":   "P3",
            "study_start":   "2026-07-06",
            "sleep":         sleep_data,
            "resting_hr":    rhr_data,
            "hrv":           hrv_data
        }

        with open("p3_data.json", "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✅ SUCCESS")
        print(f"   Sleep days: {len(sleep_data)}")
        print(f"   RHR days:   {len(rhr_data)}")
        print(f"   HRV days:   {len(hrv_data)}")
        if sleep_data:
            for d, v in sleep_data.items():
                print(f"   {d}: score={v['score']} deep={v['deep']}min total={v['total_sleep_hrs']}h")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback; traceback.print_exc()
        with open("p3_data.json", "w") as f:
            json.dump({"last_updated": now.strftime("%Y-%m-%d %H:%M UTC"),
                       "error": str(e), "sleep": {}, "resting_hr": {}, "hrv": {}}, f)

if __name__ == "__main__":
    main()
