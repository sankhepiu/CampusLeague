from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny


@api_view(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([])
@permission_classes([AllowAny])
def api_not_found(request):
    """Catch-all for /api/ paths that match no endpoint.

    Without it Django answers with an HTML page (and, with DEBUG on, a list
    of every URL pattern). Raising NotFound sends it through the shared
    exception handler, so the client gets the usual error shape.
    """
    raise NotFound('No such endpoint.')
