from django.db import models


class BaseInvitation(models.Model):
    """
    Base class for authorship invitations and storage requests
    """
    project = models.ForeignKey('project.ActiveProject',
        related_name='%(class)ss', on_delete=models.CASCADE)
    request_datetime = models.DateTimeField(auto_now_add=True)
    response_datetime = models.DateTimeField(null=True)
    response = models.BooleanField(null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
