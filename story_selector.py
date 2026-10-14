"""
AIKidVerse1 Story Planner v3.1
Free, template-driven Telugu Shorts script planner.

Inputs:
  SUPABASE_URL
  SUPABASE_SECRET_KEY
  YOUTUBE_TOKEN_JSON

Outputs:
  daily_story.json

Important:
- Uses YouTube Data API public video statistics as trend/performance signals.
- Does not claim public search results are official YouTube trending rankings.
- Generates validated 45-second scripts from original structured templates.
- No paid LLM/API is used.
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "daily_story.json"

REGION_CODE = "IN"
MAX_OWN_VIDEOS = 40
MAX_HISTORY_ROWS = 100
SEARCH_QUERIES_PER_RUN = 4
SEARCH_RESULTS_PER_QUERY = 5
TARGET_DURATION = 45

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("aikidverse1")


# The dialogue and story beats are authored templates, not copied from
# external videos. The trend topic affects category selection only.
STORY_FORMATS = {
    "Telugu Baby and Family Comedy": {
        "keywords": ["baby", "amma", "nanna", "family", "mother", "father", "sleep", "homework", "chocolate", "బాబు", "అమ్మ"],
        "characters": [
            {"name": "Chinnu", "description": "A mischievous 4-year-old Telugu child, round expressive face, yellow T-shirt, blue shorts, consistent appearance in every scene."},
            {"name": "Amma", "description": "A warm Telugu mother in a simple green cotton saree, expressive eyes, patient but playfully strict."},
        ],
        "setting": "One bright, tidy family living room. Keep the same furniture, lighting, clothing, and character designs throughout.",
        "scenes": [
            ("Hook", "Close-up: Chinnu hides a small squeaky toy behind their back. Chinnu accidentally squeezes it; it gives a tiny squeak. Amma notices.", "చిన్నూ, నీ వెనకాల ఏముంది?", "Chinnu freezes, hides the same squeaky toy behind their back, and tries to look innocent."),
            ("Setup", "Medium two-shot: Chinnu points toward the kitchen to distract Amma while keeping the toy hidden.", "అమ్మా, వంటగదిలో ఏదో శబ్దం వచ్చింది!", "Amma turns toward the kitchen. Chinnu relaxes, but accidentally squeezes the toy again."),
            ("Escalation", "Amma turns back toward Chinnu as the hidden toy squeaks loudly. Keep the toy hidden until the reaction.", "వంటగదిలో కాదు… శబ్దం నీ వెనకాల నుంచే వస్తోంది!", "Amma points gently at Chinnu's back. Chinnu looks down at the toy, caught red-handed."),
            ("Payoff", "Chinnu slowly brings the squeaky toy out and it squeaks one final time. Amma tries to stay serious but laughs.", "అమ్మా… ఈ బొమ్మే నా రహస్యాన్ని చెప్పేసింది!", "Chinnu hugs the toy sheepishly; Amma smiles and taps Chinnu's nose. End on their shared laugh."),
        ],
    },
    "School Comedy": {
        "keywords": ["school", "teacher", "student", "class", "homework", "exam", "పాఠశాల", "టీచర్"],
        "characters": [
            {"name": "Balu", "description": "A playful Telugu schoolboy wearing a neat blue school uniform and backpack."},
            {"name": "Teacher", "description": "A friendly teacher in a simple formal outfit, expressive but kind."},
        ],
        "setting": "One sunny classroom with desks, a blackboard, and school bags. Keep classroom layout and costumes consistent.",
        "scenes": [
            ("Hook", "Wide classroom shot. Balu proudly raises his hand before the teacher finishes the question.", "సార్, నాకు సమాధానం తెలుసు!", "Balu sits extra straight, looking overconfident."),
            ("Setup", "Medium shot. The teacher asks a simple question and gestures toward the blackboard.", "సరే బాలు, నిన్న ఇచ్చిన హోంవర్క్ ఎక్కడ?", "Balu's smile slowly disappears."),
            ("Escalation", "Close-up. Balu searches every pocket and opens his backpack upside down; only a lunch box falls out.", "సార్… హోంవర్క్ చదువుకోవడానికి ఇంట్లోనే ఉండిపోయింది!", "Nearby students try not to laugh."),
            ("Payoff", "The teacher points at the lunch box while Balu offers it like a peace treaty.", "అయితే రేపు హోంవర్క్‌తో పాటు నీ సమాధానం కూడా తీసుకురా!", "Balu nods seriously, then checks whether the lunch box is still safe."),
        ],
    },
    "Animal Adventure": {
        "keywords": ["animal", "bear", "cat", "dog", "squirrel", "rabbit", "monkey", "bird", "puppy", "kitten", "కోతి", "కుక్క"],
        "characters": [
            {"name": "Mintu", "description": "A small orange squirrel with a cream belly, huge brown eyes, and a tiny blue scarf."},
            {"name": "Crow", "description": "A friendly black crow with glossy feathers and a curious head tilt."},
        ],
        "setting": "One colorful garden with a large tree, a low wooden bench, and scattered leaves. Preserve character colors and prop positions.",
        "scenes": [
            ("Hook", "Low-angle close-up. Mintu proudly holds an oversized nut almost as big as its head.", "ఇది నా జీవితంలోనే పెద్ద గింజ!", "Mintu struggles to balance the nut."),
            ("Setup", "Tracking shot as Mintu rolls the nut toward a tree hollow.", "దీన్ని నా రహస్య చోట దాచేస్తా!", "The nut rolls a little faster than Mintu expects."),
            ("Escalation", "The nut bumps the bench and rolls in a circle. The crow hops aside just in time.", "అయ్యో! ఆగు… ఆగు!", "Mintu runs after it, paws moving comically fast."),
            ("Payoff", "The nut stops right beside the tree hollow; the crow gently points to it with one wing.", "నేను పట్టుకున్నానా… లేక అదృష్టం పట్టుకుందా?", "Mintu laughs, shares a tiny piece with the crow, and they celebrate."),
        ],
    },
    "Visual Slapstick": {
        "keywords": ["funny", "prank", "balloon", "kite", "crazy", "slapstick", "comedy", "కామెడీ", "నవ్వు"],
        "characters": [
            {"name": "Raju", "description": "A cheerful young Telugu man wearing a bright orange shirt, dark trousers, and simple sandals."},
            {"name": "Balloon", "description": "One oversized purple balloon tied to a short string; maintain its color, size, and string in every shot."},
        ],
        "setting": "One open village courtyard in daylight with a low wall and a single wooden stool.",
        "scenes": [
            ("Hook", "Raju poses proudly with the balloon as if it is a trophy.", "ఈ బెలూన్‌తో నా స్టైల్ చూడండి!", "A gentle breeze pulls the balloon upward."),
            ("Setup", "Raju grabs the string with both hands and leans backward dramatically.", "నిన్ను అంత ఈజీగా వదలను!", "The stool slides slightly as Raju braces himself."),
            ("Escalation", "The balloon drifts around the stool; Raju spins once and ends up facing the wrong direction.", "అయ్యో, బెలూన్ నా చుట్టూ తిరుగుతోందా… నేనా?", "He stops dizzy but remains safely on his feet."),
            ("Payoff", "The balloon gently settles on Raju's head like a silly hat.", "చూశారా? చివరికి నా తలపైనే పార్క్ అయింది!", "Raju poses again, now pretending this was his plan all along."),
        ],
    },
    "Fantasy Comedy": {
        "keywords": ["magic", "magical", "wizard", "fantasy", "dragon", "time", "mystery", "మాయ", "మంత్రం"],
        "characters": [
            {"name": "Tara", "description": "A curious Telugu girl with two braids, a purple dress, and a small glowing toy wand."},
            {"name": "Tiny Robot", "description": "A knee-high silver toy robot with blue lights and a friendly face."},
        ],
        "setting": "One cozy playroom with a toy shelf, a rug, and a window. Magical effects are soft, colorful, and family-friendly.",
        "scenes": [
            ("Hook", "Tara points her toy wand at a teddy bear; a tiny sparkle pops.", "అబ్బా! నా మంత్రం పని చేసింది!", "The robot watches with wide glowing eyes."),
            ("Setup", "Tara points at a toy block and whispers a spell.", "ఇప్పుడు ఈ బ్లాక్ ఎగరాలి!", "The block stays still; the robot tilts its head."),
            ("Escalation", "The wand accidentally activates the robot's tiny fan; paper stars swirl around the room.", "అయ్యో, బ్లాక్ కాదు… గది మొత్తం ఎగురుతోంది!", "Tara and the robot duck playfully as paper stars float."),
            ("Payoff", "The fan stops and one paper star lands perfectly on Tara's head.", "మంత్రం సక్సెస్… అలంకరణ ఫ్రీ!", "Tara bows; the robot gives a happy beep."),
        ],
    },
    "Village Comedy": {
        "keywords": ["village", "farmer", "market", "village comedy", "పల్లె", "రైతు", "గ్రామం"],
        "characters": [
            {"name": "Ramu", "description": "A cheerful Telugu village youth wearing a cream shirt, checked lungi, and sandals."},
            {"name": "Vendor", "description": "A friendly local fruit vendor in a simple shirt, standing behind a wooden cart."},
        ],
        "setting": "One colorful village market lane with a fruit cart and a few baskets. Keep the cart and fruit positions consistent.",
        "scenes": [
            ("Hook", "Ramu examines one huge watermelon with exaggerated seriousness.", "అన్నా, ఈ పుచ్చకాయ ఎంత బరువుంది?", "The vendor proudly pats the watermelon."),
            ("Setup", "The vendor points to a weighing scale. Ramu tries lifting the watermelon with one hand.", "బరువు కాదు బాబూ, ఇది స్పెషల్ పుచ్చకాయ!", "Ramu pretends it is light, but his knees bend."),
            ("Escalation", "Ramu rolls it carefully onto the cart; the cart creaks and moves a few inches.", "అన్నా, పుచ్చకాయ కొనాలా… బండిని కొనాలా?", "The vendor grabs the cart handle to stop it."),
            ("Payoff", "The watermelon settles safely into a basket; Ramu proudly pays with a tiny coin.", "ఇంత పెద్దదానికి ఇంత చిన్న బిల్లు!", "The vendor reveals the coin is only an advance; both laugh."),
        ],
    },
    "Human and Animal Friendship": {
        "keywords": ["friend", "rescue", "boy", "girl", "dog", "cat", "puppy", "kitten", "friendship", "స్నేహం"],
        "characters": [
            {"name": "Anu", "description": "A kind Telugu child in a yellow dress with a small red backpack."},
            {"name": "Puppy", "description": "A tiny cream-colored puppy with floppy ears and a red collar."},
        ],
        "setting": "One quiet park path beside a bench and a small flower bed. Keep the weather and character appearance consistent.",
        "scenes": [
            ("Hook", "Anu hears a tiny whimper and kneels beside the bench.", "ఎవరది? చిన్నగా ఏడుపు వినిపిస్తోంది!", "The puppy peeks out from behind the bench."),
            ("Setup", "Anu places a little bowl of water on the ground and waits patiently.", "భయపడకు బుజ్జీ, నేను నీకు సహాయం చేస్తాను.", "The puppy sniffs the bowl and slowly approaches."),
            ("Escalation", "The puppy's loose leash catches gently on a low branch; Anu carefully frees it.", "అయ్యో, నీ పట్టీ ఇక్కడ చిక్కుకుంది!", "Anu unhooks the leash without pulling the puppy."),
            ("Payoff", "The puppy wags its tail and places one paw in Anu's hand.", "ఇప్పటి నుంచి మనం మంచి ఫ్రెండ్స్!", "They walk together toward a nearby adult for safe help."),
        ],
    },
    "Festival Story": {
        "keywords": ["festival", "diwali", "bonalu", "ganesha", "holi", "sankranti", "dasara", "పండుగ", "బోనాలు"],
        "characters": [
            {"name": "Chinni", "description": "A cheerful Telugu child wearing a festive traditional outfit in pink and gold."},
            {"name": "Grandmother", "description": "A smiling Telugu grandmother in a traditional saree, with gentle expressions."},
        ],
        "setting": "One decorated home entrance with flowers, rangoli, and warm festive lights. Keep decorations stable across scenes.",
        "scenes": [
            ("Hook", "Chinni stands proudly beside a colorful rangoli and holds a flower basket.", "నానమ్మా, నా అలంకరణ ఎలా ఉంది?", "Grandmother admires the design."),
            ("Setup", "Chinni carefully places one final flower, then steps back to admire the rangoli.", "ఇప్పుడు ఇది పర్ఫెక్ట్!", "A tiny breeze moves a loose flower."),
            ("Escalation", "The flower lands on Chinni's head like a crown.", "అయ్యో! పువ్వు నా తల మీదకు వచ్చేసింది!", "Grandmother laughs softly while Chinni looks surprised."),
            ("Payoff", "Grandmother adjusts the flower into a neat little hair decoration.", "ఇప్పుడు నువ్వే పండుగ రాణివి!", "Chinni poses proudly; both smile toward the decorated doorway."),
        ],
    },
    "Mini Moral Story": {
        "keywords": ["moral", "lesson", "kindness", "honesty", "help", "truth", "నిజం", "మంచి పాఠం"],
        "characters": [
            {"name": "Kiran", "description": "A thoughtful Telugu child in a green T-shirt and shorts, with clear expressive eyes."},
            {"name": "Friend", "description": "Kiran's friend in a blue outfit, friendly and patient."},
        ],
        "setting": "One sunny neighborhood walkway with a small flower pot near a gate.",
        "scenes": [
            ("Hook", "Kiran accidentally bumps a small empty flower pot; it tips over harmlessly.", "అయ్యో! ఇది నా వల్లే పడిపోయింది.", "Kiran looks around and hesitates."),
            ("Setup", "Kiran notices the friend approaching and considers walking away.", "ఎవరూ చూడలేదు కదా…?", "Kiran pauses and looks back at the pot."),
            ("Escalation", "Kiran returns, sets the pot upright, and checks that it is not broken.", "తప్పు జరిగితే దాన్ని సరిచేయాలి.", "The friend arrives and helps move the pot to a safe spot."),
            ("Payoff", "The friend gives Kiran a grateful smile.", "నిజం చెప్పడం, సహాయం చేయడం రెండూ మంచివే!", "They water the plant together and walk away happily."),
        ],
    },
    "Human vs Technology": {
        "keywords": ["robot", "AI", "technology", "gadget", "smart", "phone", "టెక్నాలజీ", "రోబో"],
        "characters": [
            {"name": "Lok", "description": "A curious young Telugu creator wearing a teal hoodie and dark jeans."},
            {"name": "Mini Robot", "description": "A small white home robot with a blue digital face and rounded arms."},
        ],
        "setting": "One tidy modern living room with a small side table and a charging dock.",
        "scenes": [
            ("Hook", "Lok stands beside the robot and folds his arms confidently.", "ఈ రోజు ఈ రోబోని నేను గెలుస్తా!", "The robot's blue face displays a playful smile."),
            ("Setup", "Lok asks the robot to bring a book from the side table.", "రోబో, నాకు పుస్తకం తీసుకురా.", "The robot turns carefully toward the table."),
            ("Escalation", "The robot brings the book perfectly, then gently offers Lok a bookmark too.", "అయ్యో, నేను చెప్పింది ఒక్కటే కదా!", "Lok looks at the extra bookmark in surprise."),
            ("Payoff", "The robot points at the messy table; Lok notices his own unfinished chores.", "సరే బాస్, ముందు గది సర్దేస్తా!", "Lok starts tidying while the robot gives a cheerful beep."),
        ],
    },
}


TREND_QUERIES = [
    ("Telugu comedy shorts", "Telugu Baby and Family Comedy"),
    ("funny 3D animation shorts", "Visual Slapstick"),
    ("kids funny animal cartoon", "Animal Adventure"),
    ("Indian family comedy shorts", "Telugu Baby and Family Comedy"),
    ("school comedy shorts India", "School Comedy"),
    ("AI animation funny shorts", "Human vs Technology"),
    ("Telugu animated stories", "Mini Moral Story"),
    ("Telugu festival shorts", "Festival Story"),
]


def now_utc():
    return datetime.now(timezone.utc)


def safe_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def tokenize(value):
    words = re.findall(r"[a-z0-9]+|[\u0C00-\u0C7F]+", clean_text(value).lower())
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "when",
        "what", "your", "you", "are", "was", "has", "have", "into",
        "his", "her", "its", "they", "their", "a", "an", "of", "to",
        "in", "on", "is", "it", "shorts", "short", "video", "videos",
        "official", "viral", "new",
    }
    return {word for word in words if word not in stop and len(word) > 1}


def similarity(a, b):
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def story_key(title, concept):
    return hashlib.sha256(
        (clean_text(title).lower() + "|" + clean_text(concept).lower()).encode("utf-8")
    ).hexdigest()


def youtube_client():
    raw = os.getenv("YOUTUBE_TOKEN_JSON")
    if not raw:
        raise RuntimeError("Missing GitHub secret YOUTUBE_TOKEN_JSON.")
    try:
        token = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("YOUTUBE_TOKEN_JSON must contain valid token.json JSON.") from exc

    credentials = Credentials.from_authorized_user_info(token)
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SECRET_KEY.")
    return create_client(url, key)


def published_age_days(published_at):
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return max(1, (now_utc() - published).days)
    except (ValueError, AttributeError):
        return 7


def fetch_own_videos(yt):
    videos = []
    try:
        channels = yt.channels().list(part="contentDetails", mine=True, maxResults=1).execute()
        items = channels.get("items", [])
        if not items:
            log.warning("Authenticated account returned no YouTube channel.")
            return videos

        playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist = yt.playlistItems().list(
            part="contentDetails", playlistId=playlist_id, maxResults=MAX_OWN_VIDEOS
        ).execute()
        ids = [
            x.get("contentDetails", {}).get("videoId")
            for x in playlist.get("items", [])
        ]
        ids = [x for x in ids if x]
        if not ids:
            return videos

        response = yt.videos().list(
            part="snippet,statistics", id=",".join(ids), maxResults=50
        ).execute()

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            age = published_age_days(snippet.get("publishedAt"))
            views = safe_int(stats.get("viewCount"))
            videos.append({
                "video_id": item.get("id"),
                "title": clean_text(snippet.get("title")),
                "views": views,
                "likes": safe_int(stats.get("likeCount")),
                "age_days": age,
                "views_per_day": views / age,
            })
    except HttpError as exc:
        log.warning("Channel performance request failed: %s", exc)

    return sorted(videos, key=lambda x: x["views_per_day"], reverse=True)


def infer_format(text):
    lowered = clean_text(text).lower()
    best_name, best_score = None, 0
    for name, spec in STORY_FORMATS.items():
        score = sum(1 for keyword in spec["keywords"] if keyword.lower() in lowered)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def channel_format_scores(videos):
    scores = Counter()
    for video in videos:
        fmt = infer_format(video["title"])
        if fmt:
            # Diminishing returns prevent one huge video dominating every decision.
            scores[fmt] += min(3.0, video["views_per_day"] / 100.0)
    return scores


def fetch_external_trends(yt):
    today_index = now_utc().timetuple().tm_yday % len(TREND_QUERIES)
    rotated = TREND_QUERIES[today_index:] + TREND_QUERIES[:today_index]
    selected_queries = rotated[:SEARCH_QUERIES_PER_RUN]
    trend_videos = []
    query_format_scores = Counter()

    for query, expected_format in selected_queries:
        try:
            response = yt.search().list(
                part="snippet",
                q=query,
                type="video",
                order="date",
                publishedAfter=(now_utc() - timedelta(days=14)).isoformat().replace("+00:00", "Z"),
                regionCode=REGION_CODE,
                safeSearch="strict",
                maxResults=SEARCH_RESULTS_PER_QUERY,
            ).execute()
            query_format_scores[expected_format] += 0.5

            for item in response.get("items", []):
                vid = item.get("id", {}).get("videoId")
                snippet = item.get("snippet", {})
                if not vid:
                    continue
                trend_videos.append({
                    "video_id": vid,
                    "title": clean_text(snippet.get("title")),
                    "channel_title": clean_text(snippet.get("channelTitle")),
                    "published_at": snippet.get("publishedAt"),
                    "query_format": expected_format,
                })
        except HttpError as exc:
            log.warning("Trend search failed for %s: %s", query, exc)

    unique = {v["video_id"]: v for v in trend_videos}
    trend_videos = list(unique.values())

    # videos.list accepts up to 50 IDs per call.
    if trend_videos:
        try:
            response = yt.videos().list(
                part="statistics,snippet",
                id=",".join(v["video_id"] for v in trend_videos[:50]),
                maxResults=50,
            ).execute()
            stats = {x["id"]: x for x in response.get("items", [])}

            for video in trend_videos:
                item = stats.get(video["video_id"], {})
                counts = item.get("statistics", {})
                video["views"] = safe_int(counts.get("viewCount"))
                video["likes"] = safe_int(counts.get("likeCount"))
                video["views_per_day"] = video["views"] / published_age_days(video.get("published_at"))
                inferred = infer_format(video["title"])
                video["inferred_format"] = inferred or video["query_format"]
                query_format_scores[video["inferred_format"]] += min(
                    3.0, video["views_per_day"] / 100.0
                )
        except HttpError as exc:
            log.warning("External trend statistics request failed: %s", exc)

    trend_videos.sort(key=lambda x: x.get("views_per_day", 0), reverse=True)
    return trend_videos[:20], query_format_scores


def fetch_history(sb):
    response = (
        sb.table("story_history")
        .select("story_key,title,concept,hook,ending,status,created_at")
        .order("created_at", desc=True)
        .limit(MAX_HISTORY_ROWS)
        .execute()
    )
    return response.data or []


def make_script(format_name):
    spec = STORY_FORMATS[format_name]
    scene_beats = spec["scenes"]
    scene_durations = [5, 12, 13, 15]
    scenes = []

    for idx, (beat, visual, dialogue, action) in enumerate(scene_beats):
        scenes.append({
            "scene_number": idx + 1,
            "scene_name": beat,
            "duration_seconds": scene_durations[idx],
            "timecode": None,  # Filled by validator.
            "location": spec["setting"],
            "visual_direction": visual,
            "character_action_and_expression": action,
            "camera_direction": [
                "Vertical 9:16 framing; start with a readable close-up and establish the location.",
                "Use a medium shot to show both the character and the cause of the problem.",
                "Use a close-up/reaction shot; keep screen direction and prop positions consistent.",
                "Hold the final reaction long enough for the punchline to land; end cleanly.",
            ][idx],
            "dialogue_telugu": dialogue,
            "dialogue_speaker": [
                ["Amma", "Chinnu"], ["Chinnu"], ["Amma", "Chinnu"], ["Amma", "Chinnu"]
            ][idx] if format_name == "Telugu Baby and Family Comedy" else [],
            "voice_direction": [
                "Quick, curious delivery; make the hook immediately understandable.",
                "Natural conversational Telugu; do not rush the words.",
                "Increase comic tension, then leave a short reaction pause.",
                "Deliver the punchline clearly; finish with a warm, expressive reaction.",
            ][idx],
            "audio": {
                "dialogue": "Record clean Telugu dialogue; dialogue must remain intelligible over music.",
                "music": ["Light playful opening", "Bouncy comic bed", "Brief tension build", "Short upbeat payoff"][idx],
                "sound_effects": [
                    "Soft opening pop or room tone",
                    "Subtle movement sound matched to the action",
                    "One synchronized comic accent; avoid excessive effects",
                    "Gentle comic sting, then a clean audio tail",
                ][idx],
            },
            "transition": "Use a simple continuous cut; do not change location or character design.",
        })

    # Set speaker labels for every format, using character names in the authored line.
    dialogue_speakers = {
        "Telugu Baby and Family Comedy": ["Amma", "Chinnu", "Amma", "Chinnu"],
        "School Comedy": ["Balu", "Teacher", "Balu", "Teacher"],
        "Animal Adventure": ["Mintu", "Mintu", "Mintu", "Mintu"],
        "Visual Slapstick": ["Raju", "Raju", "Raju", "Raju"],
        "Fantasy Comedy": ["Tara", "Tara", "Tara", "Tara"],
        "Village Comedy": ["Ramu", "Ramu", "Ramu", "Ramu"],
        "Human and Animal Friendship": ["Anu", "Anu", "Anu", "Anu"],
        "Festival Story": ["Chinni", "Chinni", "Chinni", "Grandmother"],
        "Mini Moral Story": ["Kiran", "Kiran", "Kiran", "Friend"],
        "Human vs Technology": ["Lok", "Lok", "Lok", "Lok"],
    }
    for scene, speaker in zip(scenes, dialogue_speakers[format_name]):
        scene["dialogue_speaker"] = speaker

    return {
        "language": "Natural spoken Telugu",
        "production_instruction_language": "English",
        "target_duration_seconds": TARGET_DURATION,
        "aspect_ratio": "9:16",
        "visual_style": "Original high-quality cinematic 3D family animation",
        "character_bible": spec["characters"],
        "location_and_continuity": spec["setting"],
        "global_continuity_rules": [
            "Use exactly the character designs listed in character_bible.",
            "Keep clothing, colors, props, lighting, and location consistent across all scenes.",
            "Do not introduce a new speaking character without updating the character bible.",
            "Every action must follow logically from the previous scene.",
            "Keep all physical comedy harmless and family-friendly.",
            "Do not add on-screen text, captions, logos, or watermarks unless explicitly requested.",
            "Generate original visuals and dialogue; do not reproduce source videos.",
        ],
        "story_arc": {
            "setup": "Introduce one clear problem, secret, or goal in the hook/setup scenes.",
            "escalation": "Make the same problem harder or more obvious; do not introduce an unrelated problem.",
            "payoff": "Resolve the original setup with a clear visual or verbal punchline.",
        },
        "scenes": scenes,
        "ending_instruction": "The final scene must resolve the setup and end with a clear visual or verbal punchline.",
    }


def validate_script(script):
    errors = []
    scenes = script.get("scenes", [])

    if script.get("target_duration_seconds") != TARGET_DURATION:
        errors.append("Target duration must be exactly 45 seconds.")
    if len(scenes) < 4:
        errors.append("At least four scenes are required.")
    if not script.get("character_bible"):
        errors.append("Character bible is missing.")

    char_names = [
        clean_text(c.get("name"))
        for c in script.get("character_bible", [])
        if clean_text(c.get("name"))
    ]
    total = 0
    previous_end = 0
    expected_beats = ["Hook", "Setup", "Escalation", "Payoff"]
    if len(scenes) != 4:
        errors.append("Exactly four story beats are required: Hook, Setup, Escalation, Payoff.")
    for i, scene in enumerate(scenes, start=1):
        required = [
            "scene_number", "scene_name", "duration_seconds", "visual_direction",
            "character_action_and_expression", "camera_direction", "dialogue_telugu",
            "dialogue_speaker", "voice_direction", "audio", "transition",
        ]
        for field in required:
            if not scene.get(field):
                errors.append(f"Scene {i}: missing {field}.")

        duration = safe_int(scene.get("duration_seconds"))
        if duration <= 0:
            errors.append(f"Scene {i}: duration must be positive.")
        total += duration
        scene["timecode"] = f"{previous_end:02d}-{previous_end + duration:02d}s"
        previous_end += duration

        dialogue = clean_text(scene.get("dialogue_telugu"))
        if len(dialogue) < 8:
            errors.append(f"Scene {i}: Telugu dialogue is missing or too short to carry a story beat.")
        if not re.search(r"[\u0C00-\u0C7F]", dialogue):
            errors.append(f"Scene {i}: dialogue must contain Telugu script.")
        if i > len(expected_beats) or scene.get("scene_name") != expected_beats[i - 1]:
            errors.append(f"Scene {i}: story beat order must be Hook, Setup, Escalation, Payoff.")

        speaker = clean_text(scene.get("dialogue_speaker"))
        if not speaker:
            errors.append(f"Scene {i}: dialogue speaker is missing.")
        elif speaker not in char_names:
            errors.append(f"Scene {i}: speaker '{speaker}' is not listed in the character bible.")

        # A 45-second Short needs concise lines. This is a warning threshold, not a grammar check.
        word_count = len(dialogue.split())
        if duration > 0 and word_count / duration > 3.5:
            errors.append(f"Scene {i}: dialogue is too dense for its {duration}-second scene.")

    if total != TARGET_DURATION:
        errors.append(
            f"Scene durations total {total} seconds, expected {TARGET_DURATION}."
        )

    if len(char_names) != len(set(char_names)):
        errors.append("Character bible contains duplicate names.")

    return {"valid": len(errors) == 0, "errors": errors, "total_duration_seconds": total}


def build_candidates(own_videos, external_scores, history):
    own_scores = channel_format_scores(own_videos)
    max_own = max(own_scores.values(), default=1.0)
    max_external = max(external_scores.values(), default=1.0)

    # Count formats recently used, based on title/concept text.
    recent_usage = Counter()
    for old in history[:20]:
        text = " ".join([
            clean_text(old.get("title")),
            clean_text(old.get("concept")),
        ])
        fmt = infer_format(text)
        if fmt:
            recent_usage[fmt] += 1

    candidates = []
    for format_name, spec in STORY_FORMATS.items():
        channel_signal = own_scores.get(format_name, 0) / max_own if own_scores else 0.35
        trend_signal = external_scores.get(format_name, 0) / max_external if external_scores else 0.25
        novelty_signal = 1.0 / (1.0 + recent_usage[format_name])
        variety_signal = 1.0 / (1.0 + recent_usage[format_name])

        score = (
            0.40 * channel_signal
            + 0.30 * trend_signal
            + 0.20 * novelty_signal
            + 0.10 * variety_signal
        )

        script = make_script(format_name)
        validation = validate_script(script)
        if not validation["valid"]:
            log.warning("Rejecting %s: %s", format_name, validation["errors"])
            continue

        concept = (
            f"Original {format_name} short. "
            f"Core setup: {spec['scenes'][0][1]} "
            f"Resolution: {spec['scenes'][3][1]}"
        )
        title = {
            "Telugu Baby and Family Comedy": "The Little Secret — Telugu Family Comedy",
            "School Comedy": "Homework Has a Mind of Its Own — School Comedy",
            "Animal Adventure": "Mintu and the Giant Nut — Animal Adventure",
            "Visual Slapstick": "The Balloon Boss — Visual Comedy",
            "Fantasy Comedy": "The Wand That Did the Wrong Thing — Fantasy Comedy",
            "Village Comedy": "The Giant Watermelon Problem — Village Comedy",
            "Human and Animal Friendship": "A Tiny Friend in Need — Friendship Story",
            "Festival Story": "The Flower Crown Surprise — Festival Story",
            "Mini Moral Story": "The Honest Little Fix — Moral Story",
            "Human vs Technology": "The Robot's Extra Task — Tech Comedy",
        }[format_name]

        story_text = title + " " + concept
        duplicate = False
        for old in history:
            old_text = " ".join([
                clean_text(old.get("title")),
                clean_text(old.get("concept")),
            ])
            if (
                old.get("story_key") == story_key(title, concept)
                or similarity(story_text, old_text) >= 0.72
            ):
                duplicate = True
                break
        if duplicate:
            continue

        candidates.append({
            "story_key": story_key(title, concept),
            "title": title,
            "concept": concept,
            "hook": script["scenes"][0]["dialogue_telugu"],
            "ending": script["scenes"][-1]["dialogue_telugu"],
            "format": format_name,
            "audience": "Telugu-speaking family and Shorts audiences",
            "trend_topic": format_name,
            "score": round(score, 4),
            "score_breakdown": {
                "channel_performance": round(channel_signal, 3),
                "external_trends": round(trend_signal, 3),
                "novelty": round(novelty_signal, 3),
                "format_variety": round(variety_signal, 3),
            },
            "script": script,
            "validation": validation,
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def save_story(sb, story):
    # Match the existing story_history schema.
    record = {
        "story_key": story["story_key"],
        "title": story["title"],
        "concept": story["concept"],
        "hook": story["hook"],
        "ending": story["ending"],
        "script": story["script"],
        "status": "planned",
    }
    response = sb.table("story_history").insert(record).execute()
    if not response.data:
        raise RuntimeError("Supabase did not confirm the story insert.")
    return response.data[0]


def main():
    started = now_utc()
    yt = youtube_client()
    sb = supabase_client()

    own_videos = fetch_own_videos(yt)
    external_videos, external_scores = fetch_external_trends(yt)
    history = fetch_history(sb)

    candidates = build_candidates(own_videos, external_scores, history)
    if not candidates:
        raise RuntimeError(
            "No valid non-duplicate candidates were found. "
            "Check story history or run again after reviewing duplicates."
        )

    selected = candidates[0]
    selected["selection"] = {
        "planner_version": "3.1-quality-gate",
        "selected_at_utc": now_utc().isoformat(),
        "selection_score": selected["score"],
        "score_breakdown": selected["score_breakdown"],
        "channel_video_sample": [
            {
                "title": v["title"],
                "views": v["views"],
                "views_per_day": round(v["views_per_day"], 2),
            }
            for v in own_videos[:10]
        ],
        "external_trend_sample": [
            {
                "title": v["title"],
                "views": v.get("views", 0),
                "views_per_day": round(v.get("views_per_day", 0), 2),
                "url": "https://www.youtube.com/watch?v=" + v["video_id"],
            }
            for v in external_videos[:10]
        ],
        "history_rows_checked": len(history),
        "candidate_count": len(candidates),
        "run_duration_seconds": round((now_utc() - started).total_seconds(), 2),
        "limitations": [
            "Trend results are public YouTube search samples, not an official trending ranking.",
            "Public views per day are only a rough trend signal.",
            "Scripts are generated from authored templates, not a generative AI model.",
            "Quality checks validate structure and Telugu-script presence, not perfect grammar.",
            "Video generation, voice synthesis, editing, and publishing are separate workflow stages.",
        ],
    }

    validation = validate_script(selected["script"])
    selected["validation"] = validation
    if not validation["valid"]:
        raise RuntimeError("Final script validation failed: " + "; ".join(validation["errors"]))

    saved = save_story(sb, selected)
    selected["database"] = {
        "table": "story_history",
        "status": "saved",
        "record_id": saved.get("id"),
    }

    OUTPUT_FILE.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.info("Selected story: %s", selected["title"])
    log.info("Format: %s | score: %.3f", selected["format"], selected["score"])
    log.info("Script validation: PASS | duration: %ss", validation["total_duration_seconds"])
    log.info("Saved to Supabase and %s", OUTPUT_FILE)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Story planner failed.")
        raise
