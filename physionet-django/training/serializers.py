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


class CourseSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True)

    class Meta:
        model = Course
        fields = ['version', 'modules']
        read_only_fields = ['id', 'training_type']


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


def update_or_create_course(validated_data):
    with transaction.atomic():
        course = validated_data.pop('courses')[0]
        modules = course.pop('modules')

        if 'id' in course:
            instance = Course.objects.get(id=course['id'])
            for attr, value in course.items():
                setattr(instance, attr, value)
            instance.save()
        else:
            course_instance = Course.objects.create(**course)

        create_modules(course_instance, modules)

        if course.get("version"):
            if str(course.get("version")).endswith("0"):
                course.update_course_for_major_version_change(instance)

        return course_instance


class TrainingTypeSerializer(serializers.ModelSerializer):
    courses = CourseSerializer(many=True)

    class Meta:
        model = TrainingType
        fields = ['name', 'description', 'valid_duration', 'courses']
        read_only_fields = ['id']

    def update(self, instance, validated_data):
        validated_data['training_type'] = instance
        course_instance = update_or_create_course(validated_data)
        return course_instance

    def create(self, validated_data):
        validated_data['required_field'] = RequiredField.PLATFORM
        instance = TrainingType.objects.create(**validated_data)
        course_instance = update_or_create_course(validated_data)
        return instance  # is the return value correct?
