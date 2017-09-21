from django.db import models

class Project():
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=20, unique=True)
    
