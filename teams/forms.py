from django import forms

class TeamSearchForm(forms.Form):
    q = forms.CharField(label='Team name', max_length=200)
