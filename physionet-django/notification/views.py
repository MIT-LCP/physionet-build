from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Min, Max

from .models import News


def news(request):
    """
    Redirect to news for current year
    """
    news_pieces = News.objects.order_by('-publish_datetime')

    # The year range of all the PN news in existence.
    minmax = News.objects.all().aggregate(min=Min('publish_datetime'), max=Max('publish_datetime'))
    news_years = list(range(minmax['min'].year, minmax['max'].year+1))
    return render(request, 'notification/news.html',
        {'year':'All', 'news_pieces':news_pieces, 'news_years':news_years})

def news_year(request, year):
    news_pieces = News.objects.filter(publish_datetime__year=int(year)).order_by('-publish_datetime')
    # The year range of all the PN news in existence.
    # Yes, the start is hardcoded.
    minmax = News.objects.all().aggregate(min=Min('publish_datetime'), max=Max('publish_datetime'))
    news_years = list(range(minmax['min'].year, minmax['max'].year+1))
    return render(request, 'notification/news.html',
        {'year':year, 'news_pieces':news_pieces, 'news_years':news_years})
