from django.contrib import admin

from .models import Player, Game, Challenge, PlayerScore, Setting

admin.site.register(Player)
admin.site.register(Game)
admin.site.register(Challenge)
admin.site.register(PlayerScore)
admin.site.register(Setting)