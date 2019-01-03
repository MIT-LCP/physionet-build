from django.shortcuts import render, redirect
from django.utils import timezone

from .models import News


def news(request):
    """
    Redirect to news for current year
    """
    return redirect('news_year', year=timezone.now().year)

def news_year(request, year):
    news_pieces = News.objects.filter(publish_datetime__year=int(year)).order_by('-publish_datetime')
    # The year range of all the PN news in existence.
    # Yes, the start is hardcoded.
    news_years = list(range(2019, timezone.now().year + 1))
    return render(request, 'notification/news.html',
        {'year':year, 'news_pieces':news_pieces, 'news_years':news_years})
