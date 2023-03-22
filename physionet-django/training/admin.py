from django.contrib import admin
from training import models


class ContentBlockInline(admin.StackedInline):
    model = models.ContentBlock
    extra = 1


class QuizChoiceInline(admin.TabularInline):
    model = models.QuizChoice
    extra = 1


class QuizInline(admin.StackedInline):
    model = models.Quiz
    inlines = [QuizChoiceInline, ]
    extra = 1


class ModuleInline(admin.StackedInline):
    model = models.Module
    inlines = [ContentBlockInline, QuizInline]
    extra = 1


@admin.register(models.Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('module', 'question', 'order')
    inlines = [QuizChoiceInline, ]


@admin.register(models.Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'training', 'order')
    inlines = [ContentBlockInline, QuizInline]


@admin.register(models.OnPlatformTraining)
class OnPlatformTrainingAdmin(admin.ModelAdmin):
    list_display = ('training_type', 'version')
    inlines = [ModuleInline]
