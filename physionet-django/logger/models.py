from django.db import models


class DBLogEntry(models.Model):
    """
    Custom logger to store the user and core project
    """
    time = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10)
    message = models.TextField()
    asctime = models.CharField(max_length=50)
    module = models.CharField(max_length=50)
    msg = models.TextField()
    user = models.ForeignKey('user.User', related_name='%(class)s',
                             on_delete=models.SET_NULL, null=True)
    core_project = models.ForeignKey('project.CoreProject', null=True,
                                     related_name='%(class)s',
                                     on_delete=models.SET_NULL)

    def __str__(self):
        return self.message
