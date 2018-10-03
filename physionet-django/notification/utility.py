"""
Module for generating notifications
"""
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template import loader


RESPONSE_ACTIONS = {0:'rejected', 1:'accepted'}


# ---------- Project App ---------- #

def invitation_notify(request, invite_author_form, target_email):
    """
    Notify someone when they are invited to author a project
    """
    inviter = invite_author_form.inviter
    project = invite_author_form.project
    subject = 'Invitation to author project: {}'.format(project.title)
    email_context = {'inviter_name':inviter.get_full_name(),
                     'inviter_email':inviter.email,
                     'project':project,
                     'domain':get_current_site(request)}
    body = loader.render_to_string('project/email/invite_author.html',
                                    email_context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [target_email], fail_silently=False)


def invitation_response_notify(invitation, affected_emails):
    """
    Notify the submitting author when an invitation to join a project
    is processed.
    """
    response = RESPONSE_ACTIONS[invitation.response]
    project = invitation.project

    subject = 'Authorship invitation {} for project: {}'.format(response,
                                                                project.title)
    email, name = project.get_submitting_author_info()
    email_context = {'name':name, 'project':project,
        'response':response}
    # Send an email for each email belonging to the accepting user
    for author_email in affected_emails:
        email_context['author_email'] = author_email
        body = loader.render_to_string(
            'project/email/author_response.html', email_context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)

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


# ---------- Console App ---------- #

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


def edit_reject_notify(request, submission):
    """
    Notify authors when an editor rejects a submission
    """
    project = submission.project
    subject = 'Submission rejected for project {0}'.format(project.title)
    for email, name in project.get_author_info():
        body = loader.render_to_string(
            'console/email/reject_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def edit_resubmit_notify(request, submission):
    """
    Notify authors when an editor requests a resubmission
    """
    project = submission.project
    subject = 'Resubmission request for project {0}'.format(project.title)
    for email, name in project.get_author_info():
        body = loader.render_to_string(
            'console/email/resubmit_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def edit_accept_notify(request, submission):
    """
    Notify authors when an editor accepts a submission
    """
    project = submission.project
    subject = 'Submission accepted for project: {0}'.format(project.title)
    for email, name in project.get_author_info():
        body = loader.render_to_string(
            'console/email/accept_submission_notify.html',
            {'name':name, 'project':project,
             'editor_comments':submission.editor_comments,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def copyedit_complete_notify(request, submission):
    """
    Notify authors when the copyedit stage is complete
    """
    project = submission.project
    subject = 'Copyedit complete for project: {0}'.format(project.title)
    for email, name in submission.project.get_author_info():
        body = loader.render_to_string(
            'console/email/copyedit_complete_notify.html',
            {'name':name, 'project':project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def publish_notify(request, project, published_project):
    """
    Notify authors when a project is published
    """
    subject = 'Your project has been published: {0}'.format(
        published_project.title)
    for email, name in project.get_author_info():
        body = loader.render_to_string(
            'console/email/publish_notify.html',
            {'name':name, 'published_project':published_project,
             'domain':get_current_site(request)})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [email], fail_silently=False)


def storage_response_notify(storage_request):
    """
    Notify submitting author when storage request is processed
    """
    project = storage_request.project
    response = RESPONSE_ACTIONS[storage_request.response]
    subject = 'Storage request {0} for project: {1}'.format(response,
        project.title)
    email, name = project.get_submitting_author_info()
    body = loader.render_to_string('console/email/storage_response_notify.html',
        {'name':name, 'project':project, 'response':response,
         'allowance':storage_request.request_allowance,
         'response_message':storage_request.response_message})
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [email], fail_silently=False)

