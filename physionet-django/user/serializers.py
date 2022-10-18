from project.models import ActiveProject, ArchivedProject
from rest_framework import serializers

from .models import (CloudInformation, CredentialApplication, CredentialReview,
                     Event, EventParticipant, Orcid, Profile, Training, User)


class OrcidSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orcid
        fields = '__all__'


class CredentialApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CredentialApplication
        fields = '__all__'


class CredentialReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = CredentialReview
        fields = '__all__'


class TrainingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Training
        fields = '__all__'


class CloudInformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudInformation
        fields = '__all__'


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = '__all__'


class EventParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventParticipant
        fields = '__all__'


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id','email','username','join_date','is_credentialed','credential_datetime')
        order_by = ('id')

class ActiveProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActiveProject
        fields = '__all__'

class ArchivedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivedProject
        fields = '__all__'        

class UserDetailSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(many=False, read_only=True)
    orcid = OrcidSerializer(many=False, read_only=True)
    credential_applications = CredentialApplicationSerializer(many=True, read_only=True)
    credential_review = CredentialReviewSerializer(many=True, read_only=True)
    trainings = TrainingSerializer(many=True, read_only=True)
    cloud_information = CloudInformationSerializer(many=True, read_only=True)
    active_projects = ActiveProjectSerializer(many=True, read_only=True)
    archived_projects = ArchivedProjectSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ('id','email','username','join_date','is_credentialed','credential_datetime','profile','orcid','credential_applications','credential_review','trainings','cloud_information', 'active_projects', 'archived_projects')
