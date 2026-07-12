"""
NephroWear Study — Health Data Fetcher v4
Diagnostic version — tries multiple endpoint formats to find what works
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

def try_get(token, url, params=None):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or {})
    print(f"  GET {url}")
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        pts = data.get("dataPoints", data.get("rollupDataPoints", []))
        print(f"  ✓ Got {len(pts)} points — keys: {list(data.keys())}")
        if pts: print(f"  Sample: {json.dumps(pts[0])[:300]}")
        return pts
    print(f"  ✗ Error: {r.text[:300]}")
    return None

def try_post(token, url, body):
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    print(f"  POST {url}")
    print(f"  Body: {json.dumps(body)}")
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        pts = data.get("dataPoints", data.get("rollupDataPoints", []))
        print(f"  ✓ Got {len(pts)} points — keys: {list(data.keys())}")
        if pts: print(f"  Sample: {json.dumps(pts[0])[:300]}")
        return pts
    print(f"  ✗ Error: {r.text[:400]}")
    return None

def main():
    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")
    sy, sm, sd = int(start[:4]), int(start[5:7]), int(start[8:10])
    ey, em, ed = int(end[:4]),   int(end[5:7]),   int(end[8:10])

    print("=" * 60)
    print(f"NephroWear Diagnostic v4 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    token = get_token()

    # ── SLEEP: try different endpoint formats ──────────────
    print("\n=== SLEEP TESTS ===")

    print("\n[S1] GET .../sleep/dataPoints (no :list)")
    try_get(token, f"{BASE}/sleep/dataPoints",
            {"filter": f'sleep.interval.start_time >= "{start}T00:00:00Z"', "pageSize": "10"})

    print("\n[S2] GET .../sleep/dataPoints:list")
    try_get(token, f"{BASE}/sleep/dataPoints:list",
            {"filter": f'sleep.interval.start_time >= "{start}T00:00:00Z"', "pageSize": "10"})

    print("\n[S3] GET .../sleep/dataPoints:reconcile")
    try_get(token, f"{BASE}/sleep/dataPoints:reconcile",
            {"filter": f'sleep.interval.start_time >= "{start}T00:00:00Z"', "pageSize": "10"})

    # ── RHR: try different request body formats ────────────
    print("\n=== RESTING HR TESTS ===")

    print("\n[R1] POST dailyRollUp — civil date object")
    try_post(token, f"{BASE}/daily-resting-heart-rate/dataPoints:dailyRollUp", {
        "range": {
            "startDate": {"year": sy, "month": sm, "day": sd},
            "endDate":   {"year": ey, "month": em, "day": ed}
        }
    })

    print("\n[R2] POST dailyRollUp — start/end as date strings")
    try_post(token, f"{BASE}/daily-resting-heart-rate/dataPoints:dailyRollUp", {
        "startDate": f"{start}", "endDate": f"{end}"
    })

    print("\n[R3] POST dailyRollUp — civilTimeInterval")
    try_post(token, f"{BASE}/daily-resting-heart-rate/dataPoints:dailyRollUp", {
        "civilTimeInterval": {
            "startDate": {"year": sy, "month": sm, "day": sd},
            "endDate":   {"year": ey, "month": em, "day": ed}
        }
    })

    print("\n[R4] GET daily-resting-heart-rate/dataPoints list")
    try_get(token, f"{BASE}/daily-resting-heart-rate/dataPoints",
            {"filter": f'daily_resting_heart_rate.civil_time.date.year >= {sy}', "pageSize": "10"})

    print("\n[R5] GET daily-resting-heart-rate/dataPoints:list no filter")
    try_get(token, f"{BASE}/daily-resting-heart-rate/dataPoints:list", {"pageSize": "5"})

    # Save empty JSON so workflow doesn't fail
    with open("p3_data.json", "w") as f:
        json.dump({"last_updated": now.strftime("%Y-%m-%d %H:%M UTC"),
                   "participant": "P3", "study_start": "2026-07-06",
                   "diagnostic": True, "sleep": {}, "resting_hr": {}, "hrv": {}}, f, indent=2)
    print("\n✅ Diagnostic complete — check logs above to see which endpoints work!")

if __name__ == "__main__":
    main()
