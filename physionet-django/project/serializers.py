# from user.models import User
from rest_framework import serializers

from .models import ActiveProject, ArchivedProject


class ActiveProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActiveProject
        fields = '__all__'

class ArchivedProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivedProject
        fields = '__all__'

    