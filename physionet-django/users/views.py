from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.template import Context, loader, RequestContext
from django.http import HttpResponse, HttpResponseRedirect 
from django.contrib import auth, messages
from .forms import UserForm, LoginForm, RegistrationForm, ResetForm, ResetPassForm
from django.middleware import csrf
from django.core.mail import send_mail
from .models import User, user_action
from uuid import uuid4
from time import strftime

DEFAULT_FROM_EMAIL = 'Physionet Help <ftorres@dev.physionet.org>'
host = 'http://127.0.0.1:8000/' #This is here becuase I use my local computer to test all the things

def index(request):
    user = request.user #Request the user
    if user.is_authenticated():
        return HttpResponseRedirect(user.email)
    else:
        return HttpResponseRedirect('/login')
    return HttpResponse(loader.get_template('users/user.html').render(RequestContext(request, {'user': request.user})))

@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login URL.
def user_home(request):
    user = request.user #Here we get the user information.
    try:
        if user.email != request.path.split('/')[2]:#If the user is not who he says he is, redirect him.
            return HttpResponseRedirect(user.email)
    except:#If the URL path is malformed redirect
        return HttpResponseRedirect(user.email)
    c = RequestContext(request, {'form' : UserForm(instance=user), 'user': user, 'csrf_token': csrf.get_token(request), 'messages': messages.get_messages(request)})
    return HttpResponse(loader.get_template('users/home.html').render(c))

def login(request):
    user = request.user #Request the user
    if user.is_authenticated():
        return HttpResponseRedirect(user.email)
    if request.method == 'POST':
        form = LoginForm(request.POST) #Assign the information from the post into the form variable
        try:
            if form.is_valid():#Check if the content of the form is valid
                user = auth.authenticate(email=request.POST['email'], password=request.POST.get('Password'))#If the content is a post, check it can authenticate
                if user is not None and user.is_active:#If the account is activated and it could be authenticated
                    auth.login(request, user)#Mark the login and redirect home
                    return HttpResponseRedirect(user.email)
                else:
                    messages.add_message(request, messages.INFO, "Please verify that the Username/Password is correct, or, that the account is activated.", extra_tags='Login Information')
                    return HttpResponseRedirect('/login')
            else:
                messages.add_message(request, messages.INFO, "Please verify that the Username/Password is correct.", extra_tags='Login Information')
        except Exception as e:
            messages.add_message(request, messages.INFO, "Please verify that the Username/Password is correct.", extra_tags='Login Information')
    c = RequestContext(request, {'form': LoginForm(), 'csrf_token': csrf.get_token(request), 'messages':messages.get_messages(request), 'login':1})
    return HttpResponse(loader.get_template('users/login.html').render(c))

def logout(request):
    auth.logout(request)#Force the user to logout
    return HttpResponseRedirect("/")

@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login url.
def edit(request):
    user = request.user #Here we get the user information.
    if request.method == 'POST':
        form = UserForm(request.POST, request.FILES, instance=user)#Assign the information from the post into the form variable
        try:
            if form.is_valid():#Check if the content of the form is valid
                form.save()
                instance = User.objects.get(email=user.email)
                if form.cleaned_data['photo']:
                    instance.photo = form.cleaned_data['photo']
                    instance.save()
                return HttpResponseRedirect(user.email)
            else:
                messages.add_message(request, messages.INFO, "There was an error with the information entered, please verify and try again.", extra_tags='Error Submitting')
        except Exception as e:
            messages.add_message(request, messages.INFO, e, extra_tags='Error Submitting')
    try:
        form#If we received the post before, then form will be set
    except:
        form = UserForm(instance=user)#If no post request, then initialize the form
    c = RequestContext(request, {'form': form, 'user': user, 'csrf_token': csrf.get_token(request), 'messages':messages.get_messages(request), 'edit':1})
    return HttpResponse(loader.get_template('users/user.html').render(c))

def register(request):
    user = request.user #Request the user
    if user.is_authenticated():
        return HttpResponseRedirect(user.email)
    if request.method == 'POST':#If we receive a post in the web request
        form = RegistrationForm(request.POST, request.FILES)#Assign the information from the post into the form variable
        if form.is_valid():#Check if the content of the form is valid
            form.save()
            instance = User.objects.get(email=form.cleaned_data['email'])
            if form.cleaned_data['photo']:
                instance.photo = form.cleaned_data['photo']
                instance.save()
            UUID = uuid4()
            Activate = user_action(code=UUID,email=request.POST['email'],action='Activation')#Add the line with the UUID and email to the activation table
            Activate.save()#Save the input
            Message = "An account has been created\n\r please activate the account by clicking or copy pasting the following link in the URL of the web browser\n\r\n\r %sactivate/%s/%s\n\r\n\rThanks!" % (host, str(UUID), request.POST['email'])#Generate the email to be sent
            Subject = "Activate the account"
            send_mail(Subject, Message, DEFAULT_FROM_EMAIL, [request.POST['email']], fail_silently=False)#Send the email
            return HttpResponseRedirect('/login/')
        else:
            print form.errors.as_data(), 1
    try:
        form #= RegistrationForm(request.POST)#Assign the information from the post into the form variable
    except:
        form = RegistrationForm()#If no post request, then initialize the form
    c = RequestContext(request, {'form':form, 'csrf_token': csrf.get_token(request), 'messages': messages.get_messages(request), "register":1})
    return HttpResponse(loader.get_template('users/user.html').render(c))

def activate(request):
    path = request.path.split('/')#Here we split the path to get the UUID and the email to see if the email is activated
    try:#If the EMAIL doesnt exist
        Temp_User = User.objects.get(email=path[3])
    except:#Redirect the user to registration if the EMAIL doesn't exist
        return HttpResponseRedirect('/register/')
    form = LoginForm()#Create the login form
    if not Temp_User.is_active:#If the user is not active, then we check the table for the activation.
        Found = 0#Variable for message to see if the user is found or not
        for line in user_action.objects.all():#From all the lines in the table of activations:
            if str(line.code) == path[2] and str(line.email) == path[3]:#Check if the UUID and the EMAIL are the same as the URL
                Found = 1#If they are the same mark as found
                user_action.objects.get(id=line.id).delete() #Delete the line that was found 
                Person = User.objects.get(email=line.email)#get the user from the database
                Person.is_active = True #Set the user as active
                Person.save()#Save all the changes
                messages.add_message(request, messages.INFO, "The user was activated successfully.", extra_tags='Account Activation')
                return HttpResponseRedirect("/login")
        if Found == 0:
            messages.add_message(request, messages.INFO, "Please verify that the URL was entered properly.", extra_tags='Wrong activation link')
    else:
        messages.add_message(request, messages.INFO, "The user has already been activated.", extra_tags='Account Activated')
    c = RequestContext(request, {'form': form, 'csrf_token': csrf.get_token(request), 'messages': messages.get_messages(request)})
    return HttpResponse(loader.get_template('users/login.html').render(c))

def reset(request):
    user = request.user
    if request.method == 'POST':#If we receive a post in the web request
        form = ResetForm(request.POST) #Assign the information from the post into the form variable
        try:#If the EMAIL doesn't exist
            Temp_User = User.objects.get(email=request.POST['email'])
            UUID = uuid4() #Set a UUID to be sent to the email and added to the activation table
            OLD_UUID = user_action.objects.filter(email=request.POST['email'])#get the user from the database
            for item in OLD_UUID:
                user_action.objects.get(id=item.id).delete()
            Reset = user_action(code=UUID,email=Temp_User,action="Password_Reset")#Add the line with the UUID and email to the activation table
            Reset.save()
            Message = "Password recovery requested.\n\r To change the password please click\n\r\n\r %sreset_password/%s/%s\n\r\n\rThanks!" % (host, str(UUID), request.POST['email'])#Generate the email to be sent
            Subject = "Password Reset"
            send_mail(Subject, Message, DEFAULT_FROM_EMAIL, [Temp_User], fail_silently=False)#Send the email
            messages.add_message(request, messages.INFO, "An email has been sent to the address entered.", extra_tags='Email Sent')
        except:#Redirect the user to registration if the EMAIL doesn't exist
            messages.add_message(request, messages.INFO, "There was an error with he account, please verify the information.", extra_tags='Email Sent')
    else:
        form = ResetForm()
    c = RequestContext(request, {'form': form, 'csrf_token': csrf.get_token(request), 'messages': messages.get_messages(request), 'reset':1})
    return HttpResponse(loader.get_template('users/login.html').render(c))

def reset_password(request):
    path = request.path.split('/')#Here we split the path to get the UUID and the email to see if the email is activated
    try:#If the EMAIL doesn't exist
        Temp_User = User.objects.get(email=path[3])
    except:#Redirect the user to registration if the EMAIL doesn't exist
        messages.add_message(request, messages.INFO, "Please verify that the URL was entered properly.", extra_tags='Wrong link')
        return HttpResponseRedirect('/login/')
    form = LoginForm()#Create the login form
    Found = reset_password = 0
    login = 1
    if Temp_User.is_active: #If the user is not active, then we check the table for the activation.
        for line in user_action.objects.all():#From all the lines in the table of activations:
            if str(line.code) == path[2] and str(line.email) == path[3]:#Check if the UUID and the EMAIL are the same as the URL
                reset_password = Found = 1#If they are the same mark as found
                login = 0
                if request.method == 'POST':
                    form = ResetPassForm(request.POST) #Assign the information from the post into the form variable
                    try:
                        if form.is_valid():
                            Person = User.objects.get(email=line.email)#get the user from the database
                            Person.set_password(request.POST['Password'])#Set the user as active
                            Person.save()#Save all
                            user_action.objects.get(id=line.id).delete()#Delete the line that was found 
                            messages.add_message(request, messages.INFO, "Password changed successfully", extra_tags='Password changed.')
                            return HttpResponseRedirect('/login/')
                    except Exception as e:
                        messages.add_message(request, messages.INFO, "Please verify that the URL was entered properly.", extra_tags='Wrong link')
                        print e
                else:
                    form = ResetPassForm()#Create the login form
                    template=loader.get_template('users/login.html')#Create the template to render
                    storage = messages.get_messages(request)
                    c = RequestContext(request, {'form': form, 'email':path[3], 'uuid':path[2],'csrf_token': csrf.get_token(request), 'messages': storage, 'login':login, 'reset_password':reset_password})
                    return HttpResponse(template.render(c))
    else:
        messages.add_message(request, messages.INFO, "User not found, please register the account or activate the account before resetting the password", extra_tags='User not found or inactive')
    if Found == 0:
        messages.add_message(request, messages.INFO, "Please verify that the URL was entered properly.", extra_tags='Wrong link')
    return HttpResponseRedirect("/login")




