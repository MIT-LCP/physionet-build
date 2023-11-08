from hmac import new
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
from project.validators import validate_version

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, TrainingQuestion, RequiredField
from user.enums import TrainingStatus

from training.models import Course, Quiz, QuizChoice, ContentBlock
from training.models import CourseProgress, ModuleProgress, CompletedContent, CompletedQuiz
from training.serializers import TrainingTypeSerializer


# Utility Functions
def is_major_change(version1, version2):
    """
    This function takes two version numbers as input parameters,
    and returns True if the first digit of the version number is changed,
    else returns False.
    """
    version1_first_digit = int(str(version1).split('.', maxsplit=1)[0])
    version2_first_digit = int(str(version2).split('.', maxsplit=1)[0])
    if version1_first_digit != version2_first_digit:
        return True
    return False


@permission_required('training.change_course', raise_exception=True)
def courses(request):
    """
    View function for managing courses.
    Allows creation and updating of courses for a given training type.
    """
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
            existing_course_version = existing_course.order_by('-version').first().version
            new_course_version = file_data['courses'][0]['version']
            # checking if the new course file has a valid version
            if not validate_version(file_data['courses'][0]['version']):
                messages.error(request, 'Version number is not valid.')
            # checking if the version number is greater than the existing version
            elif float(file_data['courses'][0]['version']
                       ) <= float(existing_course.order_by('-version').first().version):
                messages.error(request, 'Version number should be greater than the existing version.')
            else:
                serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
                if serializer.is_valid(raise_exception=False):
                    if is_major_change(new_course_version,
                                       existing_course_version):
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
    """
    This view takes a primary key and a version number as input parameters,
    and returns a JSON response containing information about the
    training course with the specified primary key and version number.
    """
    training_type = get_object_or_404(TrainingType, pk=pk)
    version = float(version)
    if training_type.required_field != RequiredField.PLATFORM:
        messages.error(request, 'Only onplatform course can be downloaded')
        return redirect('courses')

    serializer = TrainingTypeSerializer(training_type)
    response_data = serializer.data
    response = JsonResponse(response_data, safe=False, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename={training_type.name}--version-{version}.json'
    return response
