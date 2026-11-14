import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

API_KEY = os.environ.get("THESPORTSDB_API_KEY", "123")
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"
REQUEST_TIMEOUT = 10


def _get_json(endpoint, params=None, max_retries=2):
    """Fetch JSON from a TheSportsDB API endpoint, retrying briefly on HTTP 429."""
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(max_retries + 1):
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and attempt < max_retries:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 1.5 * (attempt + 1)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()


def _extract_team_id(team):
    """Extract numeric TheSportsDB team ID from a team dict, object, URL, or ID string."""
    if isinstance(team, dict):
        raw = team.get("url") or team.get("idTeam") or ""
    elif hasattr(team, "url"):
        raw = team.url or ""
    else:
        raw = str(team or "")

    match = re.search(r"/team/(\d+)", raw)
    if match:
        return match.group(1)
    if raw.strip().isdigit():
        return raw.strip()
    return None


def _parse_event_datetime(event):
    """Parse event kickoff time from TheSportsDB event dict into a UTC-aware datetime."""
    ts = (event.get("strTimestamp") or "").strip()
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

    date_str = (event.get("dateEvent") or "").strip()
    time_str = (event.get("strTime") or "").strip()
    if not date_str or not time_str:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def search_teams(query, max_results=10):
    """Search TheSportsDB for soccer teams matching `query`."""
    if not query or not query.strip():
        return []

    data = _get_json("searchteams.php", params={"t": query.strip()})
    teams = data.get("teams") or []

    results = []
    for team in teams:
        if team.get("strSport") != "Soccer":
            continue
        team_id = team.get("idTeam")
        name = team.get("strTeam")
        if not team_id or not name:
            continue
        results.append({
            "name": name,
            "url": f"https://www.thesportsdb.com/team/{team_id}",
            "league": team.get("strLeague") or "",
            "logo": team.get("strBadge") or team.get("strTeamBadge") or "",
        })
        if len(results) >= max_results:
            break

    return results


def fetch_upcoming_matches_for_team(team, days_ahead=30):
    """Return upcoming matches for a team from TheSportsDB within `days_ahead` days."""
    team_id = _extract_team_id(team)
    if not team_id:
        return []

    data = _get_json("eventsnext.php", params={"id": team_id})
    events = data.get("events") or []

    if isinstance(team, dict):
        original_team_name = team.get("name", "")
    else:
        original_team_name = getattr(team, "name", "")

    now = datetime.now(timezone.utc)
    max_delta = timedelta(days=days_ahead)
    matches = []

    for event in events:
        dt = _parse_event_datetime(event)
        if not dt:
            continue
        delta = dt - now
        if not (timedelta(0) <= delta <= max_delta):
            continue

        event_id = event.get("idEvent")
        matches.append({
            "home": event.get("strHomeTeam") or "",
            "away": event.get("strAwayTeam") or "",
            "league": event.get("strLeague") or "",
            "datetime": dt,
            "url": f"https://www.thesportsdb.com/event/{event_id}" if event_id else "",
            "team_id": team_id,
            "team_name": original_team_name,
        })

    matches.sort(key=lambda m: m["datetime"])
    return matches
