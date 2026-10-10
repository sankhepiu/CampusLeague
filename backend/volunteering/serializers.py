from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from django.utils import timezone

from common.validation import MAX_AMOUNT, MAX_DESCRIPTION, MAX_TITLE

from . import services
from .models import Fundraiser, FundraiserSale, Task

User = get_user_model()


def error(message, code):
    return [ErrorDetail(message, code=code)]


class TaskSerializer(serializers.ModelSerializer):
    assignees = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ['id', 'fundraiser', 'event', 'title', 'description', 'status', 'due_date', 'assignees']
        read_only_fields = fields

    def get_assignees(self, task):
        return [
            {'id': a.user_id, 'name': a.user.name, 'role_note': a.role_note}
            for a in task.assignments.all()
        ]


class TaskWriteSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=MAX_TITLE)
    description = serializers.CharField(max_length=MAX_DESCRIPTION, allow_blank=True, required=False)

    class Meta:
        model = Task
        # status is changed through PATCH /tasks/{id}/status only.
        fields = ['fundraiser', 'event', 'title', 'description', 'due_date']

    def validate(self, attrs):
        task = self.instance
        fundraiser = attrs.get('fundraiser', getattr(task, 'fundraiser', None))
        event = attrs.get('event', getattr(task, 'event', None))
        if (fundraiser is None) == (event is None):
            raise serializers.ValidationError(
                {'fundraiser': error('A task belongs to exactly one fundraiser or one event.', 'one_parent_required')}
            )
        # ASSUMPTION: a due date being set or changed cannot be in the past.
        # An untouched old due date does not block other edits.
        due = attrs.get('due_date')
        if due and due != getattr(task, 'due_date', None) and due < timezone.localdate():
            raise serializers.ValidationError({'due_date': error('The due date cannot be in the past.', 'in_past')})
        return attrs


class TaskStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Task.Status.values)


class AssignSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))
    role_note = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class FundraiserSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    tasks = serializers.SerializerMethodField()

    class Meta:
        model = Fundraiser
        fields = ['id', 'title', 'goal_amount', 'starts_on', 'ends_on', 'status', 'progress', 'tasks']
        read_only_fields = fields

    def get_progress(self, fundraiser):
        return services.progress(fundraiser)

    def get_tasks(self, fundraiser):
        tasks = fundraiser.tasks.prefetch_related('assignments__user')
        return TaskSerializer(tasks, many=True).data


class FundraiserWriteSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=MAX_TITLE)
    goal_amount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)

    class Meta:
        model = Fundraiser
        fields = ['title', 'goal_amount', 'starts_on', 'ends_on', 'status']

    def validate(self, attrs):
        fundraiser = self.instance
        starts = attrs.get('starts_on', getattr(fundraiser, 'starts_on', None))
        ends = attrs.get('ends_on', getattr(fundraiser, 'ends_on', None))
        if starts and ends and ends < starts:
            raise serializers.ValidationError({'ends_on': error('The fundraiser cannot end before it starts.', 'ends_before_start')})
        return attrs


class SaleSerializer(serializers.ModelSerializer):
    amount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    note = serializers.CharField(max_length=200, allow_blank=True, required=False)

    class Meta:
        model = FundraiserSale
        fields = ['id', 'amount', 'note', 'created_at']
        read_only_fields = ['id', 'created_at']
