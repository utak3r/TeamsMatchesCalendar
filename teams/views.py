from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Team
from .forms import TeamSearchForm
from .utils.transfermarkt import search_transfermarkt, fetch_upcoming_matches_for_team
from .utils.google_calendar import create_events_for_matches, ensure_credentials_for_user
from django.contrib import messages
import datetime
from django.utils import timezone

def team_list(request):
    teams = Team.objects.order_by('name')
    form = TeamSearchForm()
    return render(request, 'teams/team_list.html', {'teams': teams, 'form': form})

@require_POST
def tm_search(request):
    form = TeamSearchForm(request.POST)
    if not form.is_valid():
        return redirect('teams:list')
    q = form.cleaned_data['q']
    # search_transfermarkt should return a list of dicts:
    # [{'name':..., 'url':..., 'league':..., 'logo':...}, ...]
    results = search_transfermarkt(q)
    return render(request, 'teams/search_results.html', {'results': results, 'q': q})

@require_POST
def add_team_from_tm(request):
    # params from the add button on search_results: url, name, league, logo
    name = request.POST.get('name')
    url = request.POST.get('url')
    league = request.POST.get('league', '')
    logo = request.POST.get('logo', '')
    if not name:
        messages.error(request, 'Brak nazwy drużyny.')
        return redirect('teams:team_list')
    team, created = Team.objects.get_or_create(name=name, defaults={'url': url or '', 'league': league, 'logo': logo})
    if not created:
        # optionally update fields
        team.url = url or team.url
        team.league = league or team.league
        team.logo = logo or team.logo
        team.save()
    messages.success(request, f'Dodano drużynę {team.name}')
    return redirect('teams:team_list')

def upcoming_matches(request):
    teams = Team.objects.all()
    matches = []
    for team in teams:
        try:
            team_matches = fetch_upcoming_matches_for_team(team)
            matches.extend(team_matches)
        except Exception as e:
            # log; continue
            print(f"Error fetching for {team}: {e}")
    # Each match dict should contain at least: 'home','away','datetime'(timezone-aware), 'url','team'...
    matches = sorted(matches, key=lambda m: m['datetime'])
    return render(request, 'teams/upcoming_matches.html', {'matches': matches})

@require_POST
def add_matches_to_calendar(request):
    # This view will:
    # 1) ensure user has OAuth credentials (redirect to consent if needed)
    # 2) create events for the posted matches
    # For demo we'll accept a JSON payload with matches; in practice use server-side fetching / session flows.

    # Example: we'll fetch upcoming matches server-side and create events for them.
    teams = Team.objects.all()
    matches = []
    for team in teams:
        try:
            matches.extend(fetch_upcoming_matches_for_team(team))
        except Exception:
            pass
    matches = sorted(matches, key=lambda m: m['datetime'])

    # Ensure credentials: this function should check for token in session and if not, return redirect URL
    creds_flow = ensure_credentials_for_user(request)
    if creds_flow.get('redirect'):
        return creds_flow['redirect']  # HttpResponseRedirect to Google consent

    credentials = creds_flow['credentials']
    created_events = create_events_for_matches(credentials, matches)
    messages.success(request, f'Added {len(created_events)} events to Google Calendar.')
    return redirect('teams:upcoming')

@require_POST
def remove_team(request, team_id):
    team = get_object_or_404(Team, pk=team_id)
    team_name = team.name
    team.delete()
    messages.success(request, f'Removed team {team_name}.')
    return redirect('teams:team_list')
