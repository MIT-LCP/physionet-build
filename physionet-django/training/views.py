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

from training.models import Course, Quiz, QuizChoice, ContentBlock
from training.models import CourseProgress, ModuleProgress, CompletedContent, CompletedQuiz
from training.serializers import TrainingTypeSerializer


@login_required
def take_training(request, training_id=None):

    if request.method == 'POST':
        if request.POST.get('training_type'):
            return redirect('platform_training', request.POST['training_type'])

        return redirect("edit_training")

    course = Course.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()
    modules = sorted(chain(course.modules.all()), key=operator.attrgetter('order'))
    # get the progress of the user for the modules, updated_date
    course_progress = CourseProgress.objects.filter(user=request.user, course__id=course.id).last()
    if not course_progress:
        course_progress = CourseProgress.objects.create(user=request.user, course_id=course.id)

    for module in modules:
        module_progress = course_progress.module_progresses.filter(module_id=module.id).last()
        if module_progress:
            module.progress_status = module_progress.get_status_display()
            module.progress_updated_date = module_progress.updated_at
        else:
            module.progress_status = 'Not Started'
            module.progress_updated_date = None
    return render(request, 'training/course.html', {
        'modules': modules,
        'course': course,
        'ModuleStatus': ModuleProgress.Status,
    })


@login_required
def take_module_training(request, training_id, module_id):
    course = Course.objects.select_related('training_type').filter(
        training_type__id=training_id).last()
    module = course.modules.filter(pk=module_id).first()

    course_progress = CourseProgress.objects.filter(user=request.user, course__id=course.id).last()
    if not course_progress:
        course_progress = CourseProgress.objects.create(user=request.user, course_id=course.id)

    # mandate the user to complete all the previous modules before starting the requested module
    next_module = course_progress.get_next_module()
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
                    return redirect('platform_training', course.training_type.id)

        except json.JSONDecodeError:
            messages.error(request, 'Please submit the training correctly.')
            return redirect('platform_training', course.training_type.id)

        # update the module progress
        module_progress = course_progress.module_progresses.filter(module_id=module_id).last()

        if module_progress.status == ModuleProgress.Status.COMPLETED:
            messages.info(request, 'You have already completed this module.')
            return redirect('platform_training', course.training_type.id)

        module_progress.status = ModuleProgress.Status.COMPLETED
        module_progress.save()

        # only save a training object to database in Training if it is the last module
        if module == course.modules.last():
            course_progress.status = CourseProgress.Status.COMPLETED
            course_progress.save()
            training = Training()
            slug = get_random_string(20)
            while Training.objects.filter(slug=slug).exists():
                slug = get_random_string(20)

            training.slug = slug
            training.training_type = course.training_type
            training.user = request.user
            training.process_datetime = timezone.now()
            training.status = TrainingStatus.ACCEPTED
            training.save()

            training_questions = []
            for question in course.training_type.questions.all():
                training_questions.append(TrainingQuestion(training=training, question=question))

            TrainingQuestion.objects.bulk_create(training_questions)

            messages.success(
                request, f'Congratulations! You completed the training {course.training_type.name} successfully.')
        else:
            messages.success(
                request, f'Congratulations! You completed the module {module.name} successfully.')
            return redirect('platform_training', course.training_type.id)

        return redirect('platform_training', course.training_type.id)

    course = Course.objects.prefetch_related(
        Prefetch("modules__quizzes", queryset=Quiz.objects.order_by("?")),
        Prefetch("modules__contents", queryset=ContentBlock.objects.all())).filter(
            training_type__id=training_id).order_by('version').last()

    # we shouldn't use the next_module here as users might request to review a completed module
    requested_module = course.modules.get(id=module_id)

    # find the content or quiz to be displayed
    resume_content_or_quiz_module = course_progress.module_progresses.filter(
        module=requested_module).last()
    if not resume_content_or_quiz_module:
        resume_content_or_quiz_from = 1
    else:
        resume_content_or_quiz_object = resume_content_or_quiz_module.get_next_content_or_quiz()
        resume_content_or_quiz_from = resume_content_or_quiz_object.order if resume_content_or_quiz_object else 1

    # get the ids of the completed contents and quizzes
    completed_contents = course_progress.module_progresses.filter(
        module=requested_module).values_list('completed_contents__content_id', flat=True)
    completed_contents_ids = [content for content in completed_contents if content]

    completed_quizzes = course_progress.module_progresses.filter(
        module=requested_module).values_list('completed_quizzes__quiz_id', flat=True)
    completed_quizzes_ids = [quiz for quiz in completed_quizzes if quiz]

    return render(request, 'training/quiz.html', {
        'quiz_content': sorted(chain(
            requested_module.quizzes.all(), requested_module.contents.all()),
            key=operator.attrgetter('order')),
        'quiz_answer': requested_module.quizzes.filter(choices__is_correct=True).values_list("id", "choices"),
        'module': requested_module,
        'course': course,
        'resume_content_or_quiz_from': resume_content_or_quiz_from,
        'completed_contents_ids': completed_contents_ids,
        'completed_quizzes_ids': completed_quizzes_ids,
    })


@login_required
def update_module_progress(request):
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        module_id = request.POST.get('module_id')
        update_type = request.POST.get('update_type')
        update_type_id = request.POST.get('update_type_id')

        if update_type not in ['content', 'quiz']:
            return JsonResponse({'detail': 'Unsupported update type'}, status=400)

        course_progress = CourseProgress.objects.filter(
            user=request.user, course__id=course_id).last()
        module_progress = course_progress.module_progresses.filter(module__id=module_id).last()

        with transaction.atomic():
            if not module_progress:
                module_progress = ModuleProgress.objects.create(
                    course_progress=course_progress,
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


@permission_required('training.change_course', raise_exception=True)
def courses(request):
    if request.POST:

        if request.POST.get('training_id') != "-1":
            training_type = get_object_or_404(TrainingType, pk=request.POST.get('training_id'))
        else:
            training_type = None

        json_file = request.FILES.get("json_file", "")

        if not json_file.name.endswith('.json'):
            messages.warning(request, 'File is not of JSON type')
            return redirect("courses")

        # Checking if the content of the JSON file is properly formatted and according to the schema
        try:
            file_data = JSONParser().parse(json_file.file)
        except json.decoder.JSONDecodeError:
            messages.error(request, 'JSON file is not properly formatted.')
            return redirect("courses")
        
        # Checking if a course with the same name already exists
        existing_course = Course.objects.filter(training_type__name=file_data['name'])
        if existing_course.exists():
            messages.error(request, 'Course with the same name already exists.')
            return redirect("courses")

        # Checking if the Training type with the same version already exists
        existing_course = Course.objects.filter(training_type=training_type)
        if existing_course.exists():
            if not all(map(lambda x: x.isdigit() or x == '.', str(file_data['courses'][0]['version']))):
                messages.error(request, 'Version number is not valid.')
            elif file_data['courses'][0]['version'] <= existing_course.order_by(
                    '-version').first().version:  # Version Number is greater than the latest version
                messages.error(request, 'Version number should be greater than the latest version.')
            else:  # Checks passed and moving to saving the course
                serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
                if serializer.is_valid(raise_exception=False):
                    # A Major Version change is detected : The First digit of the version number is changed
                    if int(str(existing_course.order_by('-version').first().version).split('.')[0]) != int(str(
                            file_data['courses'][0]['version']).split('.')[0]):
                        # calling the update_course_for_major_version_change method to update the course
                        existing_course[0].update_course_for_major_version_change(training_type)
                    serializer.save()
                    messages.success(request, 'Course updated successfully.')
        else:
            serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
            if serializer.is_valid(raise_exception=False):
                serializer.save()
                messages.success(request, 'Course created successfully.')
            else:
                messages.error(request, serializer.errors)

        return redirect("courses")

    training_types = TrainingType.objects.filter(required_field=RequiredField.PLATFORM)
    return render(
        request,
        'console/training_type/index.html',
        {
            'training_types': training_types,
            'training_type_nav': True,
        })


@permission_required('training.change_course', raise_exception=True)
def download_course(request, pk, version):
    training_type = get_object_or_404(TrainingType, pk=pk)
    version = float(version)
    if training_type.required_field != RequiredField.PLATFORM:
        messages.error(request, 'Only onplatform course can be downloaded')
        return redirect('courses')

    serializer = TrainingTypeSerializer(training_type)
    response_data = serializer.data
    response_data['courses'] = list(filter(lambda x: x['version'] == version, response_data['courses']))
    response = JsonResponse(response_data, safe=False, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename={training_type.name}--version-{version}.json'
    return response
