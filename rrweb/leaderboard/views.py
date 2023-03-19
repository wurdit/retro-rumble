import csv
import pytz
from itertools import groupby
from datetime import datetime, timedelta
from humanize import naturaltime
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template import loader
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from leaderboard.models import Player, Game, Challenge, PlayerScore, Setting
from .retro import RAclient

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
MIN_UPDATE_INTERVAL_SECONDS = 60 * 10

def is_update_allowed():
    last_run = Setting.objects.filter(name='last_run')[0]
    last_run_date = pytz.utc.localize(datetime.strptime(last_run.value, DATE_FORMAT))
    utc_now = pytz.utc.localize(datetime.utcnow())

    can_be_run = False

    if (utc_now - last_run_date).seconds > MIN_UPDATE_INTERVAL_SECONDS:
        can_be_run = True

    return (can_be_run, last_run, naturaltime(last_run_date, when=utc_now))

def get_login():
    username = Setting.objects.filter(name='username')[0].value
    api_key = Setting.objects.filter(name='api_key')[0].value
    return (username, api_key)

def table_test(request):
    template = loader.get_template('leaderboard/table.html')
    table = [['1', '2', '3']]
    context = {
        'header': ['a', 'b', 'c'],
        'table': table
    }
    return HttpResponse(template.render(context, request))

class LeaderBoardEntry():
    def __init__(self, name: str, total_score: int, game_scores: list) -> None:
        self.name = name
        self.total_score = total_score
        self.game_scores = game_scores

def index(request):
    can_be_run, last_run, natural_time = is_update_allowed()

    challenge_id = get_max_challenge_id()

    games = Game.objects.filter(challenge__id=challenge_id).order_by('retro_game_id')
    scores = PlayerScore.objects.filter(game__challenge__id=2, player__is_active=True).order_by('player_id', 'game__retro_game_id').select_related('player')

    grouped_scores = [(key, list(group)) for key, group in groupby(scores, key=lambda x: x.player)]
    sorted_grouped_scores = sorted(grouped_scores, key=lambda x: sum([score.score for score in x[1]]), reverse=True)

    template = loader.get_template('leaderboard/index.html')
    context = {
        'games': games,
        'sorted_grouped_scores': sorted_grouped_scores,
        'last_run': natural_time,
        'can_be_run': can_be_run
    }
    return HttpResponse(template.render(context, request))

def update(request):
    can_be_run, last_run, natural_time = is_update_allowed()

    if not can_be_run:
        raise PermissionDenied()
    else:
        last_run.value = timezone.now().strftime(DATE_FORMAT)
        last_run.save()
        refresh_leaderboard()
        return redirect('/leaderboard', permanent=False)
    
def get_max_challenge_id():
    challenge_id = max_id = Challenge.objects.aggregate(Max('id'))['id__max']
    return challenge_id
    
def refresh_leaderboard():
    challenge_id = get_max_challenge_id()
    challenge = Challenge.objects.get(pk=challenge_id)
    games = challenge.game_set.all()
    print(games)

    players = Player.objects.filter(is_active=True)
    print(players)

    username, api_key = get_login()
    client = RAclient(username, api_key)

    leaderboard = {player_name: 0 for player_name in [p.name for p in players]}

    for player in players:
        data = client.get_achievements_earned_between(player.name, challenge.start, challenge.end)

        for game in games:
            progress = data.get_progress(game.retro_game_id)
            print(f'{player.name}, {game.retro_game_id}: {progress}')
            leaderboard[player.name] += progress
            update_player_score(player, game, progress)
        print()

    for player in sorted(((v,k) for k,v in leaderboard.items()), reverse=True):
        print(f'{player[1]} ({player[0]})')

def update_player_score(player: Player, game: Game, score: int):
    player_score = PlayerScore()
    try:
        player_score = PlayerScore.objects.get(player_id=player.pk, game_id=game.pk)
        print(f'Player score for {player.name} and game {game.retro_game_id} exists. Updating...')
    except PlayerScore.DoesNotExist:
        player_score.player = player
        player_score.game = game
        print(f'Player score for {player.name} and game {game.retro_game_id} does NOT exist. Creating...')

    player_score.score = score
    player_score.save()

def import_players(request):
    response = ''
    with open(r'./players.csv', newline='') as csvfile:
        player_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in player_reader:
            name = row[0]
            is_active = True if row[1].lower().strip() == 'true' else False
            player = Player(name=name, is_active=is_active)
            response += f'{player}</br>'
            player.save() 
    return HttpResponse(response)

def import_games(request):
    username = Setting.objects.filter(name='username')[0].value
    api_key = Setting.objects.filter(name='api_key')[0]
    response = ''
    with open(r'./games.csv', newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            retro_game_id = int(row[0])
            challenge_id = int(row[1])
            game = Game(retro_game_id = retro_game_id, challenge_id=challenge_id)
            client = RAclient(username, api_key)
            game_data = client.get_game(retro_game_id)
            game.name = game_data['Title']
            game.image_icon = game_data['ImageIcon']
            game.game_icon = game_data['GameIcon']
            game.image_title = game_data['ImageTitle']
            game.image_ingame = game_data['ImageIngame']
            game.image_box_art = game_data['ImageBoxArt']
            print(game.name)
            response += f'{game}</br>'
            game.save()
    return HttpResponse(response)

def refresh_games(request):
    username, api_key = get_login()
    client = RAclient(username, api_key)
    response = ''

    games = Game.objects.all()

    for game in games:
        data = client.get_game(game.retro_game_id)
        game.name = data['Title']
        game.image_icon = data['ImageIcon']
        game.game_icon = data['GameIcon']
        game.image_title = data['ImageTitle']
        game.image_ingame = data['ImageIngame']
        game.image_box_art = data['ImageBoxArt']
        game.save()
        response += f'{game}</br>'
    
    return HttpResponse(response)
