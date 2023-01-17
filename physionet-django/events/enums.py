from django.db import models


class EventCategory(models.TextChoices):
    COURSE = "Course"
    WORKSHOP = "Workshop"
