from django.test import SimpleTestCase
from datetime import datetime, timezone

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
