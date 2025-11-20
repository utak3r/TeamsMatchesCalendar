from django.urls import path
from . import views
from .utils import google_calendar

app_name = 'teams'
urlpatterns = [
    path('', views.team_list, name='team_list'),
    path('search/', views.tm_search, name='search'),
    path('add/', views.add_team_from_tm, name='add'),
    path('upcoming/', views.upcoming_matches, name='upcoming'),
    path('add-to-calendar/', views.add_matches_to_calendar, name='add_to_calendar'),
    path('remove/<int:team_id>/', views.remove_team, name='remove'),
    path('oauth2callback/', google_calendar.oauth2callback, name='oauth2callback'),
]
