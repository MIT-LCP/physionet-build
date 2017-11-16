from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import inlineformset_factory, HiddenInput
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .forms import AssociatedEmailForm, AssociatedEmailChoiceForm, ProfileForm, UserCreationForm
from .models import AssociatedEmail, Profile, User

import pdb
def activate_user(request, uidb64, token):
    """
    Page to active the account of a newly registered user.
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and not user.is_active and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        email = user.associated_emails.first()
        email.verification_date = timezone.now()
        email.save()
        context = {'title':'Activation Successful', 'isvalid':True}
    else:
        context = {'title':'Invalid Activation Link', 'isvalid':False}

    return render(request, 'user/activate_user.html', context)


# Helper functions for edit_emails view
def set_public_emails(request, formset):
    "Set public/private status of associated emails"
    if formset.is_valid():
        formset.save()
        messages.success(request, 'Your email privacy settings have been updated.')

def set_primary_email(request, primary_email_form):
    "Set the selected email as the primary email"
    user = request.user
    if primary_email_form.is_valid():
        associated_email = primary_email_form.cleaned_data['associated_email']
        # Only do something if they selected a different email
        if associated_email.email != user.email:
            user.email = associated_email.email
            user.save(update_fields=['email'])
            messages.success(request, 'Your email: %s has been set as your new primary email.' % user.email)

def add_email(request, add_email_form):
    user = request.user
    if add_email_form.is_valid():
        associated_email = AssociatedEmail.objects.create(user=user,
            email=add_email_form.cleaned_data['email'])
        # Send an email to the newly added email with a verification link
        uidb64 = urlsafe_base64_encode(force_bytes(associated_email.pk))
        token = default_token_generator.make_token(user)
        subject = "PhysioNet Email Verification"
        context = {'name':user.get_full_name(),
            'domain':get_current_site(request), 'uidb64':uidb64, 'token':token}
        body = loader.render_to_string('user/email/verify_email_email.html', context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
            [add_email_form.cleaned_data['email']], fail_silently=False)
        messages.success(request, 'A verification link has been sent to: %s' % associated_email.email)

def remove_email(request, remove_email_form):
    "Remove a non-primary email associated with a user"
    user = request.user
    if remove_email_form.is_valid():
        associated_email = remove_email_form.cleaned_data['associated_email']
        associated_email.delete()
        messages.success(request, 'Your email: %s has been removed from your account.' % user.email)

@login_required
def edit_emails(request):
    """
    Edit emails page
    """
    user = request.user
    # Email forms to display
    AssociatedEmailFormset = inlineformset_factory(User, AssociatedEmail,
        fields=('email','is_primary_email', 'is_public'), extra=0, max_num=3,
        widgets={'email': HiddenInput, 'is_primary_email':HiddenInput})
    associated_email_formset = AssociatedEmailFormset(instance=user,
        queryset=AssociatedEmail.objects.filter(verification_date__isnull=False))
    primary_email_form = AssociatedEmailChoiceForm(user=user, include_primary=True)
    add_email_form = AssociatedEmailForm()
    remove_email_form = AssociatedEmailChoiceForm(user=user, include_primary=False)

    if request.method == 'POST':
        if 'set_public_emails' in request.POST:
            formset = AssociatedEmailFormset(request.POST, instance=user)
            set_public_emails(request, formset)

        elif 'set_primary_email' in request.POST:
            primary_email_form = AssociatedEmailChoiceForm(user=user,
                include_primary=True, data=request.POST)
            set_primary_email(request, primary_email_form)

        elif 'add_email' in request.POST:
            add_email_form = AssociatedEmailForm(request.POST)
            add_email(request, add_email_form)
                
        elif 'remove_email' in request.POST:
            remove_email_form = AssociatedEmailChoiceForm(user=user,
                include_primary=False, data=request.POST)
            remove_email(request, remove_email_form)

    context = {'associated_email_formset':associated_email_formset,
        'primary_email_form':primary_email_form,
        'add_email_form':add_email_form, 'remove_email_form':remove_email_form}

    context['messages'] = messages.get_messages(request)

    return render(request, 'user/edit_emails.html', context)


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
            messages.success(request, 'Your profile has been updated.')
        else:
            messages.error(request,
                'There was an error with the information entered, please verify and try again.')
    return render(request, 'user/edit_profile.html', {'user':user, 'form':form,
        'messages':messages.get_messages(request)})


@login_required
def edit_password_done(request):
    """
    After password has successfully been changed. Need this view because we
    can't control the edit password view to show a success message.
    """
    return render(request, 'user/edit_password_done.html')


def public_profile(request, email):
    """
    A user's public profile
    """
    return render(request, 'user/public_profile.html', {'email':email})


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
            # Create the new user
            user = form.save()
            # Send an email with the activation link
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            subject = "PhysioNet Account Activation"
            context = {'name':user.get_full_name(),
                'domain':get_current_site(request), 'uidb64':uidb64, 'token':token}
            body = loader.render_to_string('user/email/register_email.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, 
                [form.cleaned_data['email']], fail_silently=False)

            # Registration successful
            return render(request, 'user/register_done.html', {'email':user.email})
    else:
        form = UserCreationForm()

    return render(request, 'user/register.html', {'form':form})


@login_required
def user_home(request):
    """
    Home page/dashboard for individual users
    """
    return render(request, 'user/user_home.html', {'user':request.user})


@login_required
def user_settings(request):
    """
    Settings. Redirect to default - settings/profile
    Don't call this 'settings' because there's an import called 'settings'
    """
    return HttpResponseRedirect(reverse('edit_profile'))


def verify_email(request, uidb64, token):
    """
    Page to verify an associated email
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        associated_email = AssociatedEmail.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, AssociatedEmail.DoesNotExist):
        associated_email = None

    if associated_email is not None:
        # Test the token with the user
        user = associated_email.user
        if default_token_generator.check_token(user, token):
            associated_email.verification_date = timezone.now()
            associated_email.save()
            return render(request, 'user/verify_email.html',
                {'title':'Verification Successful', 'isvalid':True})

    return render(request, 'user/verify_email.html',
        {'title':'Invalid Verification Link', 'isvalid':False})


# def test(request):
#     """
#     For testing
#     """
#     user = request.user
#     primary_email_form = AssociatedEmailChoiceForm(label='Primary Email')
#     primary_email_form.get_associated_emails(user=user)

#     if request.method == 'POST':
#         form = AssociatedEmailChoiceForm(request.POST)

#         pdb.set_trace()

#     return render(request,'user/test.html', {'user':user,
#         'form':primary_email_form, 'csrf_token': csrf.get_token(request)})
