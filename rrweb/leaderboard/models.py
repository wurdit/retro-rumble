from django.db import models

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class Player(models.Model):
    name = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name}, {self.is_active}'

class Challenge(models.Model):
    start = models.IntegerField()
    end = models.IntegerField()

    def __str__(self):
        return f'{self.id}, {self.start} to {self.end}'

class Game(models.Model):
    retro_game_id = models.IntegerField(unique=True)
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    image_icon = models.CharField(max_length=50, null=True)
    game_icon = models.CharField(max_length=50, null=True)
    image_title = models.CharField(max_length=50, null=True)
    image_ingame = models.CharField(max_length=50, null=True)
    image_box_art = models.CharField(max_length=50, null=True)
    # max_score maybe for showing NN/MM

    def __str__(self):
        return f'{self.id}, {self.name}, Challenge: {self.challenge}'

class PlayerScore(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    raw_score = models.IntegerField(default=0)

    def __str__(self):
        return f'{self.player.name}, {self.game.name}: {self.score}'
    
class Setting(models.Model):
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100)

    def __str__(self):
        return f'{self.name}: {self.value if self.name != "api_key" else "xxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
    
class Achievement(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    achievement_id = models.IntegerField()
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=500)
    date = models.DateTimeField()
    hardcore = models.BooleanField()
    points = models.IntegerField()

    def __str__(self) -> str:
        return f'{self.achievement_id}: {self.date.strftime(DATE_FORMAT)}, {self.points} {"(Hardcore)" if self.hardcore else ""}'
