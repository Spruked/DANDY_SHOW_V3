import httpx, json

job_id = "job_DANDY_EP_002_2ef9126f"
r = httpx.post(f"http://localhost:8765/episodes/generate-script?job_id={job_id}", timeout=30)
print("STATUS:", r.status_code)
data = r.json()
print("script_status:", data.get("status"))
print("word_count:", data.get("word_count"))
script = data.get("script", [])
print("lines:", len(script))
bad = [l for l in script if "[unknown]" in l.get("text", "")]
print("unknown_lines:", len(bad))
if script:
    print("\n--- First 4 lines ---")
    for line in script[:4]:
        speaker = line.get("speaker", "?")
        text = line.get("text", "")[:120]
        print(f"  {speaker}: {text}")
