"""
NephroWear Study — Health Data Fetcher v8
Fetches data AND injects it directly into index.html
so no fetch() call needed — works with GitHub Pages
"""
import os, json, re, requests
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

def fetch_all(token, endpoint):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE}/{endpoint}"
    points, page_token = [], None
    while True:
        params = {"pageSize": "1000"}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != 200:
            print(f"✗ {endpoint}: {r.status_code} — {r.text[:200]}")
            return []
        data = r.json()
        pts = data.get("dataPoints", [])
        points.extend(pts)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    print(f"✓ {endpoint}: {len(points)} points")
    return points

def process_sleep(points, start_date, end_date):
    daily = {}
    for p in points:
        sleep    = p.get("sleep", {})
        interval = sleep.get("interval", {})
        start_str = interval.get("startTime", "")
        if not start_str: continue
        date = start_str[:10]
        if date < start_date or date > end_date: continue
        light = deep = rem = awake = 0
        for stage in sleep.get("stages", []):
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
        total = light + deep + rem
        if date not in daily:
            daily[date] = {
                "date": date, "score": None,
                "light": round(light,1), "deep": round(deep,1),
                "rem": round(rem,1), "awake": round(awake,1),
                "total_sleep_hrs": round(total/60,2),
                "start_time": start_str[11:16],
                "end_time": interval.get("endTime","")[11:16]
            }
    return dict(sorted(daily.items()))

def process_rhr(points, start_date, end_date):
    result = {}
    for p in points:
        rhr = p.get("dailyRestingHeartRate", {})
        date_obj = rhr.get("date", {})
        if not date_obj: continue
        date = f"{date_obj['year']}-{date_obj['month']:02d}-{date_obj['day']:02d}"
        if start_date <= date <= end_date:
            bpm = rhr.get("beatsPerMinute")
            if bpm: result[date] = round(float(bpm), 1)
    return result

def process_hrv(points, start_date, end_date):
    result = {}
    for p in points:
        hrv = p.get("dailyHeartRateVariability", {})
        date_obj = hrv.get("date", {})
        if not date_obj: continue
        date = f"{date_obj['year']}-{date_obj['month']:02d}-{date_obj['day']:02d}"
        if start_date <= date <= end_date:
            rmssd = hrv.get("averageHeartRateVariabilityMilliseconds")
            if rmssd: result[date] = round(float(rmssd), 1)
    return result

def inject_into_html(data):
    """Update P3 data variables directly in index.html"""
    import re as _re
    try:
        with open("index.html", "r") as f:
            html = f.read()

        rhr_json   = json.dumps(data["resting_hr"])
        sleep_json = json.dumps({d: {"deep":v["deep"],"light":v["light"],"rem":v["rem"],"awake":v["awake"],"total":v["total_sleep_hrs"]} for d,v in data["sleep"].items()})
        hrv_json   = json.dumps(data["hrv"])
        updated    = data["last_updated"]

        new_block = f"""// P3_DATA_START
const P3_RHR   = {rhr_json};
const P3_SLEEP = {sleep_json};
const P3_HRV   = {hrv_json};
const P3_UPDATED = "{updated}";
// P3_DATA_END"""

        if "// P3_DATA_START" in html:
            html = _re.sub(r"// P3_DATA_START.*?// P3_DATA_END", new_block, html, flags=_re.DOTALL)
            with open("index.html", "w") as f:
                f.write(html)
            print(f"✓ P3 data injected — {len(data['resting_hr'])} RHR days, {len(data['sleep'])} sleep days")
        else:
            print("✗ P3_DATA_START marker not found in index.html")
    except Exception as e:
        print(f"✗ Injection failed: {e}")
        import traceback; traceback.print_exc()

def main():
    now        = datetime.now(timezone.utc)
    end_date   = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    print("=" * 55)
    print(f"NephroWear v8 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Fetching {start_date} → {end_date}")
    print("=" * 55)

    try:
        token = get_token()

        sleep_pts = fetch_all(token, "sleep/dataPoints:reconcile")
        rhr_pts   = fetch_all(token, "daily-resting-heart-rate/dataPoints")
        hrv_pts   = fetch_all(token, "daily-heart-rate-variability/dataPoints")

        sleep_data = process_sleep(sleep_pts, start_date, end_date)
        rhr_data   = process_rhr(rhr_pts, start_date, end_date)
        hrv_data   = process_hrv(hrv_pts, start_date, end_date)

        output = {
            "last_updated": now.strftime("%Y-%m-%d %H:%M UTC"),
            "participant": "P3", "study_start": "2026-07-06",
            "sleep": sleep_data, "resting_hr": rhr_data, "hrv": hrv_data
        }

        # Save JSON file
        with open("p3_data.json", "w") as f:
            json.dump(output, f, indent=2)

        # Inject directly into HTML
        inject_into_html(output)

        print(f"\n✅ SUCCESS")
        print(f"   Sleep: {len(sleep_data)} days")
        print(f"   RHR:   {len(rhr_data)} days")
        print(f"   HRV:   {len(hrv_data)} days")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    main()
