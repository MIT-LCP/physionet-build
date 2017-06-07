from django.forms import CharField, ModelForm, EmailInput, PasswordInput, TextInput, ChoiceField, Select, FileField, FileInput, Form
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.conf import settings
from .models import User, USA
from urllib import urlopen
import re

class BaseUserForm():
    def clean_2_password(self):
        Password  = self.cleaned_data.get('Password' , False)
        Password2 = self.cleaned_data.get('Password2' , False)
        if Password and Password2:
            if (Password == "" and Password2 == "") or (Password == None and Password2 == None):
                print "_1_"
                return Password
            if Password != Password2:
                print "2"
                raise ValidationError({'Password': ["The passwords do not match.",], 'Password2': ["The passwords do not match.",]})
            if len(Password) < 8:
                print "3"
                raise ValidationError({'Password': ["The password is too short.",], 'Password2': ["The password is too short.",]})
            if len(Password) > 15:
                print "4"
                raise ValidationError({'Password': ["The password is too long, it cannot have more than 15 characters.",], 'Password2': ["The password is too long, it cannot have more than 15 characters.",]})
            if not bool(re.search(r'\d', Password)):
                print "5"
                raise ValidationError({'Password': ["The password must contain at least 1 digit.",], 'Password2': ["The password must contain at least 1 digit.",]})
            if not bool(re.search(r'[a-zA-Z]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 letter.",], 'Password2': ["Password must contain at least 1 letter.",]})
            if not bool(re.search(r'[~!@#$%.&?^*]', Password)):
                raise ValidationError({'Password': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *",], 'Password2': ["Password must contain at least 1 special character. Acccepted are: ~ ! @ # $ % & ? ^ *.",]})
            if Password.isupper() or Password.islower():
                raise ValidationError({'Password': ["The password must contain upper and lower case letters.",], 'Password2': ["The password must contain upper and lower case letters.",]})
            return Password

    def clean_password(self):
        Password = self.cleaned_data.get('Password' , False)
        if Password:
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
        Email = self.cleaned_data.get('email' , False)
        if Email:
            Exists = True
            try:
                User.objects.get(email=Email)
            except ObjectDoesNotExist:
                Exists = False
            if Exists:
                # print 1
                raise ValidationError({'email': ['The email is already registered.',]})
            if not re.match(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', Email):
                raise ValidationError({'email': ['Invalid email.',]})
            return Email

    def clean_logged_email(self):
        Email = self.cleaned_data.get('email' , False)
        if Email:
            Exists = True
            try:
                Person = User.objects.get(email=Email)
                # print Person
            except ObjectDoesNotExist:
                Exists = False
            if not Exists:
                # print 2
                raise ValidationError({'email': ['The email is already registered.',]})
            if " " in Email:
                raise ValidationError({'email': ['The Email cannot contain spaces.',]})
            if "@" not in Email or '.' not in Email:
                raise ValidationError({'email': ['Invalid email.',]})
            return Email

    def clean_url(self):
        url = self.cleaned_data.get('url' , False)
        if url:
            if url != None or url != "None" or url != "":
                return    
            if int(urlopen(url).getcode()) >= 400:
                raise ValidationError({'url': ['The URL is invalid',]})
            return url

    def clean_image(self):
        image = self.cleaned_data.get('photo' , False)
        if image:
            if image._size > settings.MAX_UPLOAD_SIZE:
                raise ValidationError({'photo': ['Image file too large ( > 4mb ).',]})
            if image.content_type.split('/')[0] not in settings.CONTENT_TYPES:
                raise ValidationError({'photo': ['Wrong type of image.',]})
            return image

class RegistrationForm(BaseUserForm, ModelForm):
    Password  = CharField(label="Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2 = CharField(label="Confirm Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))

    def clean(self):
        Email = BaseUserForm.clean_new_email(self)
        Pass  = BaseUserForm.clean_2_password(self)
        Url   = BaseUserForm.clean_url(self)
        Image = BaseUserForm.clean_image(self)
        super(RegistrationForm, self).clean()

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'organization', 'department', 'city', 'state', 'country', 'url', 'photo']
        widgets = {
            'email' : EmailInput(attrs={'class': 'form-control', 'name': 'email', 'required':'True'}),
            'first_name'   : TextInput(attrs={'class': 'form-control', 'name': 'first_name',   'required' : 'True'}),
            'last_name'    : TextInput(attrs={'class': 'form-control', 'name': 'last_name',    'required' : 'True'}),
            'organization' : TextInput(attrs={'class': 'form-control', 'name': 'Organization', 'required' : 'True'}),
            'department'   : TextInput(attrs={'class': 'form-control', 'name':'department'   , 'required' : 'True'}),
            'city'         : TextInput(attrs={'class': 'form-control', 'name': 'city', 'required' : 'True'}),
            'state'   : Select(attrs={'class': 'form-control', 'name': 'state', 'choices' : USA}),
            'country' : TextInput(attrs={'class': 'form-control', 'name': 'country', 'required' : 'True'}),
            'url'     : TextInput(attrs={'class': 'form-control', 'name': 'Url'}),
            'photo'   : FileInput(attrs={'class': 'form-control', 'name': 'photo', 'accept': 'image/*'}),}

    def save(self,commit=True): 
        user = super(RegistrationForm, self).save(commit=False)
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.organization = self.cleaned_data['organization']
        user.department   = self.cleaned_data['department']
        user.city       = self.cleaned_data['city']
        user.state      = self.cleaned_data['state']
        user.country    = self.cleaned_data['country']
        if self.cleaned_data['url'] != None:
            if self.cleaned_data['url'] != '':
                user.url = self.cleaned_data['url']
        if self.cleaned_data['photo'] != None:
            if self.cleaned_data['photo'] != '':
                user.photo="Profile." + self.cleaned_data['photo'].name.split('.')[-1]
        user.set_password(self.cleaned_data['Password'])
        if commit:
            user.save()
        return user

class UserForm(BaseUserForm, ModelForm):
    Password = CharField(label="Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2 = CharField(label="Confirm Password",max_length=15,required=False,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))

    def clean(self):
        # print self.fields['first_name'].run_validators(self)
        Pass  = BaseUserForm.clean_2_password(self)
        Url   = BaseUserForm.clean_url(self)
        Email = BaseUserForm.clean_logged_email(self)
        Image = BaseUserForm.clean_image(self)

    class Meta:
        model   = User
        fields  = ['first_name', 'last_name', 'email', 'organization', 'department', 'city', 'state', 'country', 'url', 'photo']
        widgets = {
            'email' : EmailInput(attrs={'class': 'form-control', 'name': 'email', 'readonly':'True'}),
            'first_name' : TextInput(attrs={'class': 'form-control', 'name': 'first_name', 'required' : 'True'}),
            'last_name' : TextInput(attrs={'class': 'form-control', 'name': 'last_name', 'required' : 'True'}),
            'organization' : TextInput(attrs={'class': 'form-control', 'name': 'Organization', 'required' : 'True'}),
            'department' : TextInput(attrs={'class':'form-control','name':'department', 'required' : 'True'}),
            'city' : TextInput(attrs={'class': 'form-control', 'name': 'city', 'required' : 'True'}),
            'state' :  Select(attrs={'class': 'form-control', 'name': 'state', 'choices' : USA}),
            'country' : TextInput(attrs={'class': 'form-control', 'name': 'country', 'required' : 'True'}),
            'url' : TextInput(attrs={'class': 'form-control', 'name': 'Url'}),
            'photo' : FileInput(attrs={'class': 'form-control', 'name': 'photo', 'accept': 'image/*'}),}

    def save(self,commit=True):
        user = super(UserForm, self).save(commit=False)
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.organization = self.cleaned_data['organization']
        user.department   = self.cleaned_data['department']
        user.city       = self.cleaned_data['city']
        user.state      = self.cleaned_data['state']
        user.country    = self.cleaned_data['country']
        if self.cleaned_data['url'] != None:
            user.url = self.cleaned_data['url']
        if self.cleaned_data['photo'] != None:
            if self.cleaned_data['photo'] != '':
                user.photo="Profile." + self.cleaned_data['photo'].name.split('.')[-1]
        if self.cleaned_data['Password'] != '':
            if self.cleaned_data['Password'] != None:
                user.set_password(self.cleaned_data['Password'])        
        if commit:
            user.save()
        return user

class LoginForm(BaseUserForm, Form):
    email = CharField(label="Email",max_length=50,required=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    Password = CharField(label="Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    
    def clean(self):
        Pass  = BaseUserForm.clean_password(self)
        email = BaseUserForm.clean_logged_email(self)
        super(LoginForm, self).clean()

class ResetForm(BaseUserForm, Form):
    email = CharField(label="Email",max_length=50,required=True,widget=EmailInput(attrs={'class': 'form-control', 'name': 'email'}))
    
    def clean(self):
        email = BaseUserForm.clean_logged_email(self)

class ResetPassForm(BaseUserForm, Form):
    Password = CharField(label="Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name':'Password'}))
    Password2 = CharField(label="Confirm Password",max_length=15,required=True,widget=PasswordInput(attrs={'class':'form-control','name': 'Password2'}))

    def clean(self):
        Pass  = BaseUserForm.clean_2_password(self)
        super(ResetPassForm, self).clean()

    class Meta:
        model = User
        required_css_class = 'required'

    def save(self,commit=True): 
        user = super(UserForm, self).save(commit=False)
        if self.cleaned_data['Password'] != '':
            if self.cleaned_data['Password'] != None:
                user.set_password(self.cleaned_data['Password'])      
        if commit:
            user.save()
        return user




