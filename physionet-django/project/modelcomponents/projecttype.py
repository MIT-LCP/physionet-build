from django.db import models


class ProjectType(models.Model):
    """
    The project types available on the platform
    """
    id = models.PositiveSmallIntegerField(primary_key=True)
    name = models.CharField(max_length=20)
    description = models.TextField()

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name
