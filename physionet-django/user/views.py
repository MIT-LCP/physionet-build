from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import inlineformset_factory, HiddenInput
from django.http import HttpResponseRedirect
from django.middleware import csrf
from django.shortcuts import render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .forms import AssociatedEmailForm, EmailChoiceForm, EmailForm, ProfileForm, UserCreationForm
from .models import AssociatedEmail, Profile, User


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

    return render(request, 'user/register.html', {'form':form, 'csrf_token': csrf.get_token(request)})


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
            messages.success(request, 'Your profile has been updated.')
        else:
            messages.error(request, 'There was an error with the information entered, please verify and try again.')
    return render(request, 'user/edit_profile.html', {'user':user, 'form':form,
        'csrf_token':csrf.get_token(request), 'messages':messages.get_messages(request)})


@login_required
def edit_password_done(request):
    """
    After password has successfully been changed. Need this view because we
    can't control the edit password view to show a success message.
    """
    return render(request, 'user/edit_password_done.html')


@login_required
def edit_emails(request):
    """
    Edit emails page
    """
    user = request.user
    # Email forms to display
    AssociatedEmailsFormset = inlineformset_factory(User, AssociatedEmail,
        fields=('email','is_primary_email', 'is_public'), extra=0)
    associated_emails_formset = AssociatedEmailsFormset(instance=user,
        queryset=AssociatedEmail.objects.filter(verification_date__isnull=False))
    PublicAssociatedEmailsFormset = inlineformset_factory(User, AssociatedEmail,
        fields=('email','is_public'), extra=0, widgets={'email': HiddenInput})
    public_associated_emails_formset = PublicAssociatedEmailsFormset(instance=user,
        queryset=AssociatedEmail.objects.filter(verification_date__isnull=False))
    primary_email_form = EmailChoiceForm(label='Primary Email')
    primary_email_form.get_associated_emails(user=user)
    add_email_form = AssociatedEmailForm()
    remove_email_form = EmailChoiceForm(label='Remove Email')
    remove_email_form.get_associated_emails(user=user, include_primary=False)

    if request.method == 'POST':
        if 'set_public_emails' in request.POST:
            formset = PublicAssociatedEmailsFormset(request.POST, instance=user)
            if formset.is_valid():
                formset.save()
                messages.success(request, 'Your email privacy settings have been updated.')

        elif 'set_primary_email' in request.POST:
            form = EmailForm(request.POST)
            if form.is_valid():
                email = form.cleaned_data['email']
                associated_email = AssociatedEmail.objects.get(email=email)
                if associated_email.user == user and not associated_email.is_primary_email:
                    user.email = email
                    user.save(update_fields=['email'])
                    # Reload primary email select form to make the new primary the default selection
                    primary_email_form.get_associated_emails(user=user)
                    messages.success(request, 'Your email: %s has been set as your new primary email.' % email)

        elif 'add_email' in request.POST:
            form = AssociatedEmailForm(request.POST)
            if form.is_valid():
                email = AssociatedEmail.objects.create(user=user, email=form.cleaned_data['email'])
                # Send an email to the newly added email with a verification link
                uidb64 = urlsafe_base64_encode(force_bytes(email.pk))
                token = default_token_generator.make_token(user)
                subject = "PhysioNet Email Verification"
                context = {'name':user.get_full_name(),
                    'domain':get_current_site(request), 'uidb64':uidb64, 'token':token}
                body = loader.render_to_string('user/email/verify_email_email.html', context)
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                    [form.cleaned_data['email']], fail_silently=False)
                messages.success(request, 'A verification link has been sent to: %s' % email)
                
        elif 'remove_email' in request.POST:
            form = EmailForm(request.POST)
            if form.is_valid():
                email = form.cleaned_data['email']
                remove_email = AssociatedEmail.objects.get(email=email)
                if remove_email.user == user and not remove_email.is_primary_email:
                    remove_email.delete()
                    messages.success(request, 'Your email: %s has been removed from your account.' % email)

    context = {'associated_emails_formset':associated_emails_formset,
        'public_associated_emails_formset':public_associated_emails_formset,
        'primary_email_form':primary_email_form,
        'add_email_form':add_email_form, 'remove_email_form':remove_email_form}

    context['messages'] = messages.get_messages(request)

    return render(request, 'user/edit_emails.html', context)


def verify_email(request, uidb64, token):
    """
    Page to verify an email
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        email = AssociatedEmail.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, AssociatedEmail.DoesNotExist):
        email = None

    if email is not None:
        # Test the token with the user
        user = email.user
        if default_token_generator.check_token(user, token):
            email.verification_date = timezone.now()
            email.save()
            return render(request, 'user/verify_email.html', {'title':'Verification Successful', 'isvalid':True})

    return render(request, 'user/verify_email.html', {'title':'Invalid Verification Link', 'isvalid':False})


def public_profile(request, email):
    """
    A user's public profile
    """
    return render(request, 'user/public_profile.html', {'email':email})
