from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Min, Max

from .models import News

from datetime import date

def news(request, max_items=20):
    """
    Redirect to news for current year
    """
    news_pieces = News.objects.order_by('-publish_datetime')[:max_items]

    # The year range of all the PN news in existence.
    minmax = News.objects.all().aggregate(min=Min('publish_datetime'),
                                          max=Max('publish_datetime'))
    if news_pieces:
        news_years = list(range(minmax['max'].year, minmax['min'].year-1, -1))
    else:
        news_years = news_pieces

    return render(request, 'notification/news.html',
                  {'year': 'Latest', 'news_pieces': news_pieces,
                   'news_years': news_years})


def news_year(request, year):
    """
    Get all the news of a specific year
    """
    if int(year) < 1999 or int(year) > date.today().year:
        return redirect('news')

    news_pieces = News.objects.filter(publish_datetime__year=int(year)) \
                              .order_by('-publish_datetime')

    minmax = News.objects.all().aggregate(min=Min('publish_datetime'),
                                          max=Max('publish_datetime'))
    news_years = list(range(minmax['max'].year, minmax['min'].year-1, -1))
    return render(request, 'notification/news.html',
                  {'year': year, 'news_pieces': news_pieces,
                   'news_years': news_years})


def news_rss(request, max_items=100):
    news_pieces = News.objects.order_by('-publish_datetime')[:max_items]
    feed_date = news_pieces[0].publish_datetime
    return render(request, 'notification/news_rss.xml',
                  {'feed_date': feed_date, 'news_pieces': news_pieces},
                  content_type='text/xml; charset=UTF-8')
