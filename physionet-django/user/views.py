from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.middleware import csrf
from django.shortcuts import render
from django.urls import reverse

from .forms import UserCreationForm, ProfileForm
from .models import User, Profile

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
        return HttpResponseRedirect(reverse('user_home'))

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


def reset_password(request):
    """
    Placeholder to clean up templates. Please replace when ready!
    """
    pass


@login_required
def edit_profile(request):
    """
    Edit the profile fields
    """
    user = request.user
    form = ProfileForm(instance=user.profile)

    if request.method == 'POST':
        # Update the profile and return to the same page. Place a message
        # at the top of the page: 'your profile has been updated'
        pass
    else:
        return render(request, 'user/edit_profile.html',
            {'user':user, 'form':form,
             'csrf_token':csrf.get_token(request)})


@login_required
def edit_password(request):
    """
    Edit password page
    """
    user = request.user
    pass


@login_required
def edit_emails(request):
    """
    Edit emails page
    """
    pass


def public_profile(request, email):
    """
    Placeholder to clean up templates. Please replace when ready!
    """
    return render(request, 'user/public_profile.html', {'email':email})