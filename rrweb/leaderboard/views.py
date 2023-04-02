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
from django.db.models import Max, Sum
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from leaderboard.models import Player, Game, Challenge, PlayerScore, Setting, Achievement
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
    scores = PlayerScore.objects.filter(game__challenge__id=challenge_id, player__is_active=True).order_by('player_id', 'game__retro_game_id').select_related('player')

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
        challenge_id = get_max_challenge_id()
        refresh_leaderboard_smart(challenge_id)
        return redirect('/leaderboard', permanent=False)
    
def get_max_challenge_id():
    challenge_id = Challenge.objects.aggregate(Max('id'))['id__max']
    return challenge_id

@transaction.atomic
def refresh_leaderboard_smart(challenge_id: int):
    challenge = Challenge.objects.get(pk=challenge_id)
    games = Game.objects.filter(challenge__id=challenge.pk).order_by('retro_game_id')
    players = Player.objects.filter(is_active=True)
    player_scores = PlayerScore.objects.filter(game__challenge__id=challenge_id).select_related('game')

    players_needing_update = list()
    # Store individual player progress for updating PlayerScores later
    players_progress = dict()

    username, api_key = get_login()
    client = RAclient(username, api_key)

    for player in players:
        user_progress = client.get_user_progress(player.name, [game.retro_game_id for game in games] )
        players_progress[player.name] = user_progress

        for game in games:
            game_progress = user_progress[game.retro_game_id]
            player_score = player_scores.filter(player_id=player.pk, game_id=game.pk).first()
            if not player_score or player_score.raw_score != game_progress.score_achieved_hardcore:
                players_needing_update.append(player)
                break
    
    scores_to_update = list()
    scores_to_create = list()

    for player in players_needing_update:
        # print(player)
        max_date = Achievement.objects.filter(player_id=player.pk).aggregate(Max('date'))['date__max']
        # Only get achievments starting 1s after the date of the latest achievement, if any.
        start = max_date.timestamp() + 1 if max_date else challenge.start
        achievements_earned_between = client.get_achievements_earned_between(player.name, start, challenge.end)
        achievements_to_store = list()

        for remote_achievement in achievements_earned_between.achievements:
            # TODO: Should probably check the remote_achievement for missing data
            game = games.filter(retro_game_id=remote_achievement.game_id).first()
            # Don't store achievements for games not in the challenge
            if game:
                achievement = Achievement()
                achievement.player = player
                achievement.game = game
                achievement.achievement_id = remote_achievement.id
                achievement.title = remote_achievement.title
                achievement.description = remote_achievement.description
                achievement.date = remote_achievement.date
                achievement.hardcore = remote_achievement.hardcore
                achievement.points = remote_achievement.points
                achievements_to_store.append(achievement)
        
        Achievement.objects.bulk_create(achievements_to_store)

        # Update PlayerScores
        user_progress = players_progress[player.name]
        for game in games:
            game_progress = user_progress[game.retro_game_id]
            player_score = player_scores.filter(player_id=player.pk, game_id=game.pk).first()
            if not player_score:
                player_score = PlayerScore()
                player_score.player = player
                player_score.game = game
                scores_to_create.append(player_score)
            else:
                scores_to_update.append(player_score)
            hardcore_sum = Achievement.objects.filter(player=player, game=game, hardcore=True).aggregate(Sum('points'))['points__sum']
            player_score.score = hardcore_sum or 0
            player_score.raw_score = game_progress.score_achieved_hardcore    
        
    PlayerScore.objects.bulk_create(scores_to_create)
    PlayerScore.objects.bulk_update(scores_to_update, ['score', 'raw_score'])

    return ', '.join([player.name for player in players_needing_update])

@staff_member_required
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

@staff_member_required
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

@staff_member_required
def refresh_games(request):
    username, api_key = get_login()
    client = RAclient(username, api_key)
    response = ''

    challenge_id = get_max_challenge_id()
    games = Game.objects.filter(challenge__id=challenge_id).order_by('retro_game_id')

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
