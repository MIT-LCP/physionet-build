from django.db import models
from django.utils import timezone

from project.modelcomponents.fields import SafeHTMLField
from notification.utility import notify_users_of_training_expiry
from user.models import Training
from project.validators import validate_version

NUMBER_OF_DAYS_SET_TO_EXPIRE = 30


class Course(models.Model):
    training_type = models.ForeignKey(
        "user.TrainingType", on_delete=models.CASCADE, related_name="courses"
    )
    version = models.CharField(
        max_length=15, default="", blank=True, validators=[validate_version]
    )

    class Meta:
        default_permissions = ("change",)
        constraints = [
            models.UniqueConstraint(
                fields=["training_type", "version"], name="unique_course"
            )
        ]
        permissions = [
            ("can_view_course_guidelines", "Can view course guidelines"),
        ]

    def update_course_for_major_version_change(self, instance):
        """
        If it is a major version change, it sets all former user trainings
        to a reduced date, and informs them all.
        """

        trainings = Training.objects.filter(
            training_type=instance,
            process_datetime__gte=timezone.now() - instance.valid_duration,
        )
        _ = trainings.update(
            process_datetime=(
                timezone.now()
                - (
                    instance.valid_duration
                    - timezone.timedelta(days=NUMBER_OF_DAYS_SET_TO_EXPIRE)
                )
            )
        )

        for training in trainings:
            notify_users_of_training_expiry(
                training.user, instance.name, NUMBER_OF_DAYS_SET_TO_EXPIRE
            )

    def __str__(self):
        return f"{self.training_type} v{self.version}"


class Module(models.Model):
    name = models.CharField(max_length=100)
    course = models.ForeignKey(
        "training.Course", on_delete=models.CASCADE, related_name="modules"
    )
    order = models.PositiveIntegerField()
    description = SafeHTMLField()

    class Meta:
        unique_together = ("course", "order")

    def __str__(self):
        return self.name


class Quiz(models.Model):
    question = SafeHTMLField()
    module = models.ForeignKey(
        "training.Module", on_delete=models.CASCADE, related_name="quizzes"
    )
    order = models.PositiveIntegerField()


class ContentBlock(models.Model):
    module = models.ForeignKey(
        "training.Module", on_delete=models.CASCADE, related_name="contents"
    )
    body = SafeHTMLField()
    order = models.PositiveIntegerField()


class QuizChoice(models.Model):
    quiz = models.ForeignKey(
        "training.Quiz", on_delete=models.CASCADE, related_name="choices"
    )
    body = models.TextField()
    is_correct = models.BooleanField("Correct Choice?", default=False)


class CourseProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IP", "In Progress"
        COMPLETED = "C", "Completed"

    user = models.ForeignKey("user.User", on_delete=models.CASCADE)
    course = models.ForeignKey("training.Course", on_delete=models.CASCADE)
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.IN_PROGRESS
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"], name="unique_course_progress"
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.course}"

    def get_next_module(self):
        if self.status == self.Status.COMPLETED:
            return None

        next_module = self.module_progresses.filter(
            status=self.module_progresses.model.Status.IN_PROGRESS
        ).first()
        if next_module:
            return next_module.module

        last_module = (
            self.module_progresses.filter(
                status=self.module_progresses.model.Status.COMPLETED
            )
            .order_by("-last_completed_order")
            .first()
        )
        if last_module:
            return (
                self.course.modules.filter(order__gt=last_module.module.order)
                .order_by("order")
                .first()
            )

        return self.course.modules.first()


class ModuleProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IP", "In Progress"
        COMPLETED = "C", "Completed"

    course_progress = models.ForeignKey(
        "training.CourseProgress",
        on_delete=models.CASCADE,
        related_name="module_progresses",
    )
    module = models.ForeignKey("training.Module", on_delete=models.CASCADE)
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.IN_PROGRESS
    )
    last_completed_order = models.PositiveIntegerField(null=True, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.course_progress.user.username} - {self.module}"


class CompletedContent(models.Model):
    module_progress = models.ForeignKey(
        "training.ModuleProgress",
        on_delete=models.CASCADE,
        related_name="completed_contents",
    )
    content = models.ForeignKey("training.ContentBlock", on_delete=models.CASCADE)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.module_progress.course_progress.user.username} - {self.content}"


class CompletedQuiz(models.Model):
    module_progress = models.ForeignKey(
        "training.ModuleProgress",
        on_delete=models.CASCADE,
        related_name="completed_quizzes",
    )
    quiz = models.ForeignKey("training.Quiz", on_delete=models.CASCADE)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.module_progress.course_progress.user.username} - {self.quiz}"
