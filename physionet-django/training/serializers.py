import datetime
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from training.models import OnPlatformTraining, Module, Quiz, QuizChoice, ContentBlock
from user.models import Training, TrainingType
from notification.utility import notify_users_of_training_expiry


NUMBER_OF_DAYS_SET_TO_EXPIRE = 30


class QuizChoiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = QuizChoice
        fields = "__all__"
        read_only_fields = ['id', 'quiz']


class QuizSerializer(serializers.ModelSerializer):
    choices = QuizChoiceSerializer(many=True)

    class Meta:
        model = Quiz
        fields = "__all__"
        read_only_fields = ['id', 'module']


class ContentBlockSerializer(serializers.ModelSerializer):

    class Meta:
        model = ContentBlock
        fields = "__all__"
        read_only_fields = ['id', 'module']


class ModuleSerializer(serializers.ModelSerializer):
    quizzes = QuizSerializer(many=True)
    contents = ContentBlockSerializer(many=True)

    class Meta:
        model = Module
        fields = "__all__"
        read_only_fields = ['id', 'training']


class OnPlatformTrainingSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True)

    class Meta:
        model = OnPlatformTraining
        fields = "__all__"
        read_only_fields = ['id', 'training_type']


class TrainingTypeSerializer(serializers.ModelSerializer):
    op_trainings = OnPlatformTrainingSerializer()

    class Meta:
        model = TrainingType
        fields = "__all__"
        read_only_fields = ['id']

    def update_training_for_major_version_change(self, instance):
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
            op_training = validated_data.pop('op_trainings')
            quizzes = op_training.pop('quizzes')
            contents = op_training.pop('contents')

            op_training['training_type'] = instance

            op_training_instance = OnPlatformTraining.objects.create(**op_training)

            quiz_bulk = []
            choice_bulk = []
            for quiz in quizzes:
                choices = quiz.pop('choices')

                quiz['training'] = op_training_instance
                q = Quiz(**quiz)
                q.save()
                quiz_bulk.append(q)

                for choice in choices:
                    choice['quiz'] = q
                    choice_bulk.append(QuizChoice(**choice))

            # Quiz.objects.bulk_create(quiz_bulk)
            QuizChoice.objects.bulk_create(choice_bulk)

            content_bulk = []
            for content in contents:
                content['training'] = op_training_instance
                content_bulk.append(ContentBlock(**content))
            ContentBlock.objects.bulk_create(content_bulk)

            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if op_training.get("version"):
                if str(op_training.get("version")).endswith("0"):
                    self.update_training_for_major_version_change(instance)

        return instance

    def create(self, validated_data):

        with transaction.atomic():
            op_training = validated_data.pop('op_trainings')
            modules = op_training.pop('modules')

            op_training['training_type'] = instance = TrainingType.objects.create(**validated_data)

            op_training_instance = OnPlatformTraining.objects.create(**op_training)

            for module in modules:
                quizzes = module.pop('quizzes')
                contents = module.pop('contents')

                module['training'] = op_training_instance
                module_instance = Module.objects.create(**module)

                # quiz_bulk = []
                choice_bulk = []
                for quiz in quizzes:
                    choices = quiz.pop('choices')

                    quiz['module'] = module_instance
                    q = Quiz(**quiz)
                    q.save()
                    # quiz_bulk.append(q)

                    for choice in choices:
                        choice['quiz'] = q
                        choice_bulk.append(QuizChoice(**choice))

                # Quiz.objects.bulk_create(quiz_bulk)
                QuizChoice.objects.bulk_create(choice_bulk)

                content_bulk = []
                for content in contents:
                    content['module'] = module_instance
                    content_bulk.append(ContentBlock(**content))
                ContentBlock.objects.bulk_create(content_bulk)

        return instance
