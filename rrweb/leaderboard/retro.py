import sys
import os
import json
from datetime import date
from datetime import datetime
import pytz
import requests
from dateutil.relativedelta import relativedelta
from leaderboard.models import Player, Game, Challenge, PlayerScore, Setting

class _NotReturned:
    '''For when a value isn't returned by the API'''
    def __repr__(self):
        return 'NotReturned'

    def __bool__(self): #so we can use or when there's 2 possible keys
        return False

    def __int__(self):
        return -1

NotReturned = _NotReturned() #that way it's always the same object

def try_key_or_nr(d, k): #tries to return a value, else returns NotReturned
    try:
        return d[k]
    except KeyError:
        return NotReturned

def try_int_key_or_nr(d, k): #tries to return an int value, else returns NotReturned
    try:
        return int(d[k])
    except KeyError:
        return NotReturned

def try_date_key_or_nr(d, k): #tries to return an int value, else returns NotReturned
    try:
        return get_utc_date_from_response_string((d[k]))
    except KeyError:
        return NotReturned

def try_bool_key_or_nr(d, k): #tries to return an int value, else returns NotReturned
    try:
        value = (d[k])
        return True if value == 1 or value == '1' else False
    except KeyError:
        return NotReturned

def get_utc_date_from_response_string(date_string: str):
    return pytz.utc.localize(datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S'))

class Achievement:
    def __init__(self, data: dict):
        self.id = try_int_key_or_nr(data, 'AchievementID')
        self.date = try_date_key_or_nr(data, 'Date')
        self.hardcore = try_bool_key_or_nr(data, 'HardcoreMode')
        self.title = try_key_or_nr(data, 'Title')
        self.description = try_key_or_nr(data, 'Description')
        self.game_title = try_key_or_nr(data, 'GameTitle')
        self.points = try_int_key_or_nr(data, 'Points')
        self.game_id = try_int_key_or_nr(data, 'GameID')

        self.key = f'{self.id}-{self.hardcore}'

    def __lt__(self, other):
         # Define less-than function so sorting works automatically.
         return (self.game_title, self.id, self.hardcore) < (other.game_title, other.id, other.hardcore)

class AchievementsEarnedBetween:
    def __init__(self):
        self.achievements = list()

    def add(self, data: list):
        self.achievements.extend([Achievement(a) for a in data])
        # de-dupe by key while maintaining sort order
        seen = set()
        # set.add() returns None and `not None` is True, so it adds it iff it wasn't already in seen
        distinct = [a for a in self.achievements if a.key not in seen and not seen.add(a.key)] 
        self.achievements = distinct

    def get_progress(self, game_id: int, hardcore: bool = True):
        return sum([a.points for a in self.achievements if a.hardcore == hardcore and a.game_id == game_id])
    
class UserProgress:
    def __init__(self, game_id: int, data: dict):
        '''
        {
        "676": {
            "NumPossibleAchievements": 59,
            "PossibleScore": "509",
            "NumAchieved": 0,
            "ScoreAchieved": 0,
            "NumAchievedHardcore": 0,
            "ScoreAchievedHardcore": 0
        },
        "1451": {
            "NumPossibleAchievements": 84,
            "PossibleScore": "800",
            "NumAchieved": 36,
            "ScoreAchieved": "245",
            "NumAchievedHardcore": 36,
            "ScoreAchievedHardcore": "245"
        },
        '''
        self.game_id = game_id
        self.num_possible = try_int_key_or_nr(data, 'NumPossibleAchievements')
        self.possible_score = try_int_key_or_nr(data, 'PossibleScore')
        self.num_achieved = try_int_key_or_nr(data, 'NumAchieved')
        self.score_achieved = try_int_key_or_nr(data, 'ScoreAchieved')
        self.num_achieved_hardcore = try_int_key_or_nr(data, 'NumAchievedHardcore')
        self.score_achieved_hardcore = try_int_key_or_nr(data, 'ScoreAchievedHardcore')

    def __repr__(self) -> str:
        return f'{self.game_id}: {self.num_achieved_hardcore}'    
    
class Endpoints:
    _api_url = 'https://retroachievements.org/API'
    GetGame = f'{_api_url}/API_GetGame.php'
    GetGameInfoAndUserProgress = f'{_api_url}/API_GetGameInfoAndUserProgress'
    GetUserSummary = f'{_api_url}/API_GetUserSummary.php'
    GetAchievementsEarnedBetween = f'{_api_url}/API_GetAchievementsEarnedBetween.php'
    GetUserProgress = f'{_api_url}/API_GetUserProgress.php'

class RAclient:
    def __init__(self, username: str, api_key: str):
        self.base_params = {
            'z': username,
            'y': api_key
        }

    def make_request(self, endpoint: str, params: dict):
        response = requests.get(endpoint, params | self.base_params)

        if response.status_code == 200:
            data = json.loads(response.text)
            return data
        else:
            raise Exception(f'Request failed with status code {response.status_code}')

    def get_game(self, game_id: int):
        params = {
            'i': game_id
        }
        raw_data = self.make_request(Endpoints.GetGame, params)
        return raw_data
        
    def get_achievements_earned_between(self, player: str, startdate_unix: int, enddate_unix: int):
        # We have to get the data in chunks. 14 days seems to be the max chunk, but we'll do 12 so it's ~3 even chunks
        increment = 12 * 24 * 60 * 60 # 10 days in sec
        start = startdate_unix
        # start_date_s = datetime.utcfromtimestamp(start).strftime('%Y-%m-%d %H:%M:%S')
        data = AchievementsEarnedBetween()

        now_unix = int(datetime.utcnow().timestamp())
        if(now_unix < enddate_unix):
            enddate_unix = now_unix

        while start <= enddate_unix:
            end = start + increment
            # end_date_s = datetime.utcfromtimestamp(end).strftime('%Y-%m-%d %H:%M:%S')
            params = {
                'u': player,
                'f': start,
                't': end
            }
            raw_data = self.make_request(Endpoints.GetAchievementsEarnedBetween, params)
            data.add(raw_data)
            if len(raw_data) >= 500:
                # The next `start` needs to be the last date found in the response since the API is count-limited to 500
                max_date = max(item['Date'] for item in raw_data)
                converted_max_date = get_utc_date_from_response_string(max_date)
                converted_max_date_ts = converted_max_date.timestamp()
                start = int(converted_max_date_ts) + 1
                # start_date_s = datetime.utcfromtimestamp(start).strftime('%Y-%m-%d %H:%M:%S')
            else:
                # since we didn't hit the 500 record limit, set start = end + 1
                start = end + 1

        return data
    
    def get_user_progress(self, player: str, game_ids: list[int]):
        params = {
            'u': player,
            'i': ",".join(game_ids)
        }
        print(params['i'])
        raw_data = self.make_request(Endpoints.GetUserProgress, params)
        return [UserProgress(int(k), v) for (k, v) in raw_data]

def leaderboard(client: RAclient, players: list, game_ids: list, start_unix_time: int, end_unix_time: int):    
    leaderboard = {player: 0 for player in players}

    start, end = start_unix_time, end_unix_time

    local_tz = pytz.timezone('US/Eastern')
    start_date = pytz.utc.localize(datetime.utcfromtimestamp(start)).astimezone(local_tz)
    end_date = pytz.utc.localize(datetime.utcfromtimestamp(end)).astimezone(local_tz)

    print(f'Getting achievments between \n\
{start_date.strftime("%Y-%m-%d %H:%M:%S")} EST and \n\
{end_date.strftime("%Y-%m-%d %H:%M:%S")} EST \n\
for games: {game_ids} \n\
for players: {players}"')

    for player in players:
        data = client.get_achievements_earned_between(player, start, end)

        for game_id in game_ids:
            progress = data.get_progress(game_id)
            print(f'{player}, {game_id}: {progress}')
            leaderboard[player] += progress
        print()

    for player in sorted(((v,k) for k,v in leaderboard.items()), reverse=True):
        print(f'{player[1]} ({player[0]})')

def get_login():
    username = Setting.objects.filter(name='username')[0].value
    api_key = Setting.objects.filter(name='api_key')[0].value
    return (username, api_key)

if __name__ == '__main__':
    username, api_key = get_login()
    client = RAclient(username, api_key)
    data = client.get_user_progress('monozaki', [676,710,1451,2826,3585,11264,11283,11329])
    for progress in data:
        print(progress)


    
    