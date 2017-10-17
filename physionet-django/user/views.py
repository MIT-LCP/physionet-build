from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def user_home(request):
    """
    Home page/dashboard for individual users
    """
    return render(request, 'user/user_home.html', {'user':request.user})
