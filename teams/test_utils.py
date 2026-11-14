from django.test import SimpleTestCase
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
import requests

class utils(SimpleTestCase):

    def test_process_datetime(self):
        from teams.utils.transfermarkt import process_datetime
        
        date_str = 'Sun 19/10/25'
        time_str = '2:45 PM'
        # CEST is UTC+2
        expected = datetime(2025, 10, 19, 12, 45, tzinfo=timezone.utc)
        self.assertEqual(process_datetime(date_str, time_str), expected)

        date_str = 'Sat 25/10/25'
        time_str = '5:30 PM'
        # CEST is UTC+2
        expected = datetime(2025, 10, 25, 15, 30, tzinfo=timezone.utc)
        self.assertEqual(process_datetime(date_str, time_str), expected)

        date_str = 'Thu 30/10/25'
        time_str = '9:00 PM'
        # On last Sunday of October, which is October 26th, it becomes
        # CET (UTC+1)
        expected = datetime(2025, 10, 30, 20, 00, tzinfo=timezone.utc)
        self.assertEqual(process_datetime(date_str, time_str), expected)


        date_str = 'Mon 03/11/25'
        time_str = '6:00 PM'
        # CET (UTC+1)
        expected = datetime(2025, 11, 3, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(process_datetime(date_str, time_str), expected)

        date_str = 'Sun 09/11/25'
        time_str = '5:30 PM'
        # CET (UTC+1)
        expected = datetime(2025, 11, 9, 16, 30, tzinfo=timezone.utc)
        self.assertEqual(process_datetime(date_str, time_str), expected)


class TheSportsDBTests(SimpleTestCase):

    @patch('teams.utils.thesportsdb.requests.get')
    def test_search_teams_filters_soccer_and_maps_fields(self, mock_get):
        from teams.utils.thesportsdb import search_teams

        mock_resp = Mock()
        mock_resp.json.return_value = {
            'teams': [
                {
                    'idTeam': '135302',
                    'strTeam': 'Pogoń Szczecin',
                    'strSport': 'Soccer',
                    'strLeague': 'Polish Ekstraklasa',
                    'strBadge': 'https://example.com/pogon.png',
                },
                {
                    'idTeam': '999999',
                    'strTeam': 'Pogoń Basketball',
                    'strSport': 'Basketball',
                    'strLeague': 'PLK',
                    'strBadge': 'https://example.com/basket.png',
                },
            ]
        }
        mock_get.return_value = mock_resp

        results = search_teams('Pogon')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], {
            'name': 'Pogoń Szczecin',
            'url': 'https://www.thesportsdb.com/team/135302',
            'league': 'Polish Ekstraklasa',
            'logo': 'https://example.com/pogon.png',
        })
        mock_resp.raise_for_status.assert_called_once()

    @patch('teams.utils.thesportsdb.requests.get')
    def test_search_teams_handles_empty_or_null_results(self, mock_get):
        from teams.utils.thesportsdb import search_teams

        self.assertEqual(search_teams('   '), [])
        mock_get.assert_not_called()

        mock_resp = Mock()
        mock_resp.json.return_value = {'teams': None}
        mock_get.return_value = mock_resp
        self.assertEqual(search_teams('UnknownTeam'), [])

    @patch('teams.utils.thesportsdb.requests.get')
    def test_search_teams_raises_on_http_error(self, mock_get):
        from teams.utils.thesportsdb import search_teams

        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError('500 Server Error')
        mock_get.return_value = mock_resp

        with self.assertRaises(requests.HTTPError):
            search_teams('Barcelona')

    @patch('teams.utils.thesportsdb.time.sleep')
    @patch('teams.utils.thesportsdb.requests.get')
    def test_search_teams_retries_on_429(self, mock_get, mock_sleep):
        from teams.utils.thesportsdb import search_teams

        resp_429 = Mock(status_code=429, headers={'Retry-After': '1'})
        resp_200 = Mock(status_code=200)
        resp_200.json.return_value = {
            'teams': [{
                'idTeam': '133901',
                'strTeam': 'Poland',
                'strSport': 'Soccer',
                'strLeague': 'UEFA Nations League',
                'strBadge': '',
            }]
        }
        mock_get.side_effect = [resp_429, resp_200]

        results = search_teams('Poland')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Poland')
        mock_sleep.assert_called_once_with(1.0)

    @patch('teams.utils.thesportsdb.requests.get')
    def test_fetch_upcoming_matches_for_team_happy_path_and_filtering(self, mock_get):
        from teams.utils.thesportsdb import fetch_upcoming_matches_for_team

        now = datetime.now(timezone.utc)
        in_range = (now + timedelta(days=2)).replace(microsecond=0)
        past_event = (now - timedelta(hours=2)).replace(microsecond=0)
        too_far = (now + timedelta(days=45)).replace(microsecond=0)

        mock_resp = Mock()
        mock_resp.json.return_value = {
            'events': [
                {
                    'idEvent': '101',
                    'strHomeTeam': 'Romania',
                    'strAwayTeam': 'Poland',
                    'strLeague': 'UEFA Nations League',
                    'strTimestamp': in_range.strftime('%Y-%m-%dT%H:%M:%S'),
                },
                {
                    'idEvent': '102',
                    'strHomeTeam': 'Poland',
                    'strAwayTeam': 'Old Opponent',
                    'strLeague': 'UEFA Nations League',
                    'strTimestamp': past_event.strftime('%Y-%m-%dT%H:%M:%S'),
                },
                {
                    'idEvent': '103',
                    'strHomeTeam': 'Poland',
                    'strAwayTeam': 'Far Opponent',
                    'strLeague': 'Friendly',
                    'dateEvent': too_far.strftime('%Y-%m-%d'),
                    'strTime': too_far.strftime('%H:%M:%S'),
                },
            ]
        }
        mock_get.return_value = mock_resp

        matches = fetch_upcoming_matches_for_team({
            'name': 'Poland',
            'url': 'https://www.thesportsdb.com/team/133901',
        })

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['home'], 'Romania')
        self.assertEqual(matches[0]['away'], 'Poland')
        self.assertEqual(matches[0]['league'], 'UEFA Nations League')
        self.assertEqual(matches[0]['datetime'], in_range)
        self.assertEqual(matches[0]['url'], 'https://www.thesportsdb.com/event/101')
        self.assertEqual(matches[0]['team_id'], '133901')
        self.assertEqual(matches[0]['team_name'], 'Poland')

    @patch('teams.utils.thesportsdb.requests.get')
    def test_fetch_upcoming_matches_fallback_date_time_and_invalid_url(self, mock_get):
        from teams.utils.thesportsdb import fetch_upcoming_matches_for_team

        # Invalid/legacy URL without /team/<id> returns [] without calling API
        self.assertEqual(
            fetch_upcoming_matches_for_team({'name': 'Poland', 'url': 'https://www.transfermarkt.com/polen/startseite/verein/3442'}),
            [],
        )
        mock_get.assert_not_called()

        # Fallback to dateEvent + strTime when strTimestamp is missing
        in_range = (datetime.now(timezone.utc) + timedelta(days=1)).replace(second=0, microsecond=0)
        mock_resp = Mock()
        mock_resp.json.return_value = {
            'events': [
                {
                    'idEvent': '202',
                    'strHomeTeam': 'Barcelona',
                    'strAwayTeam': 'Villarreal',
                    'strLeague': 'Spanish La Liga',
                    'dateEvent': in_range.strftime('%Y-%m-%d'),
                    'strTime': in_range.strftime('%H:%M:%S'),
                },
                {
                    'idEvent': '203',
                    'strHomeTeam': 'Barcelona',
                    'strAwayTeam': 'No Time FC',
                    'strLeague': 'Spanish La Liga',
                    'dateEvent': in_range.strftime('%Y-%m-%d'),
                    'strTime': '',
                },
            ]
        }
        mock_get.return_value = mock_resp

        matches = fetch_upcoming_matches_for_team('https://www.thesportsdb.com/team/133739')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['datetime'], in_range)
