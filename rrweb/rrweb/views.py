from django.http import HttpResponse

def index(request):
    return(HttpResponse('<a href="leaderboard">Retro Rumble Leaderboard</a>'))