from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role

from . import health, savefiles, simulator
from .models import SaveFile
from .serializers import SaveFileSerializer, SaveFileWriteSerializer, SimulatorSerializer

# Roles from the plan's API table.
SimulatorUsers = has_role('event_manager', 'treasurer', 'president')
HealthReaders = has_role('president')
SaveFileUsers = has_role('event_manager', 'president')


class SimulatorView(APIView):
    """POST /simulator. A calculation: POST because it takes a body, but it
    changes nothing.
    """

    permission_classes = [SimulatorUsers]

    def post(self, request):
        serializer = SimulatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event = data.pop('event')
        try:
            forecast = simulator.simulate(**data)
        except simulator.NoBreakEven:
            raise ValidationError({'ticket_price': [ErrorDetail(
                'The ticket price must be higher than the cost per head; otherwise every guest '
                'loses money and the event can never break even.', code='no_break_even',
            )]})
        return Response({
            'inputs': data,
            **forecast,
            'event': event and {'id': event.id, 'title': event.title},
            'forecast_vs_actual': event and simulator.forecast_vs_actual(event, forecast, data['expected_attendance']),
        })


class HealthView(APIView):
    """GET /health. The club health score, not a server uptime check."""

    permission_classes = [HealthReaders]

    def get(self, request):
        return Response(health.club_health())


class SaveFileListCreateView(ListAPIView):
    """GET /savefiles (optionally ?event=<id>), POST /savefiles.

    ASSUMPTION: the plan gives only GET and POST and says save files are
    editable, so POST for an event that already has one updates it.
    """

    permission_classes = [SaveFileUsers]
    serializer_class = SaveFileSerializer

    def get_queryset(self):
        save_files = SaveFile.objects.select_related('event')
        event = self.request.query_params.get('event')
        if event:
            if not event.isdigit():
                raise ValidationError({'event': [ErrorDetail('Must be an event id.', code='invalid')]})
            save_files = save_files.filter(event_id=int(event))
        return save_files

    def post(self, request):
        serializer = SaveFileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        save_file, created = savefiles.save(event=data.pop('event'), actor=request.user, **data)
        return Response(
            SaveFileSerializer(save_file).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
