from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.middleware import csrf
from django.shortcuts import render
from django.urls import reverse


from .forms import UserCreationForm

@login_required
def user_home(request):
    """
    Home page/dashboard for individual users
    """
    return render(request, 'user/user_home.html', {'user':request.user})

def register(request):
    """
    User registration page
    """
    user = request.user
    if user.is_authenticated():
        return HttpResponseRedirect(reverse('userhome'))

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            # Create the new user (triggers profile creation)
            user = form.save()
            # 

            # To do: send the activation email

            return register_done(request, email=user.email)
    else:
        form = UserCreationForm()

    return render(request, 'user/register.html', {'form':form, 'csrf_token': csrf.get_token(request)})


def register_done(request, email):
    """
    Page shown after registration is complete
    """
    return render(request, 'user/register_done.html', {'email':email})