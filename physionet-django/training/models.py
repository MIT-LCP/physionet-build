from django.db import models
from django.utils import timezone

from project.modelcomponents.fields import SafeHTMLField
from user.models import Training
from project.validators import validate_version

NUMBER_OF_DAYS_SET_TO_EXPIRE = 30


class Course(models.Model):
    """
    A model representing a course for a specific training type.

    Attributes:
        training_type (ForeignKey): The training type associated with the course.
        version (CharField): The version of the course.
    """

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

    def __str__(self):
        return f"{self.training_type} v{self.version}"


class Module(models.Model):
    """
    A module is a unit of teaching within a course, typically covering a single topic or area of knowledge.

    Attributes:
        name (str): The name of the module.
        course (Course): The course to which the module belongs.
        order (int): The order in which the module appears within the course.
        description (SafeHTML): The description of the module, in SafeHTML format.
    """

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
    """
    A model representing a quiz within a training module.

    Each quiz has a question, belongs to a specific module, and has a designated order within that module.
    """

    question = SafeHTMLField()
    module = models.ForeignKey(
        "training.Module", on_delete=models.CASCADE, related_name="quizzes"
    )
    order = models.PositiveIntegerField()


class ContentBlock(models.Model):
    """
    A model representing a block of content within a training module.

    Attributes:
        module (ForeignKey): The module to which this content block belongs.
        body (SafeHTMLField): The HTML content of the block.
        order (PositiveIntegerField): The order in which this block should be displayed within the module.
    """

    module = models.ForeignKey(
        "training.Module", on_delete=models.CASCADE, related_name="contents"
    )
    body = SafeHTMLField()
    order = models.PositiveIntegerField()


class QuizChoice(models.Model):
    """
    A quiz choice is a collection of choices, which is a collection of several types of
    content. A quiz choice is associated with a quiz, and an order number.
    The order number is used to track the order of the quiz choices in a quiz.
    """

    quiz = models.ForeignKey(
        "training.Quiz", on_delete=models.CASCADE, related_name="choices"
    )
    body = models.TextField()
    is_correct = models.BooleanField("Correct Choice?", default=False)


class CourseProgress(models.Model):
    """
    Model representing the progress of a user in a course.

    Fields:
    - user: ForeignKey to User model
    - course: ForeignKey to Course model
    - status: CharField with choices of "In Progress" and "Completed"
    - started_at: DateTimeField that is automatically added on creation
    - completed_at: DateTimeField that is nullable and blankable

    Methods:
    - __str__: Returns a string representation of the CourseProgress object
    - get_next_module: Returns the next module that the user should be working on
    """

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
    """
    Model representing the progress of a user in a module.

    Fields:
    - course_progress: ForeignKey to CourseProgress model
    - module: ForeignKey to Module model
    - status: CharField with choices of "In Progress" and "Completed"
    - last_completed_order: PositiveIntegerField with default value of 0
    - started_at: DateTimeField that is nullable and blankable
    - updated_at: DateTimeField that is automatically updated on save

    Methods:
    - __str__: Returns a string representation of the ModuleProgress object

    """

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
    """
    Model representing a completed content block.

    Fields:
    - module_progress: ForeignKey to ModuleProgress model
    - content: ForeignKey to ContentBlock model
    - completed_at: DateTimeField that is nullable and blankable

    Methods:
    - __str__: Returns a string representation of the CompletedContent object
    """

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
    """
    Model representing a completed quiz.

    Fields:
    - module_progress: ForeignKey to ModuleProgress model
    - quiz: ForeignKey to Quiz model
    - completed_at: DateTimeField that is nullable and blankable

    Methods:
    - __str__: Returns a string representation of the CompletedQuiz object
    """

    module_progress = models.ForeignKey(
        "training.ModuleProgress",
        on_delete=models.CASCADE,
        related_name="completed_quizzes",
    )
    quiz = models.ForeignKey("training.Quiz", on_delete=models.CASCADE)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.module_progress.course_progress.user.username} - {self.quiz}"
