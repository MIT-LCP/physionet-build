from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.middleware import csrf
from django.shortcuts import render
from django.template import loader
from django.urls import reverse
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

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
            user.is_active = False
            user.save()
            # Send an email with the activation link
            uid = urlsafe_base64_encode(force_bytes(user.pk)).decode('utf-8')
            token = default_token_generator.make_token(user)
            subject = "PhysioNet Account Activation"
            context = {'name':user.get_full_name(),
                'site_name':get_current_site(request),
                'activation_url':'http://{0}/activate/{1}/{2}/'.format(request.META['HTTP_HOST'], uid, token)}
            body = loader.render_to_string('user/register_email.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, 
                [form.cleaned_data['email']], fail_silently=False)

            # Registration successful
            return render(request, 'user/register_done.html', {'email':user.email})
    else:
        form = UserCreationForm()

    return render(request, 'user/register.html', {'form':form, 'csrf_token': csrf.get_token(request)})


def activate_user(request, *args, **kwargs):
    """
    Page to active the account of a newly registered user.
    """
    try:
        user = User.objects.get(pk=force_text(urlsafe_base64_decode(kwargs['uidb64'])))
        if default_token_generator.check_token(user, kwargs['token']):
            user.is_active = True
            user.save()
            messages.info(request, 'Your account has been activated, to login click below.')
        else:
            messages.error(request, 'There was an error with your link. Please try again or contact the site administrator.')
    except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
        user = None
        messages.error(request, 'There was an error with your link. Please try again or contact the site administrator.')

    return render(request, 'user/activate.html', {'messages': messages.get_messages(request)})


@login_required
def user_settings(request):
    """
    Settings. Redirect to default - settings/profile
    Don't call this 'settings' because there's an import called 'settings'
    """
    return HttpResponseRedirect(reverse('edit_profile'))


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
        form = ProfileForm(request.POST, instance=user.profile)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, 'There was an error with the information entered, please verify and try again.')
    return render(request, 'user/edit_profile.html', {'user':user, 'form':form,
        'csrf_token':csrf.get_token(request), 'messages':messages.get_messages(request)})


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
