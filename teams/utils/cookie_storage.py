import json
import uuid

COOKIE_NAME = 'my_teams'

def get_teams(request):
    """
    Retrieve list of teams from the cookie.
    Returns a list of dictionaries.
    """
    cookie_value = request.COOKIES.get(COOKIE_NAME)
    if not cookie_value:
        return []
    try:
        return json.loads(cookie_value)
    except json.JSONDecodeError:
        return []

def save_teams(response, teams):
    """
    Save the list of teams to the cookie in the response.
    """
    response.set_cookie(COOKIE_NAME, json.dumps(teams), max_age=365*24*60*60, samesite='Lax')

def add_team(teams, name, url, league, logo):
    """
    Add a new team to the list if it doesn't exist.
    Returns (team_dict, created_boolean).
    """
    # Check for duplicates (by name or url)
    for team in teams:
        if team['name'] == name or (url and team.get('url') == url):
            return team, False # existing, not created

    new_team = {
        'id': str(uuid.uuid4()),
        'name': name,
        'url': url,
        'league': league,
        'logo': logo
    }
    teams.append(new_team)
    return new_team, True

def remove_team_by_id(teams, team_id):
    """
    Remove a team by its ID.
    Returns the new list of teams.
    """
    return [t for t in teams if t.get('id') != team_id]
