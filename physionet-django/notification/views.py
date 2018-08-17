from django.shortcuts import render

from .models import News

def news(request):
    news_pieces = News.objects.all().order_by('datetime')
    return render(request, 'notification/news.html',
        {'news_pieces':news_pieces})
