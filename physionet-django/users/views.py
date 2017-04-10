from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.template import Context, loader, RequestContext
from django.http import HttpResponse, HttpResponseRedirect 
from django.contrib import auth, messages
from .forms import UserForm, LoginForm, RegistrationForm
from django.middleware import csrf
from .models import User, user_action
from uuid import uuid4

# @login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login URL.
def index(request):
    template = loader.get_template("users/user.html")
    return HttpResponse(template.render())

def handle_uploaded_file(file, email):
    import os
    if not os.path.exists('media/Users/' + email + '/'):
        os.makedirs('media/Users/' + email + '/')
    with open('media/Users/' + email + '/'+ email + '.' + file.name.split('.')[-1], 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login URL.
def user_home(request):
    try:#If the EMAIL doesn't exist
        Temp_User = User.objects.get(email=request.path.split('/')[2])
        if request.user.email != Temp_User.email:
            return HttpResponseRedirect('/home/' + request.user.email)
    except:#Redirect the user to registration if the EMAIL doesn't exist
        return HttpResponseRedirect('/home/' + request.user.email)
    user = request.user #Here we get the user information.
    storage = messages.get_messages(request)
    template = loader.get_template('users/home.html')#args['form']
    c = RequestContext(request, {'form':UserForm(instance=user), 'user': user, 'csrf_token': csrf.get_token(request), 'messages': storage})
    return HttpResponse(template.render(c))

def login(request):
    user = request.user #Request the user
    if user.is_authenticated():
        return HttpResponseRedirect('/home/' + user.email)
    if request.method == 'POST':
        form = LoginForm(request.POST) #Assign the information from the post into the form variable
        try:
            if form.is_valid():#Check if the content of the form is valid
                print "IS VALID"
                user = auth.authenticate(email=request.POST['email'], password=request.POST.get('Password'))#If the content is a post, check it can authenticate
                if user is not None and user.is_active:#If the account is activated and it could be authenticated
                    auth.login(request, user)#Mark the login and redirect home
                    return HttpResponseRedirect('/home/' + user.email)
                else:
                    messages.add_message(request, messages.INFO, "Please verify that the Username/Password is correct, or, that the account is activated.", extra_tags='Login Information')
                    return HttpResponseRedirect('/login')
            else:
                print valid, error
                messages.add_message(request, messages.INFO, "ePlease verify that the Username/Password is correct.", extra_tags='Login Information')
        except Exception as e:
            messages.add_message(request, messages.INFO, "Please verify that the Username/Password is correct.", extra_tags='Login Information')
    form = LoginForm()
    template = loader.get_template('users/login.html')
    storage = messages.get_messages(request)
    c = RequestContext(request, {'form': form, 'csrf_token': csrf.get_token(request), 'messages':storage, 'login':1})
    return HttpResponse(template.render(c))

def logout(request):
    auth.logout(request)#Force the user to logout
    return HttpResponseRedirect("/")

@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login url.
def edit(request):
    user = request.user #Here we get the user information.
    if request.method == 'POST':
        form = UserForm(request.POST, request.FILES, instance=request.user)#Assign the information from the post into the form variable
        try:
            if form.is_valid():#Check if the content of the form is valid
                if request.FILES:
                    if request.FILES['photo']:
                        handle_uploaded_file(request.FILES['photo'], user.email)
                form.save()
                return HttpResponseRedirect("/home/" + user.email)
            else:
                messages.add_message(request, messages.INFO, "There was an error with the information entered, please verify and try again.", extra_tags='Error Submitting')
        except Exception as e:
            messages.add_message(request, messages.INFO, "There was an error with the information entered, please verify and try again.", extra_tags='Error Submitting')
    try:
        form#If we received the post before, then form will be set
    except:
        form = UserForm(instance=user)#If no post request, then initialize the form
    template = loader.get_template('users/user.html')
    storage = messages.get_messages(request)
    c = RequestContext(request, {'form': form, 'user': user, 'csrf_token': csrf.get_token(request), 'messages':storage, 'edit':1})
    return HttpResponse(template.render(c))

def register(request):
    user = request.user
    if request.method == 'POST':#If we receive a post in the web request
        form = RegistrationForm(request.POST)#Assign the information from the post into the form variable
        if form.is_valid():#If the form is valid it means it passed the checks
            form.save()#Save the user in the database
            UUID = uuid4()#Set a UUID to be sent to the email and added to the activation table
            Activate = user_action(activation_code=UUID,email=request.POST['email'],action='Activation')#Add the line with the UUID and email to the activation table
            Activate.save()#Save the input
            Message = "An account has been created\n\r please activate the account by clicking or copy pasting the following link in the URL of the web browser\n\r\n\r %s%s/%s\n\r\n\rThanks!" % (host, str(UUID), request.POST['email'])#Generate the email to be sent
            Subject = "Activate the account"
            send_mail(Subject, Message, DEFAULT_FROM_EMAIL, [request.POST['email']], fail_silently=False)#Send the email
        else:
            print "*** Form is invalid ***"
            print form.errors.as_data(), 1
    args = {}#Variable to get all the arguments and not have to fill the form again.
    template = loader.get_template('users/user.html')
    storage = messages.get_messages(request)
    try:
        args['form'] = form#If we received the post before, then form will be set
    except:
        args['form'] = RegistrationForm()#If no post request, then initialize the form
    c = RequestContext(request, {'form':args['form'], 'csrf_token': csrf.get_token(request), 'messages': storage, "register":True})
    return HttpResponse(template.render(c))

###

def activate(request):
    template = loader.get_template("users/register.html")
    return HttpResponse(template.render())


def reset_password(request):
    template = loader.get_template("users/register.html")
    return HttpResponse(template.render())


