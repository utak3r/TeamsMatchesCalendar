from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from django.shortcuts import redirect
from django.conf import settings
from django.urls import reverse
from datetime import datetime, timedelta, timezone
from TeamsMatchesCalendar import settings

SCOPES = ['https://www.googleapis.com/auth/calendar.events',
          'https://www.googleapis.com/auth/calendar.readonly']
# now we're reading it from settings
#CLIENT_SECRETS_FILE = os.path.join(settings.BASE_DIR, 'credentials.json')

def ensure_credentials_for_user(request):
    """
    Checks if credentials are in session; if not, starts auth flow and returns redirect to consent.
    Returns dict: {'redirect': HttpResponseRedirect} or {'credentials': creds}
    """
    creds_data = request.session.get('google_creds')
    if creds_data:
        creds = Credentials(**creds_data)
        return {'credentials': creds}
    # start auth flow
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=request.build_absolute_uri(reverse('teams:oauth2callback'))
    )
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    request.session['oauth_state'] = state
    return {'redirect': redirect(auth_url)}

def oauth2callback(request):
    state = request.session.get('oauth_state')
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=request.build_absolute_uri(reverse('teams:oauth2callback'))
    )
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    creds = flow.credentials
    # save creds in session (demo)
    request.session['google_creds'] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    return redirect(reverse('teams:upcoming'))

def date_treat_as_local(date):
    local_tz = datetime.now(timezone.utc).astimezone().tzinfo
    new_date = datetime(date.year, date.month, date.day, date.hour, date.minute, tzinfo=local_tz)
    return new_date

def create_events_for_matches(credentials, matches, calendar_id='primary'):
    """
    Creates or updates match events in Google Calendar.
    Does not duplicate matches, updates if the time changes.
    """
    service = build('calendar', 'v3', credentials=credentials)
    created_or_updated = []

    for m in matches:
        dt = m.get('datetime')
        if not dt:
            continue

        #dt = date_treat_as_local(dt)
        summary = f"{m['home']} - {m['away']}"
        league = m.get('league')
        start = dt.isoformat()
        end = (dt + timedelta(hours=2)).isoformat()

        # 🔍 1. Search for similar events (on this day)
        time_min = (dt - timedelta(days=1)).astimezone().isoformat()
        time_max = (dt + timedelta(days=1)).astimezone().isoformat()

        existing_events = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            q=summary,  # search by match title
            singleEvents=True
        ).execute().get('items', [])

        # 🔎 2. Check if the match already exists
        existing_event = None
        for e in existing_events:
            if e.get('summary') == summary:
                existing_event = e
                break

        if existing_event:
            # ⏰ 3. Compare dates
            existing_start = existing_event['start'].get('dateTime')
            if existing_start and existing_start != start:
                # Changed time — update
                existing_event['start'] = {'dateTime': start}
                existing_event['end'] = {'dateTime': end}
                existing_event['description'] = f"{league}\nMatch page: {m.get('url', '')}"

                updated = service.events().update(
                    calendarId=calendar_id,
                    eventId=existing_event['id'],
                    body=existing_event
                ).execute()
                created_or_updated.append({'action': 'updated', 'id': updated['id'], 'summary': summary})
            else:
                # No changes
                created_or_updated.append({'action': 'skipped', 'summary': summary})
        else:
            # 🆕 4. New event
            event = {
                'summary': summary,
                'description': f"{league}\nMatch page: {m.get('url', '')}",
                'start': {'dateTime': start},
                'end': {'dateTime': end},
            }
            created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
            created_or_updated.append({'action': 'created', 'id': created_event['id'], 'summary': summary})

    return created_or_updated
