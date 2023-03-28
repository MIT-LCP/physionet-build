import datetime
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from training.models import Course, Module, Quiz, QuizChoice, ContentBlock
from user.models import Training, TrainingType
from user.enums import RequiredField
from notification.utility import notify_users_of_training_expiry


NUMBER_OF_DAYS_SET_TO_EXPIRE = 30


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


class TrainingTypeSerializer(serializers.ModelSerializer):
    courses = CourseSerializer(many=True)

    class Meta:
        model = TrainingType
        fields = ['name', 'description', 'valid_duration', 'courses']
        read_only_fields = ['id']

    def update_course_for_major_version_change(self, instance):
        """
        If it is a major version change, it sets all former user trainings
        to a reduced date, and informs them all.
        """

        trainings = Training.objects.filter(
            training_type=instance,
            process_datetime__gte=timezone.now() - instance.valid_duration)
        _ = trainings.update(
            process_datetime=(
                timezone.now() - (instance.valid_duration - timezone.timedelta(
                    days=NUMBER_OF_DAYS_SET_TO_EXPIRE))))

        for training in trainings:
            notify_users_of_training_expiry(
                training.user, instance.name, NUMBER_OF_DAYS_SET_TO_EXPIRE)

    def update(self, instance, validated_data):

        with transaction.atomic():
            course = validated_data.pop('courses')[0]
            modules = course.pop('modules')

            course['training_type'] = instance

            course_instance = Course.objects.create(**course)

            for module in modules:
                quizzes = module.pop('quizzes')
                contents = module.pop('contents')

                module['course'] = course_instance
                module_instance = Module.objects.create(**module)

                choice_bulk = []
                for quiz in quizzes:
                    choices = quiz.pop('choices')

                    quiz['module'] = module_instance
                    q = Quiz(**quiz)
                    q.save()

                    for choice in choices:
                        choice['quiz'] = q
                        choice_bulk.append(QuizChoice(**choice))

                QuizChoice.objects.bulk_create(choice_bulk)

                content_bulk = []
                for content in contents:
                    content['module'] = module_instance
                    content_bulk.append(ContentBlock(**content))
                ContentBlock.objects.bulk_create(content_bulk)

            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if course.get("version"):
                if str(course.get("version")).endswith("0"):
                    self.update_course_for_major_version_change(instance)

        return course_instance

    def create(self, validated_data):

        with transaction.atomic():
            course = validated_data.pop('courses')[0]
            modules = course.pop('modules')

            validated_data['required_field'] = RequiredField.PLATFORM
            course['training_type'] = instance = TrainingType.objects.create(**validated_data)

            course_instance = Course.objects.create(**course)

            for module in modules:
                quizzes = module.pop('quizzes')
                contents = module.pop('contents')

                module['course'] = course_instance
                module_instance = Module.objects.create(**module)

                choice_bulk = []
                for quiz in quizzes:
                    choices = quiz.pop('choices')

                    quiz['module'] = module_instance
                    q = Quiz(**quiz)
                    q.save()

                    for choice in choices:
                        choice['quiz'] = q
                        choice_bulk.append(QuizChoice(**choice))

                QuizChoice.objects.bulk_create(choice_bulk)

                content_bulk = []
                for content in contents:
                    content['module'] = module_instance
                    content_bulk.append(ContentBlock(**content))
                ContentBlock.objects.bulk_create(content_bulk)

        return instance
