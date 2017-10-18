from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib.auth.decorators import login_required
from django.utils.encoding import force_bytes, force_text
from .forms import UserCreationForm, ProfileForm
from django.shortcuts import render, resolve_url
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.core.mail import send_mail
from django.contrib import messages
from django.middleware import csrf
from .models import User, Profile
from django.conf import settings
from django.urls import reverse

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
            user    = form.save()
            uid     = urlsafe_base64_encode(force_bytes(user.pk))
            token   = default_token_generator.make_token(user)
            Subject = "Activate the account"
            Message = """An account has been created\n\r please activate the 
            account by clicking or copy pasting the following link in the URL of
             the web browser\n\r\n\r http://{0}/activate/{1}/{2}\n\r\n\rThanks!""".format(request.META['HTTP_HOST'], uid, token)
            send_mail(Subject, Message, settings.DEFAULT_FROM_EMAIL, 
                [request.POST['email']], fail_silently=False)
            # To do: send the activation email

            return register_done(request, email=user.email)
    else:
        form = UserCreationForm()

    return render(request, 'user/register.html', {'form':form, 'csrf_token': csrf.get_token(request)})


def register_done(request, email):
    """
    Page shown after registration is complete.
    """
    return render(request, 'user/register_done.html', {'email':email})

def activate_user(request, *args, **kwargs):
    """
    Page to active a newly registered user.
    """
    try: # Get the UID created from the user pk 
        user = User.objects.get(pk=force_text(urlsafe_base64_decode(kwargs['uidb64'])))
        if default_token_generator.check_token(user, kwargs['token']):
            user.is_active = True
            user.save()
            messages.info(request, 'Your account has been activated, to login click below.')
        else:
            messages.error(request, 'There was an error with your link, please try again or contact the site administrator.')
    except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
        user = None
        messages.error(request, 'There was an error with your link, please try again or contact the site administrator.')

    return render(request, 'user/registration_complete.html', {'messages': messages.get_messages(request)})


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
