from django.db import IntegrityError
from django.test import TestCase

from challenge.enums import DatasetType
from challenge.models import Challenge, LeaderboardEntry, Submission, Team
from project.models import PublishedProject
from user.models import User


class TestLeaderboardEntryConstraints(TestCase):
    def setUp(self):
        self.user = User.objects.get(username='rgmark')
        self.challenge = Challenge.objects.create(
            published_project=PublishedProject.objects.first(),
            slug='test-challenge',
            organizer=self.user,
        )
        self.submission = Submission.objects.create(
            challenge=self.challenge,
            submitted_by=self.user,
            code_archive_gcs_uri='gs://bucket/archive.zip',
        )
        self.team = Team.objects.create(challenge=self.challenge, name='Team A')

    def create_entry(self, **kwargs):
        return LeaderboardEntry.objects.create(
            challenge=self.challenge,
            submission=self.submission,
            dataset=DatasetType.VAL,
            primary_score=0.5,
            **kwargs,
        )

    def test_one_entry_per_user(self):
        self.create_entry(user=self.user)
        with self.assertRaises(IntegrityError):
            self.create_entry(user=self.user)

    def test_one_entry_per_team(self):
        self.create_entry(team=self.team)
        with self.assertRaises(IntegrityError):
            self.create_entry(team=self.team)

    def test_requires_team_or_user(self):
        with self.assertRaises(IntegrityError):
            self.create_entry()

    def test_rejects_team_and_user(self):
        with self.assertRaises(IntegrityError):
            self.create_entry(team=self.team, user=self.user)
