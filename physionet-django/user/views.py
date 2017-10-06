from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.template import loader, RequestContext
from django.contrib import auth, messages
from .forms import LoginForm
from django.shortcuts import render
from django.middleware import csrf


# Create your views here.
def login(request):
    user = request.user #Request the user
    if user.is_authenticated():
        return HttpResponseRedirect('/home/')
    if request.method == 'POST':
        form = LoginForm(request.POST) #Assign the information from the post into the form variable
        print dir(form)
        try:
            if form.is_valid():# Check if the content of the form is valid
                form.clean() # Clean the fields in the form.
                user = auth.authenticate(email=form.cleaned_data['email'], password=form.cleaned_data['Password'])#If the content is a post, check it can authenticate
                if user is not None and user.is_active:#If the account is activated and it could be authenticated
                    auth.login(request, user)#Mark the login and redirect home
                    return HttpResponseRedirect('/home/')
            messages.error(request, "Please verify that the Username/Password is correct.", extra_tags='Login Information')
        except Exception as e:
            print "LOGIN EXCEPTION (ERROR) - ", e
            messages.error(request, "Please verify that the Username/Password is correct.", extra_tags='Login Information')
    c = RequestContext(request, {'form': LoginForm(), 'csrf_token': csrf.get_token(request), 'messages':messages.get_messages(request), 'login':1})
    return HttpResponse(loader.get_template('user/login.html').render(c))

def logout(request):
    auth.logout(request)#Force the user to logout
    return HttpResponseRedirect("/")

def dashboard(request):
    user = request.user
    c = RequestContext(request, {'user': request.user, 'messages': messages.get_messages(request)})
    return HttpResponse(loader.get_template('user/home.html').render(c))


def user_home(request):
    pass

def edit(request):
    pass

def reset(request):
    pass

