from rest_framework import serializers

from events.models import Event

from .models import SaveFile

# ASSUMPTIONS (plan gives no limits): upper bounds that keep the arithmetic
# and the stored text sensible.
MAX_PAISE = 10 ** 11            # Rs 100 crore
MAX_ATTENDANCE = 1_000_000
MAX_TEXT = 5000
MAX_CHECKLIST_ITEMS = 50


class SimulatorSerializer(serializers.Serializer):
    ticket_price = serializers.IntegerField(min_value=0, max_value=MAX_PAISE)
    expected_attendance = serializers.IntegerField(min_value=0, max_value=MAX_ATTENDANCE)
    fixed_costs = serializers.IntegerField(min_value=0, max_value=MAX_PAISE)
    variable_cost_per_head = serializers.IntegerField(min_value=0, max_value=MAX_PAISE)
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all(), required=False, allow_null=True, default=None)


class SaveFileSerializer(serializers.ModelSerializer):
    event = serializers.SerializerMethodField()

    class Meta:
        model = SaveFile
        fields = ['id', 'event', 'vendors', 'budget_notes', 'what_worked', 'what_didnt', 'checklist', 'updated_at']
        read_only_fields = fields

    def get_event(self, save_file):
        return {'id': save_file.event_id, 'title': save_file.event.title}


class SaveFileWriteSerializer(serializers.Serializer):
    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())
    vendors = serializers.CharField(max_length=MAX_TEXT, allow_blank=True, required=False)
    budget_notes = serializers.CharField(max_length=MAX_TEXT, allow_blank=True, required=False)
    what_worked = serializers.CharField(max_length=MAX_TEXT, allow_blank=True, required=False)
    what_didnt = serializers.CharField(max_length=MAX_TEXT, allow_blank=True, required=False)
    checklist = serializers.ListField(
        child=serializers.CharField(max_length=200), max_length=MAX_CHECKLIST_ITEMS, required=False,
    )
