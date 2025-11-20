from django.db import models

# python manage.py makemigrations teams
# python manage.py migrate
# python manage.py showmigrations teams

class Team(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True)   # transfermarkt team page or official site
    league = models.CharField(max_length=200, blank=True)
    logo = models.URLField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
