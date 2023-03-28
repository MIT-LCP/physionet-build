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
        file_data = JSONParser().parse(json_file.file)
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
