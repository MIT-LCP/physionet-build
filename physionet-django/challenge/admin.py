from django.contrib import admin

from challenge import models


@admin.register(models.ChallengeConfiguration)
class ChallengeConfigurationAdmin(admin.ModelAdmin):
    list_display = ('active_project', 'start_datetime', 'end_datetime', 'primary_metric_name')
    search_fields = ('active_project__title',)


@admin.register(models.Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ('slug', 'organizer', 'phase', 'is_active', 'start_datetime', 'official_start_datetime', 'end_datetime')
    list_filter = ('phase', 'is_active')
    search_fields = ('slug', 'organizer__username')


@admin.register(models.SubmissionSpec)
class SubmissionSpecAdmin(admin.ModelAdmin):
    list_display = ('challenge', 'base_image', 'primary_metric_name')


@admin.register(models.ChallengeParticipant)
class ChallengeParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'challenge', 'team', 'is_team_captain', 'is_active')
    list_filter = ('is_active', 'is_team_captain')
    search_fields = ('user__username', 'challenge__slug')


@admin.register(models.Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'challenge', 'is_active', 'created_datetime')
    list_filter = ('is_active',)
    search_fields = ('name', 'challenge__slug')


@admin.register(models.TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ('team', 'email', 'invited_by', 'response', 'is_active')
    list_filter = ('is_active', 'response')


@admin.register(models.Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('pk', 'challenge', 'submitted_by', 'status', 'created_datetime')
    list_filter = ('status',)
    search_fields = ('submitted_by__username', 'challenge__slug')


@admin.register(models.Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('submission', 'metric_name', 'value', 'dataset')
    list_filter = ('dataset',)


@admin.register(models.LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = ('challenge', 'user', 'team', 'rank', 'primary_score', 'dataset')
    list_filter = ('dataset',)
