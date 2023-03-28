from django.db import models

from project.modelcomponents.fields import SafeHTMLField


class Course(models.Model):
    training_type = models.ForeignKey('user.TrainingType',
                                      on_delete=models.CASCADE, related_name='courses')
    version = models.FloatField(default=1.0)

    class Meta:
        default_permissions = ('change',)
        unique_together = ('training_type', 'version')

    def __str__(self):
        return f'{self.training_type} v{self.version}'


class Module(models.Model):
    name = models.CharField(max_length=100)
    course = models.ForeignKey('training.Course', on_delete=models.CASCADE, related_name='modules')
    order = models.PositiveIntegerField()
    description = SafeHTMLField()

    class Meta:
        unique_together = ('course', 'order')

    def __str__(self):
        return self.name


class Quiz(models.Model):
    question = SafeHTMLField()
    module = models.ForeignKey('training.Module',
                               on_delete=models.CASCADE, related_name='quizzes')
    order = models.PositiveIntegerField()


class ContentBlock(models.Model):
    module = models.ForeignKey('training.Module',
                               on_delete=models.CASCADE, related_name='contents')
    body = SafeHTMLField()
    order = models.PositiveIntegerField()


class QuizChoice(models.Model):
    quiz = models.ForeignKey('training.Quiz',
                             on_delete=models.CASCADE, related_name='choices')
    body = models.TextField()
    is_correct = models.BooleanField('Correct Choice?', default=False)


class CourseProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'IP', 'In Progress'
        COMPLETED = 'C', 'Completed'

    user = models.ForeignKey('user.User', on_delete=models.CASCADE)
    course = models.ForeignKey('training.Course', on_delete=models.CASCADE)
    status = models.CharField(max_length=2, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f'{self.user.username} - {self.course}'

    def get_next_module(self):
        if self.status == self.Status.COMPLETED:
            return None

        next_module = self.module_progresses.filter(status=self.module_progresses.model.Status.IN_PROGRESS).first()
        if next_module:
            return next_module.module

        last_module = self.module_progresses.filter(
            status=self.module_progresses.model.Status.COMPLETED).order_by('-last_completed_order').first()
        if last_module:
            return self.course.modules.filter(order__gt=last_module.module.order).order_by('order').first()

        return self.course.modules.first()


class ModuleProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'IP', 'In Progress'
        COMPLETED = 'C', 'Completed'

    course_progress = models.ForeignKey('training.CourseProgress', on_delete=models.CASCADE,
                                        related_name='module_progresses')
    module = models.ForeignKey('training.Module', on_delete=models.CASCADE)
    status = models.CharField(max_length=2, choices=Status.choices, default=Status.IN_PROGRESS)
    last_completed_order = models.PositiveIntegerField(null=True, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.course_progress.user.username} - {self.module}'

    def get_next_content_or_quiz(self):
        if self.status == self.Status.COMPLETED:
            return None

        next_content = self.module.contents.filter(order__gt=self.last_completed_order).order_by('order').first()
        next_quiz = self.module.quizzes.filter(order__gt=self.last_completed_order).order_by('order').first()

        if next_content and next_quiz:
            return next_content if next_content.order < next_quiz.order else next_quiz
        elif next_content:
            return next_content
        elif next_quiz:
            return next_quiz
        else:
            return None

    def update_last_completed_order(self, completed_content_or_quiz):
        if completed_content_or_quiz.order > self.last_completed_order:
            self.last_completed_order = completed_content_or_quiz.order
            self.save()


class CompletedContent(models.Model):
    module_progress = models.ForeignKey('training.ModuleProgress', on_delete=models.CASCADE,
                                        related_name='completed_contents')
    content = models.ForeignKey('training.ContentBlock', on_delete=models.CASCADE)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.module_progress.course_progress.user.username} - {self.content}'


class CompletedQuiz(models.Model):
    module_progress = models.ForeignKey('training.ModuleProgress', on_delete=models.CASCADE,
                                        related_name='completed_quizzes')
    quiz = models.ForeignKey('training.Quiz', on_delete=models.CASCADE)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.module_progress.course_progress.user.username} - {self.quiz}'
