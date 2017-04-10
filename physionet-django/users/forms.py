from django.forms import *
import re
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django import forms
from .models import User
from urllib import urlopen
# from bootstrap.forms import BootstrapForm
from django.core.validators import MaxValueValidator, MinValueValidator
from django.forms.extras.widgets import SelectDateWidget
import re
from operator import itemgetter

CONTIGUOUS_STATES = (('N/A','       '), ('AL', 'Alabama'), ('AZ', 'Arizona'), ('AR', 'Arkansas'), ('CA', 'California'), ('CO', 'Colorado'), ('CT', 'Connecticut'), ('DE', 'Delaware'), ('DC', 'District of Columbia'), ('FL', 'Florida'), ('GA', 'Georgia'), ('ID', 'Idaho'), ('IL', 'Illinois'), ('IN', 'Indiana'), ('IA', 'Iowa'), ('KS', 'Kansas'), ('KY', 'Kentucky'), ('LA', 'Louisiana'), ('ME', 'Maine'), ('MD', 'Maryland'), ('MA', 'Massachusetts'), ('MI', 'Michigan'), ('MN', 'Minnesota'), ('MS', 'Mississippi'), ('MO', 'Missouri'), ('MT', 'Montana'), ('NE', 'Nebraska'), ('NV', 'Nevada'), ('NH', 'New Hampshire'), ('NJ', 'New Jersey'), ('NM', 'New Mexico'), ('NY', 'New York'), ('NC', 'North Carolina'), ('ND', 'North Dakota'), ('OH', 'Ohio'), ('OK', 'Oklahoma'), ('OR', 'Oregon'), ('PA', 'Pennsylvania'), ('RI', 'Rhode Island'), ('SC', 'South Carolina'), ('SD', 'South Dakota'), ('TN', 'Tennessee'), ('TX', 'Texas'), ('UT', 'Utah'), ('VT', 'Vermont'), ('VA', 'Virginia'), ('WA', 'Washington'), ('WV', 'West Virginia'), ('WI', 'Wisconsin'), ('WY', 'Wyoming'))
NON_CONTIGUOUS_STATES = (('AK', 'Alaska'), ('HI', 'Hawaii'))
US_TERRITORIES = (('AS', 'American Samoa'), ('GU', 'Guam'), ('MP', 'Northern Mariana Islands'), ('PR', 'Puerto Rico'), ('VI', 'Virgin Islands'))
USA = sorted(CONTIGUOUS_STATES + NON_CONTIGUOUS_STATES + US_TERRITORIES, key=itemgetter(1))

class BaseUserForm():
    def clean_2_password(self):
        if 'Password2' in self.cleaned_data and 'Password' in self.cleaned_data:
            Password=self.cleaned_data['Password']
            Password2=self.cleaned_data['Password2']
            if (Password == "" and Password2 == "") or (Password == None and Password2 == None):
                return Password
            if Password != Password2:
                raise ValidationError({'Password': ["The passwords do not match.",], 'Password2': ["The passwords do not match.",]})
            if len(Password) < 8:
                raise ValidationError({'Password': ["The password is too short.",], 'Password2': ["The password is too short.",]})
            if len(Password) > 15:
                raise ValidationError({'Password': ["The password is too long, it cannot have more than 15 characters.",], 'Password2': ["The password is too long, it cannot have more than 15 characters.",]})
            if not bool(re.search(r'\d', Password)):
                raise ValidationError({'Password': ["The password must contain at least 1 digit.",], 'Password2': ["The password must contain at least 1 digit.",]})
            if not bool(re.search(r'[a-zA-Z]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 letter.",], 'Password2': ["Password must contain at least 1 letter.",]})
            if not bool(re.search(r'[~!@#$%.&?^*]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *",], 'Password2': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *.",]})
            if Password.isupper() or Password.islower():
                raise ValidationError({'Password': ["The password must contain upper and lower case letters.",], 'Password2': ["The password must contain upper and lower case letters.",]})
            return Password

    def clean_password(self):
        if 'Password' in self.cleaned_data:
            Password = self.cleaned_data['Password']
            if len(Password) < 8:
                raise ValidationError({'Password': ["The password is too short.",]})
            if len(Password) > 15:
                raise ValidationError({'Password': ["The password is too long, it cannot have more than 15 characters.",]})
            if not bool(re.search(r'\d', Password)):
                raise ValidationError({'Password': ["The password must contain at least 1 digit.",]})
            if not bool(re.search(r'[a-zA-Z]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 letter.",]})
            if not bool(re.search(r'[~!@#$.%&?^*]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *",]})
            if Password.isupper() or Password.islower():
                raise ValidationError({'Password': ["The password must contain upper and lower case letters.",]})
            return Password
        else:
            return None

    def clean_new_email(self):
        if 'email' in self.cleaned_data:
            email = self.cleaned_data['email']
            Exists = True
            try:
                User.objects.get(email=email)
            except ObjectDoesNotExist:
                Exists = False
            if Exists:
                raise forms.ValidationError({'email': ['The email is already registered.',]})
            if not re.match(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', email):
                raise forms.ValidationError({'email': ['Invalid email.',]})
            return email

    def clean_logged_email(self):
        if 'email' in self.cleaned_data:
            Email = self.cleaned_data['email']
            Exists = True
            try:
                User.objects.get(email=Email)
            except ObjectDoesNotExist:
                Exists = False
            if not Exists:
                raise forms.ValidationError({'email': ['The email is already registered.',]})
            if " " in Email:
                raise forms.ValidationError({'email': ['The Email cannot contain spaces.',]})
            if "@" not in Email or '.' not in Email:
                raise forms.ValidationError({'email': ['Invalid email.',]})
            return Email

    def clean_url(self):
        if 'url' in self.cleaned_data:
            url = self.cleaned_data['url']

            if url != None or url != "None" or url != "":
                return    
            if int(urlopen(url).getcode()) >= 400:
                raise forms.ValidationError({'url': ['The URL is invalid',]})
            return url

class RegistrationForm(BaseUserForm, ModelForm):
    email=CharField(label="Email",max_length=50,required=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    Password=CharField(label="Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2=CharField(label="Confirm Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))
    first_name=CharField(label="First Name",max_length=40,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'first_name'}))
    last_name=CharField(label="Last Name",max_length=40,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'last_name'}))
    organization=CharField(label="Organization",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'Organization'}))
    department=CharField(label="Department",max_length=30,required=True,widget=TextInput(attrs={'class':'form-control','name':'department'}))
    city=CharField(label="City",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'city'}))
    # State=ChoiceField(label="State",required=False,choices=USA,initial={'N/A': 'N/A'},widget=forms.Select(attrs={'class': 'form-control', 'name': 'State'}))
    state=ChoiceField(label="State",required=False,choices=USA,initial={'N/A': 'N/A'},widget=forms.Select(attrs={'class': 'form-control', 'name': 'state'}))
    country=CharField(label="Country",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'country'}))
    url=CharField(label="Url",max_length=30,required=False,widget=TextInput(attrs={'class': 'form-control', 'name': 'Uul'}))
    photo=FileField(label="Photo",required=False,widget=FileInput(attrs={'class': 'form-control', 'name': 'photo'}))

    def clean(self):
        Email = BaseUserForm.clean_new_email(self)
        Pass  = BaseUserForm.clean_2_password(self)
        Url   = BaseUserForm.clean_url(self)
        super(RegistrationForm, self).clean()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'Password', 'Password2', ]
        required_css_class = 'required'

    def save(self,commit=True): 
        user=super(RegistrationForm, self).save(commit=False)
        user.email=self.cleaned_data['email']
        user.first_name=self.cleaned_data['first_name']
        user.last_name=self.cleaned_data['last_name']
        user.organization=self.cleaned_data['organization']
        user.department=self.cleaned_data['department']
        user.city=self.cleaned_data['city']
        user.state=self.cleaned_data['state']
        user.country=self.cleaned_data['country']
        user.url=self.cleaned_data['url']
        user.photo=self.cleaned_data['photo']
        user.set_password(self.cleaned_data['Password'])
        if commit:
            user.save()
        return user

class UserForm(BaseUserForm, ModelForm):
    email=CharField(label="Email",max_length=50,required=False,disabled=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    Password=CharField(label="Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2=CharField(label="Confirm Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))
    first_name=CharField(label="First Name",max_length=40,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'first_name'}))
    last_name=CharField(label="Last Name",max_length=40,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'last_name'}))
    organization=CharField(label="Organization",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'Organization'}))
    department=CharField(label="Department",max_length=30,required=True,widget=TextInput(attrs={'class':'form-control','name':'department'}))
    city=CharField(label="City",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'city'}))
    state=ChoiceField(label="State",required=False,choices=USA,initial={'N/A': 'N/A'},widget=forms.Select(attrs={'class': 'form-control', 'name': 'state'}))
    country=CharField(label="Country",max_length=30,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'country'}))
    url=CharField(label="Url",max_length=30,required=False,widget=TextInput(attrs={'class': 'form-control', 'name': 'Uul'}))
    photo=FileField(label="Photo",required=False,widget=FileInput(attrs={'class': 'form-control', 'name': 'photo'}))

    def clean(self):
        Pass  = BaseUserForm.clean_2_password(self)
        Url   = BaseUserForm.clean_url(self)
        Email = BaseUserForm.clean_logged_email(self)
        super(UserForm, self).clean()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'Password', 'Password2', 'organization', 'department', 'city', 'state', 'country', 'url', 'photo']#, ]
        required_css_class = 'required'

    def save(self,commit=True):
        user=super(UserForm, self).save(commit=False)
        user.email=self.cleaned_data['email']
        user.first_name=self.cleaned_data['first_name']
        user.last_name=self.cleaned_data['last_name']
        user.organization=self.cleaned_data['organization']
        user.department=self.cleaned_data['department']
        user.city=self.cleaned_data['city']
        user.state=self.cleaned_data['state']
        user.country=self.cleaned_data['country']
        if self.cleaned_data['url'] != None:
            user.url=self.cleaned_data['url']
        if self.cleaned_data['photo'] != None:
            user.photo=self.cleaned_data['email'] + '.' + self.cleaned_data['photo'].name.split('.')[-1]
        if self.cleaned_data['Password'] != '':
            if self.cleaned_data['Password'] != None:
                user.set_password(self.cleaned_data['Password'])        
        if commit:
            user.save()
        return user

class LoginForm(BaseUserForm, Form):
    email=CharField(label="Email",max_length=50,required=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    Password=CharField(label="Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))

    def clean(self):
        Pass  = BaseUserForm.clean_password(self)
        email = BaseUserForm.clean_logged_email(self)
        super(LoginForm, self).clean()

class ResetForm(Form):
    email=CharField(label="Email",max_length=50,required=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    
    def clean(self):
        email = self.clean_email()


class ResetPassForm(Form):
    Password=CharField(label="Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2=CharField(label="Confirm Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))

    def clean(self):
        Pass  = self.clean_password()
        super(ResetPassForm, self).clean()

    def clean_password(self):
        if 'Password' in self.cleaned_data:
            Password=self.cleaned_data['Password']
            Password2=self.cleaned_data['Password2']
            if Password != Password2:
                raise ValidationError({'Password': ["The passwords do not match.",], 'Password2': ["The passwords do not match.",]})
            if len(Password) < 8:
                raise ValidationError({'Password': ["The password is too short.",], 'Password2': ["The password is too short.",]})
            if len(Password) > 15:
                raise ValidationError({'Password': ["The password is too long, it cannot have more than 15 characters.",], 'Password2': ["The password is too long, it cannot have more than 15 characters.",]})
            if not bool(re.search(r'\d', Password)):
                raise ValidationError({'Password': ["The password must contain at least 1 digit.",], 'Password2': ["The password must contain at least 1 digit.",]})
            if Password.isupper() or Password.islower():
                raise ValidationError({'Password': ["The password must contain upper and lower case letters.",], 'Password2': ["The password must contain upper and lower case letters.",]})
            if Password.isalnum() and not Password.isalpha() and not Password.isdigit():
                raise ValidationError({'Password': ["Password must contain at least 1 letter.",], 'Password2': ["Password must contain at least 1 letter.",]})
            return Password

    class Meta:
        model = User
        required_css_class = 'required'

    def save(self,commit=True): 
        user=super(UserForm, self).save(commit=False)
        if self.cleaned_data['Password'] != '':
            user.set_password(self.cleaned_data['Password'])        
        if commit:
            user.save()
        return user

class NewProjectForm(Form):
    import datetime
    Access1 = (('0', 'Interested members may obtain access to this project.'),('1', 'Interested members may apply for access to this project.'),('2','Access to this project is not available at this time.'),)
    project_name = CharField(label="Project Name",max_length=150,required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'project_name'}))
    project_abstract = CharField(label="Project Abstract",required=True,widget=TextInput(attrs={'class': 'form-control', 'name': 'project_abstract'}))
    access_policy=ChoiceField(label="Access Policy",required=True,initial=Access1[1],choices=Access1, widget=forms.Select(attrs={'class': 'form-control', 'name': 'access_policy'}))
    has_dua=ChoiceField(label="Has DUA",required=True,initial={'1': 'Yes'}, choices=(('1', 'Yes'),('0', 'No'),),widget=forms.Select(attrs={'class': 'form-control', 'name': 'has_dua'}))
    completition_date=forms.DateField(label="Estimated completion date",initial=datetime.date.today,required=True,widget=SelectDateWidget(attrs={'class': 'form-control form-inline col-md-4', 'name': 'completition_date'},empty_label=("Choose Year", "Choose Month", "Choose Day") ))

    storage_limit = IntegerField(label="Storage Limit",required=True,widget=NumberInput(attrs={'class': 'form-control', 'name': 'storage_limit'}), validators=[MaxValueValidator(100),MinValueValidator(1)])
    



