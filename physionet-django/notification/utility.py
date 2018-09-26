"""
Module for generating notifications
"""
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader


def submit_notify(project):
    """
    Notify authors when a project is submitted
    """
    subject = 'Submission of project: {}'.format(project.title)
    email_context = {'project':project}
    for email, name in project.get_author_info():
        email_context['name'] = name
        body = loader.render_to_string(
            'project/email/submit_notify.html', email_context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                          [email], fail_silently=False)


def assign_editor_notify(submission):
    """
    Notify authors when an editor is assigned
    """
    subject = 'Editor assigned to submission of project: {0}'.format(
        submission.project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/assign_editor_notify.html',
            {'name':name, 'project':submission.project,
             'editor':submission.editor})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def edit_reject_notify(submission):
    """
    Notify authors when an editor rejects a submission
    """
    subject = 'Submission rejected for project {0}'.format(project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/reject_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def edit_resubmit_notify(submission):
    """
    Notify authors when an editor requests a resubmission
    """
    subject = 'Resubmission request for project {0}'.format(
        submission.project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/resubmit_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def edit_accept_notify(submission):
    """
    Notify authors when an editor accepts a submission
    """
    subject = 'Submission accepted for project: {0}'.format(
        submission.project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/accept_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def copyedit_complete_notify(submission):
    """
    Notify authors when the copyedit stage is complete
    """
    subject = 'Copyedit complete for project: {0}'.format(
        submission.project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/copyedit_complete_notify.html',
            {'name':name, 'project':project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)
