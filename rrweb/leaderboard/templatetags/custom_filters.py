from django import template

register = template.Library()

@register.filter
def sum_scores(scores):
    return sum([score.score for score in scores])

@register.filter
def score_or_blank(score):
    return score if score > 0 else ''