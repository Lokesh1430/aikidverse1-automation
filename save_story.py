
import json
import os
import hashlib
import urllib.error
import urllib.parse
import urllib.request

base_url = os.environ["SUPABASE_URL"].rstrip("/")
api_key = os.environ["SUPABASE_SECRET_KEY"]

# Temporary test story. We will replace this with AI-generated stories later.
story = {
    "title": "The Runaway Watermelon",
    "concept": "A little cartoon hippo chases a rolling watermelon and gets a funny surprise.",
    "hook": "The watermelon suddenly rolls away!",
    "ending": "The watermelon bounces back into the hippo's mouth."
}

canonical = json.dumps(story, sort_keys=True, ensure_ascii=False)
story_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

payload = {
    "story_key": story_key,
    **story,
    "status": "planned"
}

url = f"{base_url}/rest/v1/story_history"

request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=representation"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=20) as response:
        result = response.read().decode("utf-8")
        if result.strip():
            print("Story saved:", result)
        else:
            print("Story already exists or was not inserted.")
except urllib.error.HTTPError as error:
    print(f"Supabase returned HTTP {error.code}")
    print(error.read().decode("utf-8", errors="replace")[:500])
    raise

print("Story key:", story_key)
