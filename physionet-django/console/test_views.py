import os
import pdb

from django.test import TestCase
from django.urls import reverse

from project.models import (ArchivedProject, ActiveProject, PublishedProject,
    Author, AuthorInvitation, License, StorageRequest)
from user.models import User
from user.test_views import prevent_request_warnings, TestMixin


class TestState(TestMixin, TestCase):
    """
    Test that all objects are in their intended states, during and
    after review/publication state transitions.

    """
    fixtures = ['demo-user', 'demo-project', 'site-data']

    def test_assign_editor(self):
        """
        Assign an editor
        """
        # Submit project
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        # Assign editor
        self.client.login(username='admin', password='Tester11!')
        editor = User.objects.get(username='admin')
        response = self.client.post(reverse(
            'submitted_projects'), data={'project':project.id,
            'editor':editor.id})
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(project.editor, editor)
        self.assertEqual(project.submission_status, 20)

    def test_edit_reject(self):
        """
        Edit a project, rejecting it.
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Reject submission
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':0, 'well_described':0, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Just bad.', 'decision':0
            })
        self.assertTrue(ArchivedProject.objects.filter(slug=project.slug))
        self.assertFalse(ActiveProject.objects.filter(slug=project.slug))

    def test_edit(self):
        """
        Edit a project. Request resubmission, then accept.
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Revise with changes
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Remove the phi.', 'decision':1
            })
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.author_editable())
        # Resubmit
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.post(reverse(
            'project_submission', args=(project.slug,)),
            data={'resubmit_project':''})
        # Accept. All quality control fields must be True
        self.client.login(username='admin', password='Tester11!')
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Good.', 'decision':2
            })
        self.assertMessage(response, 40)
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':1, 'reusable':1, 'no_phi':1,
            'pn_suitable':1, 'editor_comments':'Good.', 'decision':2
            })
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.copyeditable())

    @prevent_request_warnings
    def test_copyedit(self):
        """
        Copyedit a project
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Test that the editor cannot copyedit the content yet
        topic = project.topics.all().first()
        response = self.client.post(reverse(
            'edit_metadata_item', args=(project.slug,)), data={
            'item':'topic', 'remove_id':topic.id})
        self.assertEqual(response.status_code, 404)
        # Accept submission
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':1, 'reusable':1, 'no_phi':1,
            'pn_suitable':1, 'editor_comments':'Good.', 'decision':2
            })
        # Copyedit project.
        # Remove a related item
        response = self.client.post(reverse(
            'edit_metadata_item', args=(project.slug,)), data={
            'item':'topic', 'remove_id':topic.id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(project.topics.all().filter(id=topic.id))
        # Delete folders
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'delete_items':'', 'subdir':'', 'items':['subject-100',
            'subject-101']})
        self.assertMessage(response, 25)
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(),
            'subject-100')))
        # Complete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':1,
            'changelog_summary':'Removed your things'})
        project = ActiveProject.objects.get(id=project.id)
        self.assertFalse(project.copyeditable())
        # Reopen copyedit
        response = self.client.post(reverse(
            'awaiting_authors', args=(project.slug,)),
            data={'reopen_copyedit':''})
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.copyeditable())
        # Recomplete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':1,
            'changelog_summary':'Removed your things'})
        project = ActiveProject.objects.get(id=project.id)
        self.assertFalse(project.copyeditable())

    def test_approve_publish(self):
        """
        Author approves publication
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Accept submission
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':1, 'reusable':1, 'no_phi':1,
            'pn_suitable':1, 'editor_comments':'Good.', 'decision':2
            })
        # Complete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':0})
        # Approve publication
        self.assertFalse(ActiveProject.objects.get(id=project.id).is_publishable())
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.post(reverse(
            'project_submission', args=(project.slug,)),
            data={'approve_publication':''})
        self.assertTrue(ActiveProject.objects.get(id=project.id).is_publishable())

    def test_publish(self):
        """
        Test publishing project
        """
        # Get the project ready to publish
        self.test_approve_publish()
        self.client.login(username='admin', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project_slug = project.slug
        custom_slug = 'mitbih'

        # Try to publish with an already taken slug
        taken_slug = PublishedProject.objects.all().first().slug
        response = self.client.post(reverse(
            'publish_submission', args=(project.slug,)),
            data={'slug':taken_slug, 'doi':'10.13026/MIT505', 'make_zip':1})
        self.assertTrue(bool(ActiveProject.objects.filter(slug=project_slug)))

        # Publish with a valid custom slug
        response = self.client.post(reverse(
            'publish_submission', args=(project.slug,)),
            data={'slug':custom_slug, 'doi':'10.13026/MIT505', 'make_zip':1})
        self.assertTrue(bool(PublishedProject.objects.filter(slug=custom_slug)))
        self.assertFalse(bool(PublishedProject.objects.filter(slug=project_slug)))
        self.assertFalse(bool(ActiveProject.objects.filter(slug=project_slug)))

        project = PublishedProject.objects.get(slug=custom_slug)
        # Access the published project's page and its (open) files
        response = self.client.get(reverse('published_project',
            args=(project.slug, project.version)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_published_project_file', args=(
            project.slug, project.version, 'subject-100/100.atr')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_published_project_zip', args=(
            project.slug, project.version)))
        self.assertEqual(response.status_code, 200)
        # Access the submission log as the author
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('published_submission_history',
            args=(project.slug, project.version,)))
        self.assertEqual(response.status_code, 200)
