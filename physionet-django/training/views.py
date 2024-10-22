import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.http import Http404
from django.urls import reverse
from django.db import transaction

from project.validators import validate_version, is_version_greater

from rest_framework.parsers import JSONParser

from user.models import Training, TrainingType, RequiredField
from user.enums import TrainingStatus

from training.models import Course, Quiz, QuizChoice, ContentBlock, Module
from training.models import CourseProgress, ModuleProgress, CompletedContent, CompletedQuiz
from training.serializers import CourseSerializer
from console.views import console_permission_required


# Defining few utility functions to help with the views
def get_course_and_module(training_slug, module_order):
    """
    This function takes a training slug and a module order as input parameters,
    and returns the course and module objects associated with the training slug and module order.
    """
    course = Course.objects.filter(training_type__slug=training_slug, is_active=True).order_by('version').last()
    if course is None:
        raise Http404()
    module = get_object_or_404(course.modules, order=module_order)
    return course, module


def get_course_and_module_progress(user, course, module_order):
    """
    This function takes a user, course, and module order as input parameters,
    and returns the course progress and module progress objects associated with the user, course, and module order.
    """
    # get the course progress of the user for the course
    course_progress = CourseProgress.objects.filter(user=user, course=course).first()
    if not course_progress:
        course_progress = CourseProgress.objects.create(user=user, course=course)
        # Initiate the training and set the status to review
        slug = get_random_string(20)
        while Training.objects.filter(slug=slug).exists():
            slug = get_random_string(20)
        Training.objects.create(
            slug=slug,
            training_type=course.training_type,
            user=user,
            course=course,
            process_datetime=timezone.now(),
            status=TrainingStatus.REVIEW
        )


    module = get_object_or_404(course.modules, order=module_order)
    module_progress, _ = ModuleProgress.objects.get_or_create(course_progress=course_progress, module=module)
    return course_progress, module_progress


def handle_quiz_submission(quiz, choice_id):
    """
    This function takes a module progress, quiz, and choice ID as input parameters,
    and checks if the choice ID is correct for the quiz.
    """
    correct_choice = QuizChoice.objects.filter(quiz=quiz, is_correct=True).first()
    if correct_choice.id != int(choice_id):
        return False
    return True


def update_module_progress(module_progress, order):
    """
    This function takes a module progress and an order as input parameters,
    and updates the last completed order of the module progress if the order is greater than the last completed
    """
    if order > module_progress.last_completed_order:
        module_progress.last_completed_order = order
        module_progress.save()


def get_min_max_order_in_module(module):
    """
    This function takes a module as input parameter and returns the minimum and maximum order of the module.
    """
    # calculating the max and min order of the module
    module_blocks = ContentBlock.objects.filter(module=module).values_list('order', flat=True)
    quiz_blocks = Quiz.objects.filter(module=module).values_list('order', flat=True)
    module_max_order = max(max(module_blocks, default=0), max(quiz_blocks, default=0))
    module_min_order = min(min(module_blocks, default=0), min(quiz_blocks, default=0))
    return module_min_order, module_max_order


def handle_course_completion(course, course_progress):
    """
    This function takes a course and course progress as input parameters,
    and handles the course completion by updating the course progress status to completed
    """
    with transaction.atomic():
        course_progress.status = CourseProgress.Status.COMPLETED
        course_progress.save()
        training = Training.objects.filter(course=course, user=course_progress.user).first()
        training.status = TrainingStatus.ACCEPTED
        training.save()


def handle_module_completion(course, module_progress):
    """
    This function takes a course and module progress as input parameters,
    and handles the module completion by updating the module progress status to completed
    """
    module_progress.status = ModuleProgress.Status.COMPLETED
    module_progress.save()


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
            return redirect("course_details", training_slug)

        # Checking if the content of the JSON file is properly formatted and according to the schema
        try:
            file_data = JSONParser().parse(json_file.file)
        except json.decoder.JSONDecodeError:
            messages.error(request, 'JSON file is not properly formatted.')
            return redirect("course_details", training_slug)

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

        return redirect("course_details", training_slug)

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
def archive_course(request, training_slug, version):
    """
    This view takes a primary key and a version number as input parameters,
    and archives the course with the specified primary key and version number.
    """
    course = Course.objects.filter(training_type__slug=training_slug, version=version).first()
    if not course:
        messages.error(request, 'Course not found')
        return redirect('courses')
    course.archive_course_version()
    messages.success(request, 'Course archived successfully.')
    return redirect('course_details', training_slug)


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


@login_required
def take_training(request, training_slug):
    """
    Handles the display of a user's training course and their progress.

    This view performs the following tasks:
    - Retrieves the active course based on the provided training slug.
    - Retrieves the modules associated with the course.
    - Retrieves or creates the user's course progress.
    - Retrieves or creates the user's module progress for each module.
    - Updates the module's progress status and last completed order.
    - Renders the training course page with the course and module details.

    Input Required:
    - training_slug: The slug of the training course.

    Returns:
    - A rendered template displaying the training course and module progress.
    """

    course = Course.objects.filter(training_type__slug=training_slug, is_active=True).order_by('version').last()
    if course is None:
        raise Http404()
    modules = Module.objects.filter(course=course).order_by('order')
    course_progress, _ = get_course_and_module_progress(request.user, course, modules.first().order)

    for module in modules:
        module_progress = course_progress.module_progresses.filter(module_id=module.id).last()
        if module_progress:
            module.progress_status = module_progress.get_status_display()
            module.progress_updated_date = module_progress.updated_at
            # if the module is completed, then put the last completed order as 1
            # Else put it as the last_completed_order
            if module_progress.status == ModuleProgress.Status.COMPLETED:
                module.last_completed_order = 1
            else:
                module.last_completed_order = module_progress.last_completed_order
        else:
            module.progress_status = 'Not Started'
            module.progress_updated_date = None
            module.last_completed_order = 1

    return render(request, 'training/course.html', {
        'course': course,
        'modules': modules,
        'ModuleStatus': ModuleProgress.Status,
    })


@login_required
def current_module_block(request, training_slug, module_order, order):
    """
    Handles the display and progression of a user's current module block in a training course.

    This view performs the following tasks:
    - Retrieves the course, module, course progress, and module progress based on the provided input.
    - Ensures the requested order is within the valid range of the module's content and quizzes.
    - Handles POST requests to update the user's progress when they complete a quiz or content block.
    - Redirects the user to the appropriate next block or module upon completion.
    - Renders the current module block (quiz or content) for GET requests.

    Input Required:
    - training_slug: The slug of the training course.
    - module_order: The order of the module within the course.
    - order: The order of the content block or quiz within the module.

    Returns:
    - A redirect to the appropriate module block or training page upon completion.
    - A rendered template displaying the current module block for GET requests.
    """

    # get the course, module, course_progress, module_progress
    course, module = get_course_and_module(training_slug, module_order)
    course_progress, module_progress = get_course_and_module_progress(request.user, course, module_order)

    # get the minimum and maximum order in the module
    module_minimum_order, module_maximum_order = get_min_max_order_in_module(module)

    # if the order is greater than the next available object in the order, redirect to the last completed order
    next_object = module_progress.get_next_content_or_quiz()
    if next_object and order > next_object.order:
        return redirect('current_module_block', training_slug,
                        module_order, module_progress.get_next_content_or_quiz().order)

    # if the order is smaller than the minimum order, redirect to the minimum order
    if order < module_minimum_order:
        return redirect('current_module_block', training_slug, module_order, module_minimum_order)

    # check if this is a post request, if so, handle the update of the submission
    if request.method == 'POST':
        # if it contains choice, then it is a quiz
        if 'choice' in request.POST:
            choice_id = request.POST.get('choice')
            current_block = Quiz.objects.filter(module=module, order=order).first()
            if not handle_quiz_submission(current_block, choice_id):
                messages.error(request, 'Please select the correct choice.')
                return redirect('current_module_block', training_slug, module_order, order)
            CompletedQuiz.objects.get_or_create(module_progress=module_progress, quiz=current_block)
            update_module_progress(module_progress, order)
        else:
            current_block = ContentBlock.objects.filter(module=module, order=order).first()
            CompletedContent.objects.get_or_create(module_progress=module_progress, content=current_block)
            update_module_progress(module_progress, order)
        if order == module_maximum_order:
            handle_module_completion(course, module_progress)
            if module == course.modules.last():
                handle_course_completion(course, course_progress)
                messages.success(request, f'Congratulations! You completed the training '
                                          f'{course.training_type.name} successfully.')
            return redirect('platform_training', training_slug)
        return redirect('current_module_block', training_slug, module_order, order + 1)

    current_block = Quiz.objects.filter(module=module, order=order).first()
    if current_block:
        block_type = 'quiz'
        choices = QuizChoice.objects.filter(quiz=current_block)
    else:
        current_block = ContentBlock.objects.filter(module=module, order=order).first()
        block_type = 'content'
        choices = None

    # get the previous module link using reverse function
    previous_block = reverse("platform_training", args=[training_slug]) if order < 2 else \
        reverse("current_module_block", args=[training_slug, module_order, order - 1])

    return render(request, 'training/course_block.html', {
        'current_block': current_block,
        'choices': choices,
        'type': block_type,
        'module': module,
        'course': course,
        'previous_block': previous_block,
    })
