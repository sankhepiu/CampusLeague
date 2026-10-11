"""Several clubs on one site, one PostgreSQL schema per club.

ASSUMPTION (beyond the plan, which describes one club): each club in
settings.CLUBS has its own schema holding a complete copy of every table
(users, tokens, ledger, triggers and all). No model knows about clubs. A
request names its club in the X-Club header, and the middleware below points
the database connection at that club's schema for the length of the request,
so the same code and the same queries simply read and write another club's
tables.

Isolation is therefore the database's: while the search path is one club's
schema, the other clubs' tables cannot be named by an unqualified query at
all. A login token is a row in one club's token table, so it is unknown
(401) in every other.

Skyline lives in the "public" schema, where everything was before clubs
existed, so a request with no X-Club header behaves exactly as it always did.
"""
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse

logger = logging.getLogger('campusleague.clubs')

HEADER = 'X-Club'
DEFAULT_CLUB = 'skyline'
# Schema names come only from settings, never from a request; this is a
# second check before one is placed in SQL.
SCHEMA_NAME = re.compile(r'^[a-z_][a-z0-9_]{0,62}$')

# The club the current thread is working in. A ContextVar, like the database
# connection, is per thread: two requests never share it.
_current = ContextVar('club', default=DEFAULT_CLUB)


def club_info(slug):
    """The club object the API returns: {slug, name, short, color}."""
    club = settings.CLUBS[slug]
    return {'slug': slug, 'name': club['name'], 'short': club['short'], 'color': club['color']}


def all_clubs():
    return [club_info(slug) for slug in settings.CLUBS]


def current_club():
    return _current.get()


def schema_of(slug):
    schema = settings.CLUBS[slug]['schema']
    if not SCHEMA_NAME.fullmatch(schema):
        raise ValueError(f'Bad schema name for club {slug!r}.')
    return schema


def set_search_path(schema):
    """Point this thread's connection at one schema.

    Sent on the driver's own connection rather than through a Django cursor:
    it is connection housekeeping, not one of the request's queries.
    """
    connection.ensure_connection()
    connection.connection.execute(f'SET search_path TO {connection.ops.quote_name(schema)}')


def is_set_up(slug):
    """True if the club's schema exists and has been migrated. Skyline
    (public) always is; the others once `manage.py setup_clubs` has run.
    """
    schema = schema_of(slug)
    if schema == 'public':
        return True
    connection.ensure_connection()
    row = connection.connection.execute(
        'SELECT to_regclass(%s) IS NOT NULL', [f'{schema}.django_migrations'],
    ).fetchone()
    return bool(row[0])


@contextmanager
def use_club(slug):
    """Work in another club's schema for the length of a `with` block, then
    go back to the one that was current. For commands, the seed and the
    login view (which looks for the account in every club).
    """
    from django.contrib.contenttypes.models import ContentType

    previous = _current.get()
    token = _current.set(slug)
    # Content types are cached per process, but their ids belong to a schema.
    ContentType.objects.clear_cache()
    set_search_path(schema_of(slug))
    try:
        yield club_info(slug)
    finally:
        _current.reset(token)
        ContentType.objects.clear_cache()
        set_search_path(schema_of(previous))


class ClubMiddleware:
    """First in MIDDLEWARE. Reads X-Club (default: skyline), sets the search
    path to that club's schema, and puts it back to public when the response
    is done. The reset is in a `finally` because connections are reused: the
    next request on this connection must never start in another club's
    schema, even if this one raised.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        slug = request.headers.get(HEADER, '').strip().lower() or DEFAULT_CLUB
        if slug not in settings.CLUBS or not is_set_up(slug):
            return JsonResponse(
                {'code': 'club_not_found', 'message': 'There is no club with this slug.', 'field': None},
                status=404,
            )
        request.club = club_info(slug)
        token = _current.set(slug)
        try:
            set_search_path(schema_of(slug))
            return self.get_response(request)
        finally:
            _current.reset(token)
            try:
                set_search_path('public')
            except DatabaseError:
                # A connection too broken to reset is not reused.
                logger.exception('Could not reset the search path; closing the connection.')
                connection.close()
