import json
import operator
from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, TrainingQuestion, RequiredField
from user.enums import TrainingStatus

from training.models import OnPlatformTraining, Quiz, QuizChoice, ContentBlock
from training.serializers import TrainingTypeSerializer


@login_required
def take_training(request, training_id=None):

    if request.method == 'POST':
        if request.POST.get('training_type'):
            return redirect('platform_training', request.POST['training_type'])
        # TODO remove the block below once the new view takes care of all aspects
        op_training = OnPlatformTraining.objects.select_related('training_type').filter(
            training_type__id=training_id).last()

        # check if the questions are answered correctly
        try:
            user_question_answers = json.loads(request.POST['question_answers'])
            # convert the keys to int(javascript sends them as string)
            user_question_answers = {int(k): v for k, v in user_question_answers.items()}
            for question in op_training.quizzes.all():
                correct_answer = question.choices.filter(is_correct=True).first().id
                if (question.id not in user_question_answers
                        or user_question_answers.get(question.id) != correct_answer):
                    messages.error(request, 'Please answer all questions correctly.')
                    return redirect("edit_training")

        except json.JSONDecodeError:
            messages.error(request, 'Please submit the training correctly.')
            return redirect("edit_training")

        # save a training object to database in Training
        training = Training()
        slug = get_random_string(20)
        while Training.objects.filter(slug=slug).exists():
            slug = get_random_string(20)

        training.slug = slug
        training.training_type = op_training.training_type
        training.user = request.user
        training.process_datetime = timezone.now()
        training.status = TrainingStatus.ACCEPTED
        training.save()

        training_questions = []
        for question in op_training.training_type.questions.all():
            training_questions.append(TrainingQuestion(training=training, question=question))

        TrainingQuestion.objects.bulk_create(training_questions)

        messages.success(
            request, f'Congratulations! You completed the training {op_training.training_type.name} successfully.')

        return redirect("edit_training",)

    training = OnPlatformTraining.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()

    return render(request, 'training/op_training.html', {
        'modules': sorted(chain(training.modules.all()), key=operator.attrgetter('order')),
        'training': training,
    })


@login_required
def take_module_training(request, training_id, module_id):
    # Todo add a check to ensure that the user has completed all the previous modules
    # this will be implemented with the resume training feature
    # this is needed for both post and get requests

    if request.method == 'POST':
        op_training = OnPlatformTraining.objects.select_related('training_type').filter(
            training_type__id=training_id).last()
        module = op_training.modules.filter(pk=module_id).first()

        # check if the questions are answered correctly
        try:
            user_question_answers = json.loads(request.POST['question_answers'])
            # convert the keys to int(javascript sends them as string)
            user_question_answers = {int(k): v for k, v in user_question_answers.items()}
            for question in module.quizzes.all():
                correct_answer = question.choices.filter(is_correct=True).first().id
                if (question.id not in user_question_answers
                        or user_question_answers.get(question.id) != correct_answer):
                    messages.error(request, 'Please answer all questions correctly.')
                    return redirect('platform_training', request.POST['training_type'])

        except json.JSONDecodeError:
            messages.error(request, 'Please submit the training correctly.')
            return redirect('platform_training', request.POST['training_type'])

        # only save a training object to database in Training if it is the last module
        if module == op_training.modules.last():
            training = Training()
            slug = get_random_string(20)
            while Training.objects.filter(slug=slug).exists():
                slug = get_random_string(20)

            training.slug = slug
            training.training_type = op_training.training_type
            training.user = request.user
            training.process_datetime = timezone.now()
            training.status = TrainingStatus.ACCEPTED
            training.save()

            training_questions = []
            for question in op_training.training_type.questions.all():
                training_questions.append(TrainingQuestion(training=training, question=question))

            TrainingQuestion.objects.bulk_create(training_questions)

            messages.success(
                request, f'Congratulations! You completed the training {op_training.training_type.name} successfully.')
        else:
            messages.success(
                request, f'Congratulations! You completed the module {module.name} successfully.')
            # Todo implement the resume training feature
            return redirect('platform_training', request.POST['training_type'])

        return redirect('platform_training', request.POST['training_type'])

    training = OnPlatformTraining.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()

    module = training.modules.get(id=module_id)
    return render(request, 'training/quiz.html', {
        'quiz_content': sorted(chain(
            module.quizzes.all(), module.contents.all()),
            key=operator.attrgetter('order')),
        'quiz_answer': module.quizzes.filter(choices__is_correct=True).values_list("id", "choices"),
        'module': module,
        'training': training,
    })


@permission_required('physionet.change_onplatformtraining', raise_exception=True)
def on_platform_training(request):

    if request.POST:

        if request.POST.get('training_id') != "-1":
            training_type = get_object_or_404(TrainingType, pk=request.POST.get('training_id'))
        else:
            training_type = None

        json_file = request.FILES.get("json_file", "")

        if not json_file.name.endswith('.json'):
            messages.error(request, 'File is not of JSON type')
            return redirect("create_training")
        file_data = JSONParser().parse(json_file.file)
        serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
        if serializer.is_valid(raise_exception=False):
            serializer.save()
            messages.success(request, 'On platform training created successfully.')
        else:
            messages.error(request, serializer.errors)

        return redirect("op_training")

    training_types = TrainingType.objects.filter(required_field=RequiredField.PLATFORM)
    return render(
        request,
        'console/training_type/index.html',
        {
            'training_types': training_types,
            'training_type_nav': True,
        })
