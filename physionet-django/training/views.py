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
    pass


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
