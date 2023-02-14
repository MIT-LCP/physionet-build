import operator
from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Prefetch, Max, F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, TrainingQuestion
from user.enums import TrainingStatus

from training.models import OnPlatformTraining, QuizChoice, ContentBlock
from training.serializers import TrainingTypeSerializer


@login_required
def view_training(request):
    # filters by the max version
    training = OnPlatformTraining.objects.annotate(max_version=Max('version')).filter(version=F('max_version'))
    return render(request, 'training/training.html', {'training': training})


@login_required
def take_training(request, training_id=None):

    if request.method == 'POST':
        if request.POST.get('training_type'):
            return redirect('platform_training', request.POST['training_type'])

        op_training = get_object_or_404(
            OnPlatformTraining.objects.select_related('training'), pk=training_id)

        # save a training object to database in Training
        training = Training()
        slug = get_random_string(20)
        while Training.objects.filter(slug=slug).exists():
            slug = get_random_string(20)

        training.slug = slug
        training.training_type = op_training.training
        training.user = request.user
        training.process_datetime = timezone.now()
        training.status = TrainingStatus.ACCEPTED
        training.save()

        training_questions = []
        for question in op_training.training.questions.all():
            training_questions.append(TrainingQuestion(training=training, question=question))

        TrainingQuestion.objects.bulk_create(training_questions)

        messages.success(
            request, f'Congratulations! You completed the training {op_training.training.name} successfully.')

        return redirect("edit_training",)

    training = get_object_or_404(OnPlatformTraining.objects.prefetch_related(
        Prefetch("quizzes__choices", queryset=QuizChoice.objects.order_by("?")),
        Prefetch("contents", queryset=ContentBlock.objects.all())), pk=training_id)

    return render(request, 'training/quiz.html', {
        'quiz_content': sorted(chain(
            training.quizzes.all(), training.contents.all()),
            key=operator.attrgetter('order')),
        'quiz_answer': training.quizzes.filter(choices__is_correct=True).values_list("id", "choices")
    })


@permission_required('physionet.change_onplatformtraining', raise_exception=True)
def create_op_training(request, training_id=None):

    if training_id:
        training_type = get_object_or_404(TrainingType, pk=training_id)
        json_file = request.FILES.get("json_file", "")

        if not json_file.name.endswith('.json'):
            messages.error(request, 'File is not of JSON type')
            return redirect("create_training")
        file_data = JSONParser().parse(json_file.file)
        serializer = TrainingTypeSerializer(training_type, data=file_data, partial=True)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        return redirect("trainings")

    training_types = TrainingType.objects.all()
    return render(
        request,
        'console/training_type/index.html',
        {'training_types': training_types, 'training_type_nav': True})
