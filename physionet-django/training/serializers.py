import datetime
from rest_framework import serializers
from django.db import transaction

from training.models import Course, Module, Quiz, QuizChoice, ContentBlock
from user.models import Training, TrainingType
from user.enums import RequiredField


class QuizChoiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = QuizChoice
        fields = ['body', 'is_correct']
        read_only_fields = ['id', 'quiz']


class QuizSerializer(serializers.ModelSerializer):
    choices = QuizChoiceSerializer(many=True)

    class Meta:
        model = Quiz
        fields = ['question', 'order', 'choices']
        read_only_fields = ['id', 'module']


class ContentBlockSerializer(serializers.ModelSerializer):

    class Meta:
        model = ContentBlock
        fields = ['body', 'order']
        read_only_fields = ['id', 'module']


class ModuleSerializer(serializers.ModelSerializer):
    quizzes = QuizSerializer(many=True)
    contents = ContentBlockSerializer(many=True)

    class Meta:
        model = Module
        fields = ['name', 'description', 'order', 'contents', 'quizzes']
        read_only_fields = ['id', 'course']


def create_quizzes(module_instance, quizzes_data):
    choice_bulk = []
    for quiz in quizzes_data:
        choices = quiz.pop('choices')

        quiz['module'] = module_instance
        q = Quiz(**quiz)
        q.save()

        for choice in choices:
            choice['quiz'] = q
            choice_bulk.append(QuizChoice(**choice))

    QuizChoice.objects.bulk_create(choice_bulk)


def create_contentblocks(module_instance, content_data):
    content_bulk = []
    for content in content_data:
        content['module'] = module_instance
        content_bulk.append(ContentBlock(**content))
    ContentBlock.objects.bulk_create(content_bulk)


def create_modules(course_instance, modules_data):
    for module_data in modules_data:
        quizzes = module_data.pop('quizzes')
        contents = module_data.pop('contents')

        module_data['course'] = course_instance
        module_instance = Module.objects.create(**module_data)

        create_quizzes(module_instance, quizzes)
        create_contentblocks(module_instance, contents)


class CourseSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True)

    class Meta:
        model = Course
        fields = ['title', 'description', 'valid_duration', 'version', 'modules']
        read_only_fields = ['id', 'training_type']

    def update(self, instance, validated_data):
        with transaction.atomic():
            course = validated_data
            modules = course.pop('modules')
            course['training_type'] = instance.training_type

            course_instance = Course.objects.create(**course)
            create_modules(course_instance, modules)

        return course_instance

    def create(self, validated_data):
        with transaction.atomic():
            course = validated_data
            modules = course.pop('modules')
            training_type_name = validated_data['title']
            training_type_description = validated_data['description']
            training_type_valid_duration = validated_data['valid_duration']
            training_type_required_field = RequiredField.PLATFORM

            training_type_instance = TrainingType.objects.create(
                name=training_type_name,
                description=training_type_description,
                valid_duration=training_type_valid_duration,
                required_field=training_type_required_field
            )

            course['training_type'] = training_type_instance
            course_instance = Course.objects.create(**course)

            create_modules(course_instance, modules)

        return course_instance
