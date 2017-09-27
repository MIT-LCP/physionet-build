from django.db import models
from ckeditor.fields import RichTextField

class Project(models.Model):

    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=20, unique=True)

    # 0=pre-submission, 1=under review, 2=published, 
    status = models.SmallIntegerField(default=0)

    # Access control
    owner = models.ForeignKey('user.User', related_name='owned_project') 

    # The top reviewer who authorizes/manages the review.
    editor = models.ForeignKey('user.User', related_name='editing_project', null=True)
    # People reviewing the project for publication
    reviewers = models.ManyToManyField('user.User', related_name='reviewing_project')

    # Access policy
    dua = models.ForeignKey('project.DUA', null=True, blank=True, related_name='project')
    training_course = models.ForeignKey('project.TrainingCourse', null=True, blank=True, related_name='project')
    id_verification = models.BooleanField(default=False)



    # Project metadata

    def __str__():
        return project.title


class AuthorInfo(models.Model):
    """
    Data owners/authors. Credited for contributing/owning the data
    """
    author = models.ForeignKey('user.User', related_name='author_info')
    is_submitting_author = models.BooleanField(default=False)
    equal_contributor = models.BooleanField(default=False)
    display_order = models.SmallIntegerField()
    project = models.ForeignKey('project.Project', related_name='author_info')


class DUA(models.Model):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=20, null=True)
    description = RichTextField()
    content = RichTextField()


class TrainingCourse(models.Model):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=20, null=True)
    description = RichTextField()
    url = models.URLField()


class DUASignature(models.Model):
    user = models.OneToOneField('user.User', related_name='dua_signature')
    date = models.DateField(auto_now_add=True)
    dua = models.OneToOneField('project.DUA', related_name='dua_signature')


class TrainingCourseCompletion(models.Model):
    user = models.OneToOneField('user.User', related_name='training_course_completion')
    date = models.DateField(auto_now_add=True)
    training_course = models.OneToOneField('project.TrainingCourse', related_name='training_course_completion')


class Review():
    project = models.ForeignKey('project.Project')