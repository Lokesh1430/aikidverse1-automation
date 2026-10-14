
"""
AIKidVerse1 — Trend-Based Story Selector
-----------------------------------------
Uses:
- YouTube Data API: recent public video trend signals
- YouTube Data API: recent uploads from your own channel
- Supabase: story history and duplicate avoidance
- Local JSON: daily_story.json

Required environment variables:
  SUPABASE_URL
  SUPABASE_SECRET_KEY
  YOUTUBE_TOKEN_JSON

This script selects a story brief. It does NOT generate the final video.
"""

import os
import re
import json
import hashlib
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase import create_client


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "daily_story.json"

CHANNEL_ID = "UCKZMPIaZW942vD9NO4uBLTQ"
REGION_CODE = "IN"

MAX_HISTORY_ROWS = 100
MAX_OWN_VIDEOS = 40
MAX_EXTERNAL_RESULTS = 8
TREND_SEARCHES_PER_RUN = 4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("aikidverse1")


# ---------------------------------------------------------
# STORY FORMATS
# ---------------------------------------------------------

# These are creative format templates, not fixed story ideas.
# Trend titles are used only as topic signals, never copied
# as the story title or script.

FORMATS = [
    {
        "name": "Telugu Family Comedy",
        "weight": 1.0,
        "description": "A funny family misunderstanding with a surprising ending.",
        "audience": "Telugu-speaking families and young viewers",
    },
    {
        "name": "School Comedy",
        "weight": 1.0,
        "description": "A classroom challenge becomes unexpectedly hilarious.",
        "audience": "Children, students and family audiences",
    },
    {
        "name": "Animal Adventure",
        "weight": 1.0,
        "description": "A clever animal faces a funny problem and finds an unexpected solution.",
        "audience": "Kids and animation fans",
    },
    {
        "name": "Visual Slapstick",
        "weight": 1.0,
        "description": "A simple visual gag escalates into a surprising, harmless comic situation.",
        "audience": "Shorts viewers who enjoy visual comedy",
    },
    {
        "name": "Fantasy Comedy",
        "weight": 1.0,
        "description": "An ordinary object gains a magical ability that causes comic trouble.",
        "audience": "Kids and fantasy animation fans",
    },
    {
        "name": "Village Comedy",
        "weight": 1.0,
        "description": "A village challenge turns into a playful contest with a clever twist.",
        "audience": "Telugu audiences and family viewers",
    },
    {
        "name": "Human and Animal Friendship",
        "weight": 1.0,
        "description": "A child and an animal work together to solve a small problem.",
        "audience": "Family and animal-story viewers",
    },
    {
        "name": "Festival Story",
        "weight": 0.8,
        "description": "A colorful celebration creates a funny, heartwarming surprise.",
        "audience": "Families and festival-content viewers",
    },
    {
        "name": "Mini Moral Story",
        "weight": 0.8,
        "description": "A small mistake leads to a funny discovery and a positive lesson.",
        "audience": "Children and family audiences",
    },
    {
        "name": "Human vs Technology",
        "weight": 0.9,
        "description": "A person tries to outsmart a clever gadget or robot, with a comic twist.",
        "audience": "Young viewers interested in technology and comedy",
    },
]

# A limited set of searches keeps the daily API usage predictable.
# The query list is mixed-language and covers different formats.
TREND_QUERIES = [
    "Telugu comedy shorts",
    "funny 3D animation shorts",
    "kids funny animal cartoon",
    "Indian family comedy shorts",
    "school comedy shorts India",
    "AI animation funny shorts",
    "Telugu animated stories",
    "funny fantasy animation shorts",
]


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def clean_text(value):
    """Normalize whitespace and remove empty values."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalized_words(value):
    """Return a set of meaningful normalized words."""
    value = clean_text(value).lower()
    words = re.findall(r"[a-z0-9]+|[\u0C00-\u0C7F]+", value)

    stop_words = {
        "the", "and", "for", "with", "from", "this", "that",
        "when", "what", "your", "you", "are", "was", "has",
        "have", "into", "his", "her", "its", "their", "they",
        "a", "an", "of", "to", "in", "on", "is", "it",
        "shorts", "short", "video", "videos", "official",
        "telugu", "funny", "new",
    }

    return {word for word in words if word not in stop_words}


def similarity(text_a, text_b):
    """Jaccard similarity between two text strings."""
    a = normalized_words(text_a)
    b = normalized_words(text_b)

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def make_story_key(title, concept):
    """Stable key for duplicate protection."""
    normalized = (
        clean_text(title).lower()
        + "|"
        + clean_text(concept).lower()
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_int(value, default=0):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------

def create_youtube_client():
    token_json = os.getenv("YOUTUBE_TOKEN_JSON")

    if not token_json:
        raise RuntimeError(
            "Missing GitHub Secret: YOUTUBE_TOKEN_JSON"
        )

    try:
        token_data = json.loads(token_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "YOUTUBE_TOKEN_JSON is not valid JSON. "
            "Use the contents of your authorized token.json file."
        ) from exc

    scopes = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]

    credentials = Credentials.from_authorized_user_info(
        token_data,
        scopes=scopes,
    )

    return build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def create_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")

    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SECRET_KEY."
        )

    return create_client(url, key)


# ---------------------------------------------------------
# CHANNEL PERFORMANCE
# ---------------------------------------------------------

def fetch_own_channel_videos(youtube):
    """
    Fetch recent videos from the authenticated channel.
    Public Data API statistics are used as a performance proxy.
    """
    videos = []

    try:
        channel_response = youtube.channels().list(
            part="contentDetails,snippet",
            mine=True,
            maxResults=1,
        ).execute()

        channel_items = channel_response.get("items", [])

        if not channel_items:
            log.warning(
                "The authenticated YouTube account returned no channel."
            )
            return videos

        channel = channel_items[0]
        uploads_playlist = (
            channel.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )

        if not uploads_playlist:
            log.warning("Could not find the channel uploads playlist.")
            return videos

        playlist_response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=min(MAX_OWN_VIDEOS, 50),
        ).execute()

        video_ids = [
            item.get("contentDetails", {}).get("videoId")
            for item in playlist_response.get("items", [])
        ]
        video_ids = [video_id for video_id in video_ids if video_id]

        if not video_ids:
            return videos

        stats_response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
            maxResults=50,
        ).execute()

        for item in stats_response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            published_at = snippet.get("publishedAt")
            age_days = 7

            if published_at:
                try:
                    published = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )
                    age_days = max(
                        1,
                        (utc_now() - published).days,
                    )
                except ValueError:
                    pass

            views = safe_int(stats.get("viewCount"))

            videos.append({
                "video_id": item.get("id"),
                "title": clean_text(snippet.get("title")),
                "description": clean_text(
                    snippet.get("description", "")
                )[:500],
                "views": views,
                "likes": safe_int(stats.get("likeCount")),
                "comments": safe_int(stats.get("commentCount")),
                "published_at": published_at,
                "age_days": age_days,
                "views_per_day": views / age_days,
            })

        videos.sort(
            key=lambda video: video["views_per_day"],
            reverse=True,
        )

        log.info("Loaded %s recent channel videos.", len(videos))

    except HttpError as exc:
        log.warning("Could not fetch channel videos: %s", exc)

    return videos


def analyze_channel_performance(own_videos):
    """
    Summarize top-performing recent videos by views per day.
    This is a directional signal, not a full retention analysis.
    """
    if not own_videos:
        return {
            "status": "unavailable",
            "summary": "No channel performance data was available.",
            "top_formats": [],
            "top_video_titles": [],
        }

    top_videos = own_videos[:10]

    format_keywords = {
        "Telugu Family Comedy": [
            "family", "amma", "nanna", "mother", "father",
            "brother", "sister", "telugu family",
        ],
        "School Comedy": [
            "school", "teacher", "student", "classroom", "exam",
        ],
        "Animal Adventure": [
            "bear", "cat", "dog", "squirrel", "rabbit", "animal",
            "monkey", "bird", "puppy", "kitten",
        ],
        "Visual Slapstick": [
            "balloon", "fall", "funny", "crazy", "kite", "prank",
        ],
        "Fantasy Comedy": [
            "magic", "magical", "dragon", "wizard", "fantasy",
        ],
        "Village Comedy": [
            "village", "farmer", "village comedy",
        ],
        "Human and Animal Friendship": [
            "friend", "rescue", "boy and dog", "girl and cat",
        ],
        "Festival Story": [
            "festival", "diwali", "bonalu", "ganesha", "holi",
            "sankranti", "dasara",
        ],
        "Mini Moral Story": [
            "moral", "lesson", "kindness", "honesty",
        ],
        "Human vs Technology": [
            "robot", "ai", "technology", "gadget",
        ],
    }

    format_scores = Counter()

    for video in top_videos:
        title = video["title"].lower()
        score = max(1.0, video["views_per_day"])

        for format_name, keywords in format_keywords.items():
            if any(keyword in title for keyword in keywords):
                format_scores[format_name] += score

    return {
        "status": "available",
        "summary": (
            "Channel performance is ranked by views per day "
            "for recent uploads. Retention data is not used by "
            "this script."
        ),
        "top_formats": [
            name for name, _ in format_scores.most_common(5)
        ],
        "top_video_titles": [
            video["title"] for video in top_videos[:5]
        ],
    }


# ---------------------------------------------------------
# EXTERNAL TREND RESEARCH
# ---------------------------------------------------------

def fetch_external_trends(youtube):
    """
    Search a small number of recent public YouTube videos.

    Search ordering is not an official trending ranking.
    We calculate a rough view-velocity signal from public
    statistics and video age.
    """
    all_results = []
    searches_used = 0

    # Rotate the starting query based on the day so the system
    # samples different categories across runs.
    day_number = utc_now().timetuple().tm_yday
    rotated_queries = (
        TREND_QUERIES[day_number % len(TREND_QUERIES):]
        + TREND_QUERIES[:day_number % len(TREND_QUERIES)]
    )

    selected_queries = rotated_queries[:TREND_SEARCHES_PER_RUN]

    for query in selected_queries:
        try:
            response = youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                order="date",
                publishedAfter=(
                    utc_now() - timedelta(days=14)
                ).isoformat().replace("+00:00", "Z"),
                regionCode=REGION_CODE,
                relevanceLanguage="te",
                safeSearch="strict",
                maxResults=5,
            ).execute()

            searches_used += 1

            for item in response.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                snippet = item.get("snippet", {})

                if not video_id:
                    continue

                all_results.append({
                    "video_id": video_id,
                    "title": clean_text(snippet.get("title")),
                    "channel_title": clean_text(
                        snippet.get("channelTitle")
                    ),
                    "published_at": snippet.get("publishedAt"),
                    "query": query,
                })

        except HttpError as exc:
            log.warning(
                "Trend search failed for '%s': %s",
                query,
                exc,
            )

    # Remove duplicate search results.
    unique_results = {}
    for result in all_results:
        unique_results[result["video_id"]] = result

    results = list(unique_results.values())

    # Fetch statistics in one request instead of one request
    # per video.
    if results:
        try:
            stats_response = youtube.videos().list(
                part="statistics,snippet",
                id=",".join(
                    result["video_id"] for result in results[:50]
                ),
                maxResults=50,
            ).execute()

            stats_by_id = {
                item["id"]: item
                for item in stats_response.get("items", [])
            }

            for result in results:
                item = stats_by_id.get(result["video_id"], {})
                stats = item.get("statistics", {})

                result["views"] = safe_int(stats.get("viewCount"))
                result["likes"] = safe_int(stats.get("likeCount"))
                result["comments"] = safe_int(
                    stats.get("commentCount")
                )

                age_days = 7
                published_at = result.get("published_at")

                if published_at:
                    try:
                        published = datetime.fromisoformat(
                            published_at.replace("Z", "+00:00")
                        )
                        age_days = max(
                            1,
                            (utc_now() - published).days,
                        )
                    except ValueError:
                        pass

                result["age_days"] = age_days
                result["views_per_day"] = (
                    result["views"] / age_days
                )

        except HttpError as exc:
            log.warning("Could not fetch trend statistics: %s", exc)

    results.sort(
        key=lambda item: item.get("views_per_day", 0),
        reverse=True,
    )

    log.info(
        "Trend research used %s search calls and found %s videos.",
        searches_used,
        len(results),
    )

    return results[:MAX_EXTERNAL_RESULTS]


def summarize_trends(trend_videos):
    if not trend_videos:
        return {
            "status": "unavailable",
            "summary": "External trend data was unavailable.",
            "topics": [],
            "source_video_titles": [],
        }

    topic_counter = Counter()

    # Extract general topic signals from titles.
    for video in trend_videos:
        for word in normalized_words(video["title"]):
            if len(word) >= 4:
                topic_counter[word] += max(
                    1.0,
                    video.get("views_per_day", 0),
                )

    return {
        "status": "available",
        "summary": (
            "Recent public videos were sampled from YouTube search. "
            "Scores use views per day as a rough proxy, not an "
            "official trend ranking."
        ),
        "topics": [
            word for word, _ in topic_counter.most_common(12)
        ],
        "source_video_titles": [
            {
                "title": video["title"],
                "views": video.get("views", 0),
                "views_per_day": round(
                    video.get("views_per_day", 0), 2
                ),
                "url": (
                    "https://www.youtube.com/watch?v="
                    + video["video_id"]
                ),
            }
            for video in trend_videos[:8]
        ],
    }


# ---------------------------------------------------------
# SUPABASE STORY HISTORY
# ---------------------------------------------------------

def fetch_story_history(supabase):
    try:
        response = (
            supabase.table("story_history")
            .select("story_key,title,concept,hook,ending,status,created_at")
            .order("created_at", desc=True)
            .limit(MAX_HISTORY_ROWS)
            .execute()
        )

        return response.data or []

    except Exception as exc:
        log.error(
            "Unable to read story_history. Check table columns "
            "and Supabase permissions: %s",
            exc,
        )
        raise


# ---------------------------------------------------------
# STORY CANDIDATE GENERATION
# ---------------------------------------------------------

def choose_trend_topic(trend_summary, index):
    topics = trend_summary.get("topics", [])

    if not topics:
        fallback_topics = [
            "a surprising challenge",
            "a mysterious object",
            "an unexpected friendship",
            "a funny competition",
            "a clever solution",
        ]
        return fallback_topics[index % len(fallback_topics)]

    return topics[index % len(topics)]


def create_candidates(
    trend_summary,
    channel_summary,
    history,
):
    """
    Create original concept combinations using trend topic
    signals and varied story formats. No external video's
    script, characters, or title is copied.
    """
    candidates = []
    top_formats = channel_summary.get("top_formats", [])

    # Prioritize strong formats, but preserve variety.
    ordered_formats = sorted(
        FORMATS,
        key=lambda item: (
            0 if item["name"] in top_formats else 1,
            -item["weight"],
            item["name"],
        ),
    )

    topic_count = max(
        1,
        len(trend_summary.get("topics", [])),
    )

    for index, story_format in enumerate(ordered_formats):
        topic = choose_trend_topic(trend_summary, index)

        # Create a story premise from the topic signal.
        concept = (
            f"{story_format['description']} "
            f"Use the broad topic signal '{topic}' as inspiration, "
            "with original characters, events, and a new punchline."
        )

        # Keep titles original and avoid simply copying trending titles.
        title_templates = [
            "The Unexpected Challenge",
            "The Funniest Plan Ever",
            "A Tiny Problem, A Huge Surprise",
            "The Secret Behind the Mix-Up",
            "The Most Unbelievable Contest",
            "One Small Mistake",
            "The Surprise Nobody Expected",
            "The Cleverest Trick",
            "A Very Strange Discovery",
            "The Great Last-Second Twist",
        ]

        title_seed = (
            f"{story_format['name']}|{topic}|"
            f"{utc_now().date().isoformat()}"
        )
        seed = int(
            hashlib.sha256(title_seed.encode()).hexdigest()[:8],
            16,
        )
        title = title_templates[seed % len(title_templates)]

        # Add format and topic so each concept is distinguishable.
        title = f"{title} — {story_format['name']}"

        hook = (
            f"What happens when {topic} becomes the center "
            "of an unexpected problem?"
        )

        ending = (
            "Finish with a surprising visual reveal, a clear "
            "comic payoff, and a satisfying final reaction."
        )

        story_key = make_story_key(title, concept)

        # Similarity-based duplicate protection.
        is_duplicate = False
        for old_story in history:
            old_text = " ".join([
                clean_text(old_story.get("title")),
                clean_text(old_story.get("concept")),
            ])
            new_text = title + " " + concept

            if (
                old_story.get("story_key") == story_key
                or similarity(new_text, old_text) >= 0.72
            ):
                is_duplicate = True
                break

        if is_duplicate:
            continue

        # Proposed scoring weights:
        # 40% channel performance, 30% outside trends,
        # 20% novelty, 10% variety.
        #
        # These are initial heuristics, not proven optimal weights.

        channel_score = (
            1.0 if story_format["name"] in top_formats else 0.45
        )

        trend_score = (
            1.0 if trend_summary.get("status") == "available"
            else 0.25
        )

        # The novelty score is higher when the selected concept
        # is not very similar to the latest story history.
        max_similarity = 0.0
        for old_story in history[:30]:
            old_text = " ".join([
                clean_text(old_story.get("title")),
                clean_text(old_story.get("concept")),
            ])
            max_similarity = max(
                max_similarity,
                similarity(title + " " + concept, old_text),
            )

        novelty_score = max(0.0, 1.0 - max_similarity)

        # Reward less-recently-used formats.
        recent_format_count = sum(
            1 for old_story in history[:20]
            if story_format["name"].lower()
            in (
                clean_text(old_story.get("title")).lower()
                + " "
                + clean_text(old_story.get("concept")).lower()
            )
        )
        variety_score = 1.0 / (1.0 + recent_format_count)

        total_score = (
            0.40 * channel_score
            + 0.30 * trend_score
            + 0.20 * novelty_score
            + 0.10 * variety_score
        )

        candidates.append({
            "story_key": story_key,
            "title": title,
            "concept": concept,
            "hook": hook,
            "ending": ending,
            "format": story_format["name"],
            "audience": story_format["audience"],
            "trend_topic": topic,
            "score": round(total_score, 4),
            "score_breakdown": {
                "channel_performance": round(channel_score, 3),
                "external_trends": round(trend_score, 3),
                "novelty": round(novelty_score, 3),
                "format_variety": round(variety_score, 3),
            },
            "script": {
                "language": "Telugu",
                "format": story_format["name"],
                "target_duration_seconds": 30,
                "visual_style": (
                    "Original high-quality cinematic 3D family animation"
                ),
                "trend_inspiration": topic,
                "originality_note": (
                    "Create original characters, dialogue, visuals, "
                    "and story events. Do not copy the source videos."
                ),
                "scenes": [
                    {
                        "scene": 1,
                        "duration_seconds": 5,
                        "purpose": "Immediate visual hook",
                        "visual": (
                            f"Introduce the main character and the "
                            f"unexpected problem inspired by {topic}."
                        ),
                        "dialogue_telugu": "",
                        "audio": "Playful opening sound effect",
                    },
                    {
                        "scene": 2,
                        "duration_seconds": 8,
                        "purpose": "Escalation",
                        "visual": (
                            "The character tries a funny solution, "
                            "but the situation becomes more surprising."
                        ),
                        "dialogue_telugu": "",
                        "audio": "Light comic music and synchronized effects",
                    },
                    {
                        "scene": 3,
                        "duration_seconds": 8,
                        "purpose": "Biggest comic moment",
                        "visual": (
                            "A clear visual gag reveals the main "
                            "problem in an exaggerated but harmless way."
                        ),
                        "dialogue_telugu": "",
                        "audio": "Comic impact sound and character reaction",
                    },
                    {
                        "scene": 4,
                        "duration_seconds": 9,
                        "purpose": "Twist and payoff",
                        "visual": (
                            "Reveal an unexpected solution or reversal "
                            "and end on a memorable character reaction."
                        ),
                        "dialogue_telugu": "",
                        "audio": "Short musical payoff and clean ending",
                    },
                ],
            },
        })

    candidates.sort(
        key=lambda candidate: candidate["score"],
        reverse=True,
    )

    return candidates


# ---------------------------------------------------------
# SAVE STORY
# ---------------------------------------------------------

def save_story(supabase, story):
    """
    Insert a planned story into the existing story_history table.
    The script JSON is stored in the JSONB script column.
    """
    record = {
        "story_key": story["story_key"],
        "title": story["title"],
        "concept": story["concept"],
        "hook": story["hook"],
        "ending": story["ending"],
        "script": story["script"],
        "status": "planned",
    }

    response = (
        supabase.table("story_history")
        .insert(record)
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Supabase did not return a saved story record."
        )

    return response.data[0]


def write_json(payload):
    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info("Saved output file: %s", OUTPUT_FILE)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    started_at = utc_now()

    log.info("Starting AIKidVerse1 trend-based story planner.")

    youtube = create_youtube_client()
    supabase = create_supabase_client()

    # 1. Analyze own channel.
    own_videos = fetch_own_channel_videos(youtube)
    channel_summary = analyze_channel_performance(own_videos)

    # 2. Research external videos.
    trend_videos = fetch_external_trends(youtube)
    trend_summary = summarize_trends(trend_videos)

    # 3. Load recent story history.
    history = fetch_story_history(supabase)

    # 4. Create and score original story briefs.
    candidates = create_candidates(
        trend_summary,
        channel_summary,
        history,
    )

    if not candidates:
        raise RuntimeError(
            "No new story candidates survived duplicate checks. "
            "Run again later or review recent story history."
        )

    selected = candidates[0]

    # Attach the evidence used to select the story.
    selected["selection"] = {
        "selected_at_utc": utc_now().isoformat(),
        "planner_version": "2.0",
        "selection_score": selected["score"],
        "score_breakdown": selected["score_breakdown"],
        "channel_analysis": channel_summary,
        "trend_analysis": trend_summary,
        "trend_sources": trend_summary.get(
            "source_video_titles", []
        ),
        "own_channel_sample": [
            {
                "title": video["title"],
                "views": video["views"],
                "views_per_day": round(
                    video["views_per_day"], 2
                ),
            }
            for video in own_videos[:10]
        ],
        "history_rows_checked": len(history),
        "candidate_count": len(candidates),
        "run_duration_seconds": round(
            (utc_now() - started_at).total_seconds(), 2
        ),
        "limitations": [
            "Trend scores use public video views per day as a proxy.",
            "YouTube search results are not an official trending ranking.",
            "The planner does not use private retention analytics.",
            "Story briefs use templates and do not require a paid AI model.",
            "Final video generation, voice, editing, and upload are separate steps.",
        ],
    }

    # 5. Save the selected story to Supabase.
    saved_record = save_story(supabase, selected)
    selected["database"] = {
        "table": "story_history",
        "status": "saved",
        "record_id": saved_record.get("id"),
    }

    # 6. Write a local artifact for the next workflow step.
    write_json(selected)

    log.info("Story selected: %s", selected["title"])
    log.info("Format: %s", selected["format"])
    log.info("Score: %.4f", selected["score"])
    log.info("Planner completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Story planner failed.")
        raise
