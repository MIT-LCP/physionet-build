from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Min, Max
from django.views.decorators.http import require_POST

from notification.models import News, Notification


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
    if year < 1999 or year > date.today().year:
        return redirect('news')

    news_pieces = News.objects.filter(publish_datetime__year=int(year)) \
                              .order_by('-publish_datetime')

    minmax = News.objects.all().aggregate(min=Min('publish_datetime'),
                                          max=Max('publish_datetime'))
    news_years = list(range(minmax['max'].year, minmax['min'].year-1, -1))
    return render(request, 'notification/news.html',
                  {'year': year, 'news_pieces': news_pieces,
                   'news_years': news_years})


def news_by_slug(request, news_slug, max_items=20):
    """
    Get a specific news item
    """
    try:
        news = News.objects.get(slug=news_slug)
        # The year range of all the PN news in existence.
        minmax = News.objects.all().aggregate(min=Min('publish_datetime'),
                                              max=Max('publish_datetime'))
        news_years = list(range(minmax['max'].year, minmax['min'].year-1, -1))

        return render(request, 'notification/news_item.html', {'news': news,
          'news_years': news_years})
    except News.DoesNotExist:
        raise Http404()


def news_rss(request, max_items=100):
    news_pieces = News.objects.order_by('-publish_datetime')[:max_items]
    feed_date = news_pieces[0].publish_datetime
    return render(request, 'notification/news_rss.xml',
                  {'feed_date': feed_date, 'news_pieces': news_pieces},
                  content_type='text/xml; charset=UTF-8')


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    paginator = Paginator(notifications, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'notification/notifications.html', {
        'page_obj': page_obj,
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification, id=notification_id, recipient=request.user
    )
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    if notification.url:
        return redirect(notification.url)
    return redirect('notification_list')


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)
    return redirect('notification_list')


@login_required
def unread_count(request):
    count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return JsonResponse({'unread_count': count})
