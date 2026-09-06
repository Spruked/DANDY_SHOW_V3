"""
smoke_test.py — Dandy backend smoke test
Hits all non-destructive GET endpoints and key structural POST endpoints.
Expects server running at BASE_URL.
"""
import sys
import os
import httpx

BASE = os.getenv("DANDY_BASE_URL", "http://127.0.0.1:8110").rstrip("/")
EPISODE_ID = "sovereign_software_special_001"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results = []

def check(label, method, path, body=None, expected=(200,), skip=False):
    url = f"{BASE}{path}"
    if skip:
        print(f"  {SKIP}  {method} {path}  (skipped)")
        results.append(("SKIP", label))
        return
    try:
        if method == "GET":
            r = httpx.get(url, timeout=8)
        elif method == "POST":
            r = httpx.post(url, json=body or {}, timeout=8)
        elif method == "PUT":
            r = httpx.put(url, json=body or {}, timeout=8)
        else:
            r = httpx.request(method, url, json=body or {}, timeout=8)

        ok = r.status_code in expected
        tag = PASS if ok else FAIL
        print(f"  {tag}  {method} {path}  [{r.status_code}]")
        if not ok:
            try:
                print(f"       -> {r.json()}")
            except Exception:
                print(f"       -> {r.text[:200]}")
        results.append(("PASS" if ok else "FAIL", label))
    except Exception as e:
        print(f"  {FAIL}  {method} {path}  [ERROR: {e}]")
        results.append(("FAIL", label))


print("\n=== DANDY SMOKE TEST ===\n")

# --- Root ---
print("[ Root ]")
check("root", "GET", "/")

# --- System ---
print("\n[ System ]")
check("health",         "GET", "/health")
check("config-summary", "GET", "/system/config-summary")
check("voices",         "GET", "/voices")

# --- Library ---
print("\n[ Library ]")
check("library",           "GET", "/library")
check("episodes",          "GET", "/episodes")
check("episode-by-id",     "GET", f"/episodes/{EPISODE_ID}")
check("episode-script",    "GET", f"/episodes/{EPISODE_ID}/script")
check("script-versions",   "GET", f"/episodes/{EPISODE_ID}/script-versions")

# --- Assets ---
print("\n[ Assets ]")
check("episode-assets",    "GET", f"/episodes/{EPISODE_ID}/assets")
check("media-cues",        "GET", f"/episodes/{EPISODE_ID}/media-cues")

# --- Ads ---
print("\n[ Ads ]")
check("ads-catalog",       "GET", "/ads/catalog")
check("ads-presets",       "GET", "/ads/presets")
check("episode-ads",       "GET", f"/episodes/{EPISODE_ID}/ads")
check("ad-settings",       "GET", f"/episodes/{EPISODE_ID}/ad-settings")

# --- Social ---
print("\n[ Social ]")
check("social-presets",    "GET", "/social/presets")
check("episode-social",    "GET", f"/episodes/{EPISODE_ID}/social")

# --- OBS (optional hardware; 200 or graceful error expected) ---
print("\n[ OBS (graceful) ]")
check("obs-status",        "GET", "/obs/status",   expected=(200, 503, 500))
check("obs-scenes",        "GET", "/obs/scenes",   expected=(200, 503, 500))


# --- API-prefix aliases (spot-check) ---
print("\n[ /api prefix aliases ]")
check("api/health",        "GET", "/api/health")
check("api/episodes",      "GET", "/api/episodes")
check("api/ads-catalog",   "GET", "/api/ads/catalog")
check("api/social-presets","GET", "/api/social/presets")

# --- Production POST (422 expected without valid body — means route exists) ---
print("\n[ Production routes (route-existence check) ]")
check("produce-ep route",  "POST", "/episodes/create",          body={}, expected=(200, 422))
check("generate-script",   "POST", "/episodes/generate-script", body={}, expected=(200, 422))

# --- Summary ---
print("\n=== RESULTS ===")
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
skipped = sum(1 for s, _ in results if s == "SKIP")
total = len(results)
print(f"  Total : {total}")
print(f"  Pass  : {passed}")
print(f"  Fail  : {failed}")
print(f"  Skip  : {skipped}")
if failed:
    print("\n  FAILED:")
    for s, label in results:
        if s == "FAIL":
            print(f"    - {label}")
    sys.exit(1)
else:
    print("\n  ALL CHECKS PASSED")
    sys.exit(0)
