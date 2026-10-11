from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .clubs import all_clubs


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


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def club_list(request):
    """GET /clubs. Public: the clubs on this site, for the login page and
    the club switcher. The same list whatever X-Club says.
    """
    return Response(all_clubs())
