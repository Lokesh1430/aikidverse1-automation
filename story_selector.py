
import hashlib
import json
import os
import random
from datetime import date, datetime, timezone

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Starter concepts. We'll expand this with trend research and AI writing next.
STORY_IDEAS = [
    {
        "title": "The Baby Bear and the Runaway Honey Pot",
        "concept": "A curious baby bear follows a rolling honey pot and accidentally leads a parade of forest animals.",
        "hook": "The honey pot started rolling by itself!",
        "ending": "The bear discovers a tiny bee pushing the pot, and they share the honey.",
        "theme": "animal_comedy",
    },
    {
        "title": "The Kitten and the Balloon Taxi",
        "concept": "A kitten grabs a balloon string and floats gently above a colorful garden before landing safely in a hay pile.",
        "hook": "One tiny balloon lifted the whole kitten!",
        "ending": "The kitten lands safely and gives the balloon to a friend.",
        "theme": "object_adventure",
    },
    {
        "title": "The Squirrel's Giant Acorn",
        "concept": "A little squirrel finds an enormous acorn and tries increasingly silly ways to carry it home.",
        "hook": "This acorn was bigger than the squirrel!",
        "ending": "The squirrel rolls it home and invites everyone to a forest feast.",
        "theme": "animal_comedy",
    },
    {
        "title": "The Frog and the Sneaky Caterpillar",
        "concept": "A frog guards a juicy leaf while a caterpillar keeps finding funny ways to sneak past.",
        "hook": "The frog blinked—and the leaf disappeared!",
        "ending": "The frog discovers the caterpillar only wanted to share the leaf.",
        "theme": "funny_mystery",
    },
    {
        "title": "Bob and the Mischievous Kite",
        "concept": "A cheerful boy flies a kite that catches his hat and gently pulls him across a soft grassy hill.",
        "hook": "Bob's kite stole his hat!",
        "ending": "The kite returns the hat, but now it is wearing the hat itself.",
        "theme": "slapstick_comedy",
    },
]


def fetch_story_history():
    url = f"{SUPABASE_URL}/rest/v1/story_history"
    response = requests.get(
        url,
        headers=HEADERS,
        params={
            "select": "story_key,title,concept,hook,ending,status",
            "limit": "1000",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main():
    history = fetch_story_history()
    existing_titles = {
        item.get("title", "").strip().casefold()
        for item in history
    }
    existing_concepts = {
        item.get("concept", "").strip().casefold()
        for item in history
    }

    candidates = [
        idea for idea in STORY_IDEAS
        if idea["title"].strip().casefold() not in existing_titles
        and idea["concept"].strip().casefold() not in existing_concepts
    ]

    if not candidates:
        raise RuntimeError(
            "All starter ideas have already been used. "
            "Add fresh concepts before running again."
        )

    # Temporary selection strategy; real trend/performance scoring comes next.
    chosen = random.choice(candidates)
    story_key = hashlib.sha256(
        json.dumps(chosen, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    story = {
        **chosen,
        "story_key": story_key,
        "script": {
            "scenes": [
                {"scene": 1, "purpose": "Show the character and funny problem."},
                {"scene": 2, "purpose": "Escalate the action with clear visual comedy."},
                {"scene": 3, "purpose": "Deliver the surprise ending safely."},
            ],
            "visual_style": (
                "Original high-quality cinematic 3D family animation, "
                "expressive characters, smooth natural motion, vertical 9:16."
            ),
            "audio": (
                "Playful original music and suitable sound effects; "
                "clear dialogue only if generated and checked separately."
            ),
        },
        "status": "planned",
    }

    # Save using the table's unique story_key.
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/story_history",
        headers={
            **HEADERS,
            "Prefer": "resolution=ignore-duplicates,return=representation",
        },
        json={
            "story_key": story["story_key"],
            "title": story["title"],
            "concept": story["concept"],
            "hook": story["hook"],
            "ending": story["ending"],
            "script": story["script"],
            "status": "planned",
        },
        timeout=30,
    )
    response.raise_for_status()

    with open("daily_story.json", "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    print("Story planner completed.")
    print("Date:", date.today().isoformat())
    print("Selected:", story["title"])
    print("Saved story history record:", bool(response.json()))


if __name__ == "__main__":
    main()
