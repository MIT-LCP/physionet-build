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

from training.models import OnPlatformTraining, QuizChoice, ContentBlock
from training.serializers import TrainingTypeSerializer


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
