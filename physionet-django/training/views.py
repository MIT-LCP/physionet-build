from calendar import c
from hmac import new
import json
import operator
from itertools import chain
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from project.validators import validate_version, is_version_greater

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, TrainingQuestion, RequiredField
from user.enums import TrainingStatus

from training.models import Course, Quiz, QuizChoice, ContentBlock
from training.models import CourseProgress, ModuleProgress, CompletedContent, CompletedQuiz
from training.serializers import TrainingTypeSerializer, CourseSerializer


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
            if validate_version(new_course_version) is not None:
                messages.error(request, 'Version number is not valid.')
            # checking if the version number is greater than the existing version
            elif not is_version_greater(new_course_version, existing_course_version):
                messages.error(request, 'Version number should be greater than the existing version.')
            else:
                serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
                if serializer.is_valid(raise_exception=False):
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
def course_details(request, pk):
    """
    View function for managing courses.
    Allows managing the version of the courses for a given training type.
    Allows expiring the specific version of the course.
    """
    training_type = get_object_or_404(TrainingType, pk=pk)
    active_course_versions = Course.objects.filter(training_type=training_type, is_active=True).order_by('-version')
    inactive_course_versions = Course.objects.filter(training_type=training_type, is_active=False).order_by('-version')
    return render(
        request,
        'console/training_type/course_details.html',
        {
            'training_type': training_type,
            'active_course_versions': active_course_versions,
            'inactive_course_versions': inactive_course_versions,
            'training_type_nav': True,
        })


@permission_required('training.change_course', raise_exception=True)
def expire_course(request, pk, version):
    """
    This view takes a primary key and a version number as input parameters,
    and expires the course with the specified primary key and version number.
    """
    course = Course.objects.filter(training_type__pk=pk, version=version).first()
    number_of_days = request.POST.get('number_of_days')
    if not course:
        messages.error(request, 'Course not found')
        return redirect('courses')
    if not number_of_days:
        messages.error(request, 'Number of days is required')
        return redirect('course_details', pk=pk)
    course.expire_course_version(course.training_type, int(number_of_days))
    messages.success(request, 'Course expired successfully.')
    return redirect('course_details', pk=pk)


@permission_required('training.change_course', raise_exception=True)
def download_course(request, pk, version):
    """
    This view takes a primary key and a version number as input parameters,
    and returns a JSON response containing information about the
    training course with the specified primary key and version number.
    """
    course = Course.objects.filter(training_type__pk=pk, version=version).first()
    if not course:
        messages.error(request, 'Course not found')
        return redirect('courses')
    training_type = course.training_type
    if training_type.required_field != RequiredField.PLATFORM:
        messages.error(request, 'Only onplatform course can be downloaded')
        return redirect('courses')

    serializer = CourseSerializer(course)
    response_data = serializer.data
    response = JsonResponse(response_data, safe=False, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename={training_type.name}--version-{version}.json'
    return response
