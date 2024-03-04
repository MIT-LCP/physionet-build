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
from training.serializers import CourseSerializer
from console.views import console_permission_required


@permission_required('training.change_course', raise_exception=True)
@console_permission_required('training.change_course')
def courses(request):
    """
    View function for managing courses.
    Allows creation and updating of courses for a given training type.
    """
    if request.POST:

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

        serializer = CourseSerializer(data=file_data, partial=True)

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
@console_permission_required('training.change_course')
def course_details(request, training_slug):
    """
    View function for managing courses.
    Allows managing the version of the courses for a given training type.
    Allows expiring the specific version of the course.
    """
    if request.POST:
        training_type = get_object_or_404(TrainingType, slug=training_slug)
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
            latest_course = existing_course.order_by('-version').first()
            latest_course_version = existing_course.order_by('-version').first().version
            new_course_version = file_data['version']
            # checking if the new course file has a valid version
            if validate_version(new_course_version) is not None:
                messages.error(request, 'Version number is not valid.')
            # checking if the version number is greater than the existing version
            elif not is_version_greater(new_course_version, latest_course_version):
                messages.error(request, 'Version number should be greater than the existing version.')
            else:
                serializer = CourseSerializer(latest_course, data=file_data, partial=True)
                if serializer.is_valid(raise_exception=False):
                    serializer.save()
                    messages.success(request, 'Course updated successfully.')

        return redirect("course_details", slug=training_slug)

    training_type = get_object_or_404(TrainingType, slug=training_slug)
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
@console_permission_required('training.change_course')
def expire_course(request, training_slug, version):
    """
    This view takes a primary key and a version number as input parameters,
    and expires the course with the specified primary key and version number.
    """
    course = Course.objects.filter(training_type__slug=training_slug, version=version).first()
    expiry_date = request.POST.get('expiry_date')
    if not course:
        messages.error(request, 'Course not found')
        return redirect('courses')
    if not expiry_date:
        messages.error(request, 'Expiry Date is required')
        return redirect('course_details', slug=training_slug)
    # Checking if the expiry date is greater than the current date
    expiry_date_tz = timezone.make_aware(timezone.datetime.strptime(expiry_date, '%Y-%m-%d'))
    if expiry_date_tz < timezone.now():
        messages.error(request, 'Expiry Date should be greater than the current date')
        return redirect('course_details', slug=training_slug)
    # Calculating the number of days between the current date and the expiry date
    number_of_days = (expiry_date_tz - timezone.now()).days
    course.expire_course_version(course.training_type, int(number_of_days))
    messages.success(request, 'Course expired successfully.')
    return redirect('course_details', slug=training_slug)


@permission_required('training.change_course', raise_exception=True)
@console_permission_required('training.change_course')
def download_course(request, training_slug, version):
    """
    This view takes a primary key and a version number as input parameters,
    and returns a JSON response containing information about the
    training course with the specified primary key and version number.
    """
    training_type = get_object_or_404(TrainingType, slug=training_slug)
    course = training_type.courses.filter(version=version).first()
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
