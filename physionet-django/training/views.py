import json
import operator
from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, TrainingQuestion, RequiredField
from user.enums import TrainingStatus

from training.models import OnPlatformTraining, Quiz, QuizChoice, ContentBlock
from training.models import OnPlatformTrainingProgress, ModuleProgress, CompletedContent, CompletedQuiz
from training.serializers import TrainingTypeSerializer


@login_required
def take_training(request, training_id=None):

    if request.method == 'POST':
        if request.POST.get('training_type'):
            return redirect('platform_training', request.POST['training_type'])

        return redirect("edit_training")

    training = OnPlatformTraining.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()
    modules = sorted(chain(training.modules.all()), key=operator.attrgetter('order'))
    # get the progress of the user for the modules, updated_date
    training_progress = OnPlatformTrainingProgress.objects.filter(user=request.user, training__id=training.id).last()
    for module in modules:
        module_progress = training_progress.module_progresses.filter(module_id=module.id).last()
        if module_progress:
            module.progress_status = module_progress.get_status_display()
            module.progress_updated_date = module_progress.updated_datetime
        else:
            module.progress_status = 'Not Started'
            module.progress_updated_date = None
    return render(request, 'training/op_training.html', {
        'modules': modules,
        'training': training,
        'ModuleStatus': ModuleProgress.Status,
    })


@login_required
def take_module_training(request, training_id, module_id):
    op_training = OnPlatformTraining.objects.select_related('training_type').filter(
        training_type__id=training_id).last()
    module = op_training.modules.filter(pk=module_id).first()

    training_progress = OnPlatformTrainingProgress.objects.filter(user=request.user, training__id=op_training.id).last()
    if not training_progress:
        training_progress = OnPlatformTrainingProgress.objects.create(user=request.user, training_id=op_training.id)

    # mandate the user to complete all the previous modules before starting the requested module
    next_module = training_progress.get_next_module()
    if next_module and next_module.id < int(module_id):
        messages.error(request, 'Please complete the previous modules before starting this module.')
        return redirect('platform_training', training_id)

    if request.method == 'POST':

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

        # update the module progress
        module_progress = training_progress.module_progresses.filter(module_id=module_id).last()
        module_progress.status = ModuleProgress.Status.COMPLETED
        module_progress.save()

        # only save a training object to database in Training if it is the last module
        if module == op_training.modules.last():
            training_progress.status = OnPlatformTrainingProgress.Status.COMPLETED
            training_progress.save()
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
            return redirect('platform_training', op_training.training_type.id)

        return redirect('platform_training', op_training.training_type.id)

    training = OnPlatformTraining.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()

    # we shouldn't use the next_module here as users might request to review a completed module
    requested_module = training.modules.get(id=module_id)

    # find the content or quiz to be displayed
    resume_content_or_quiz_module = training_progress.module_progresses.filter(
        module=requested_module).last()
    if not resume_content_or_quiz_module:
        resume_content_or_quiz_from = 1
    else:
        resume_content_or_quiz_object = resume_content_or_quiz_module.get_next_content_or_quiz()
        resume_content_or_quiz_from = resume_content_or_quiz_object.order if resume_content_or_quiz_object else 1

    # get the ids of the completed contents and quizzes
    completed_contents = training_progress.module_progresses.filter(
        module=requested_module).values_list('completed_contents__content_id', flat=True)
    completed_contents_ids = [content for content in completed_contents if content]

    completed_quizzes = training_progress.module_progresses.filter(
        module=requested_module).values_list('completed_quizzes__quiz_id', flat=True)
    completed_quizzes_ids = [quiz for quiz in completed_quizzes if quiz]

    return render(request, 'training/quiz.html', {
        'quiz_content': sorted(chain(
            requested_module.quizzes.all(), requested_module.contents.all()),
            key=operator.attrgetter('order')),
        'quiz_answer': requested_module.quizzes.filter(choices__is_correct=True).values_list("id", "choices"),
        'module': requested_module,
        'training': training,
        'resume_content_or_quiz_from': resume_content_or_quiz_from,
        'completed_contents_ids': completed_contents_ids,
        'completed_quizzes_ids': completed_quizzes_ids,
    })


@login_required
def update_module_progress(request):
    if request.method == 'POST':
        training_id = request.POST.get('training_id')
        module_id = request.POST.get('module_id')
        update_type = request.POST.get('update_type')
        update_type_id = request.POST.get('update_type_id')

        if update_type not in ['content', 'quiz']:
            return JsonResponse({'detail': 'Unsupported update type'}, status=400)

        op_training_progress = OnPlatformTrainingProgress.objects.filter(
            user=request.user, training__id=training_id).last()
        module_progress = op_training_progress.module_progresses.filter(module__id=module_id).last()

        with transaction.atomic():
            if not module_progress:
                module_progress = ModuleProgress.objects.create(
                    training_progress=op_training_progress,
                    module_id=module_id)

            if update_type == 'content':
                completed_content = CompletedContent.objects.create(
                    module_progress=module_progress,
                    content_id=update_type_id)
                completed_content.save()
                module_progress.last_completed_order = completed_content.content.order

            elif update_type == 'quiz':
                completed_quiz = CompletedQuiz.objects.create(
                    module_progress=module_progress,
                    quiz_id=update_type_id)
                completed_quiz.save()
                module_progress.last_completed_order = completed_quiz.quiz.order
            module_progress.save()

            return JsonResponse({'detail': 'success'}, status=200)

    return JsonResponse({'detail': 'Unsupported request method'}, status=400)


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
