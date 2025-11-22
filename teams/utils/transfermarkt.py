# teams/utils/transfermarkt.py
import re
import time
from urllib.parse import urljoin, quote, urlparse
from datetime import datetime, timedelta, timezone
from tzlocal import get_localzone
import requests
import random
from bs4 import BeautifulSoup

BASE = "https://www.transfermarkt.com"
REQUEST_TIMEOUT = 10
DEFAULT_TZ = datetime.now(timezone.utc).astimezone().tzinfo

def get_random_user_agent():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0',
        'Opera/9.80 (X11; Linux i686; Ubuntu/14.10) Presto/2.12.388 Version/12.16.2'
    ]
    return random.choice(user_agents)

def get_headers():
    return {
        'User-Agent': get_random_user_agent(), 
        "Referer": "https://www.google.com"
        }

def _safe_get(url, sleep=0.5):
    """GET with headers and small delay to be nicer to the server."""
    time.sleep(sleep)
    r = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text

def _extract_team_id_from_url(url):
    """
    Try to extract the numeric team id from Transfermarkt URLs like:
      .../verein/131 or .../verein/131/saison_id/2024
    """
    m = re.search(r'/verein/(\d+)', url)
    return int(m.group(1)) if m else None

def _extract_team_name_from_url(url):
    """
    Try to extract the team name from Transfermarkt URLs like:
      .../fc-barcelona/startseite/verein/131 or .../real-madrid/transfers/verein/418
    """
    team_url_name = None
    m = re.search(r'transfermarkt\.com/([^/]+)/startseite/verein/\d+', url)
    if m:
        team_url_name = m.group(1)
    else:
        m = re.search(r'transfermarkt\.com/([^/]+)/transfers/verein/\d+', url)
        if m:
            team_url_name = m.group(1)
    return team_url_name

def search_transfermarkt(query, max_results=10, domain=BASE):
    """
    Search TransferMarkt for clubs matching `query`.
    Returns list of dicts: {'name','url','league','logo'}.
    Strategy:
      - call /schnellsuche/ergebnis/schnellsuche?query=...
      - from the HTML collect all links that contain '/verein/' (club pages)
      - for each club link fetch club page and extract name/league/logo
    Notes: schnellsuche returns mixed results (players, clubs, competitions). We filter by '/verein/'.
    """
    q = quote(query)
    search_url = f"{domain}/schnellsuche/ergebnis/schnellsuche?query={q}"
    html = _safe_get(search_url)

    soup = BeautifulSoup(html, 'html.parser')
    results = []
    seen = set()

    # Find all anchors linking to /verein/
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/verein/' not in href:
            continue
        full = urljoin(domain, href)
        if full in seen:
            continue
        seen.add(full)
        # We'll fetch club page to get clean metadata
        try:
            meta = parse_club_page(full)
            if meta:
                results.append(meta)
        except Exception as e:
            # ignore single failures but keep going
            # in production log this properly
            print("search_transfermarkt: error parsing", full, e)
        if len(results) >= max_results:
            break

    # As fallback: if no /verein/ links found, attempt to parse
    # textual results (some pages render results as JS; then this may fail).
    return results

def parse_club_page(club_url):
    """
    Fetch club page and extract: name, url, league, logo.
    Robust approach with several fallbacks.
    """
    html = _safe_get(club_url)
    soup = BeautifulSoup(html, 'html.parser')

    # 1) Name: usually in <h1> (or <div class="dataHeader"> etc.)
    name = None
    h1 = soup.find('h1')
    if h1:
        name = h1.get_text(strip=True)
    if not name:
        # sometimes title contains "Club - Transfermarkt"
        title = soup.title.string if soup.title else ''
        if title:
            name = title.split('-')[0].strip()

    # 2) Logo: look for <img> with alt matching name or large image in header
    logo = ''
    if name:
        # search images where alt contains name or nearby image in header
        imgs = soup.find_all('img', alt=True)
        for img in imgs:
            alt = img.get('alt', '').strip()
            src = img.get('src') or img.get('data-src') or ''
            if not src:
                continue
            if name.lower() in alt.lower() or 'logo' in alt.lower() or 'verein' in alt.lower():
                logo = urljoin(BASE, src)
                break
        if not logo and imgs:
            logo = urljoin(BASE, imgs[0].get('src') or imgs[0].get('data-src') or '')

    # 3) League: site usually shows league near top (breadcrumb or a div containing competition)
    league = ''
    club_info = soup.find('div', class_='data-header__club-info')
    if club_info:
        club_span = club_info.find('span', class_='data-header__club')
        if club_span:
            leage_link = club_span.find('a')
            if leage_link:
                league = leage_link.get_text(strip=True)

    # fallback: try to find an <a> whose href contains '/wettbewerb/'
    if not league:
        for a in soup.find_all("a", href=True):
            if '/wettbewerb/' in a['href']:
                league = a.get_text(strip=True)
                break

    # final sanity checks
    if not name:
        return None

    return {
        'name': name,
        'url': club_url,
        'league': league or '',
        'logo': logo or ''
    }

def process_datetime(date_str, time_str) -> datetime:
    date_split = date_str.split(' ')[1].split('/')
    date_year = int(date_split[2]) + 2000
    date_month = int(date_split[1])
    date_day = int(date_split[0])
    time_part = time.strptime(time_str, '%I:%M %p')

    local_tz_object = get_localzone()
    # somehow it seems we need to do this in 2 steps - first create a naive date and then apply timezone
    # doing it in one step doesn't work, when trying to convert to UTC
    date_datetime_local = datetime(date_year, date_month, date_day, time_part.tm_hour, time_part.tm_min)
    date_datetime_local = date_datetime_local.replace(tzinfo=local_tz_object)
    date_datetime_utc = date_datetime_local.astimezone(timezone.utc)
    # returning datetime in UTC
    return date_datetime_utc


def fetch_upcoming_matches_for_team(team, days_ahead=30, domain=BASE):
    """
    Given a Team object (with .url attribute) or a club_url string, return upcoming matches list:
      [{'home','away','datetime' (tz-aware),'url','team_name','team_id'}...]
    Strategy:
      - extract team name and id from team.url: /{name}/startseite/{id}
      - construct spielplan url: /{name}/spielplandatum/verein/{id}
      - parse table rows: find date/time, opponent, match link
    """
    club_url = None
    if isinstance(team, dict):
        club_url = team.get('url')
    elif hasattr(team, 'url'):
        club_url = team.url
    else:
        club_url = team

    if not club_url:
        return []

    team_id = _extract_team_id_from_url(club_url)
    if not team_id:
        # try to fetch club page and re-run extraction
        try:
            meta = parse_club_page(club_url)
            team_id = _extract_team_id_from_url(meta.get('url','')) if meta else None
        except Exception:
            team_id = None

    if not team_id:
        return []
    
    team_name = _extract_team_name_from_url(club_url)
    if not team_name:
        # try to fetch club page and re-run extraction
        try:
            meta = parse_club_page(club_url)
            team_name = _extract_team_name_from_url(meta.get('url','')) if meta else None
        except Exception:
            team_name = None

    if not team_name:
        return []

    # construct season-sensitive spielplan URL
    now = datetime.now(DEFAULT_TZ)
    season_year = now.year if now.month >= 7 else now.year - 1  # heuristic: european season start in summer
    candidates = [
        f"{domain}/{team_name}/spielplandatum/verein/{team_id}"
    ]

    html = None
    for url in candidates:
        try:
            html = _safe_get(url)
            if html and 'No matches' not in html:  # cheap heuristics
                base_page_url = url
                break
        except Exception:
            html = None
            continue
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')

    matches = []

    # Find the team name
    headline = soup.find('div', class_='data-header__headline-container')
    team_name_display = headline.find('h1').text.strip()

    # Find the matches
    responsive_table_div = soup.find('div', class_='responsive-table')
    responsive_table = responsive_table_div.find('table')
    responsive_table_tbody = responsive_table.find('tbody')
    mecze = responsive_table_tbody.findAll('tr')
    league = ""
    for mecz in mecze:
        if (len(mecz.contents) > 5):
            tds = mecz.findAll('td')
            # check if it's a fixture or already played match
            match_report_or_preview = tds[9].contents[0].attrs.get('title')
            # check if the exact time is already known
            time_is_known = tds[2].text.strip() != 'Unknown' and tds[2].text.strip() != '12:00 AM'
            if (match_report_or_preview == 'Match preview' and time_is_known):
                date_datetime = process_datetime(tds[1].text.strip(), tds[2].text.strip())
                home_or_away = tds[3].text.strip()
                opponent = tds[6].find('a').text.strip()
                home = ''
                away = ''
                if (home_or_away == 'H'):
                    home = team_name_display
                    away = opponent
                    #teams_match = f"{team_name_display} - {opponent}"
                else:
                    home = opponent
                    away = team_name_display
                    #teams_match = f"{opponent} - {team_name_display}"
                match_link = f"{domain}{tds[9].find('a').attrs.get('href')}"
                
                original_team_name = ''
                if isinstance(team, dict):
                    original_team_name = team.get('name', '')
                else:
                    original_team_name = getattr(team, 'name', '')

                matches.append({
                    'home': home,
                    'away': away,
                    'league': league,
                    'datetime': date_datetime,
                    'url': match_link,
                    'team_id': team_id,
                    'team_name': original_team_name
                })

                #events.append((league, date_datetime, teams_match))
                #print(f"{league}: {teams_match}, {date_datetime}")
        else:
            league = mecz.find('td').find('img').attrs.get('title')



    # filter by next X days (days_ahead)
    #now = timezone.now()
    now = datetime.now(DEFAULT_TZ)
    filtered = [m for m in matches if 0 <= (m['datetime'] - now).days <= days_ahead]
    # sort by datetime
    filtered.sort(key=lambda x: x['datetime'])
    return filtered
