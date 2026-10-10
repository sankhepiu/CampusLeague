import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger('campusleague.api')


def _flatten(details, field=None):
    """Turn DRF's nested validation details into a flat list of
    {field, code, message}. Nested fields become dotted paths (lines.0.qty).
    """
    if isinstance(details, dict) and 'message' in details and 'code' in details:
        return [{'field': field, 'code': details['code'], 'message': str(details['message'])}]
    if isinstance(details, dict):
        errors = []
        for key, value in details.items():
            # DRF reports whole-object errors under "non_field_errors".
            if key == 'non_field_errors':
                path = field
            else:
                path = f'{field}.{key}' if field else str(key)
            errors.extend(_flatten(value, path))
        return errors
    errors = []
    for index, value in enumerate(details):
        is_leaf = isinstance(value, dict) and 'message' in value and 'code' in value
        path = field if is_leaf else (f'{field}.{index}' if field else str(index))
        errors.extend(_flatten(value, path))
    return errors


def _by_field(errors):
    fields = {}
    for item in errors:
        fields.setdefault(item['field'] or '_', item['message'])
    return fields


def api_exception_handler(exc, context):
    """Plan: "Return the same error shape everywhere: a code, a human
    message, and the field if relevant."

    Every API error body is {"code", "message", "field"}.

    ASSUMPTION (plan also asks for "field-level error messages" but shows one
    field): validation errors add an "errors" list with one {field, code,
    message} item per problem; the top-level message and field repeat the
    first item.
    """
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    # DRF builds the response first so status codes and headers such as
    # WWW-Authenticate stay correct; only the body is replaced.
    response = drf_exception_handler(exc, context)
    if response is None:
        # Not an API exception, so a bug. The traceback goes to the server
        # log only; the client gets a generic body even when DEBUG is on.
        logger.error(
            'Unhandled error in %s', type(context.get('view')).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        # Marks the surrounding transaction (if any) for rollback, as DRF
        # does for the exceptions it handles itself.
        set_rollback()
        return Response(
            {
                'code': 'server_error',
                'message': 'Something went wrong on our side. Please try again.',
                'field': None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        errors = _flatten(exc.get_full_details())
        first = errors[0] if errors else {'field': None, 'message': 'Invalid input.'}
        response.data = {
            'code': 'validation_error',
            'message': first['message'],
            'field': first['field'],
            'errors': errors,
            # The same problems keyed by field, for forms: the first message
            # for each. Problems with no single field are under "_".
            'fields': _by_field(errors),
        }
    else:
        detail = exc.detail
        response.data = {
            'code': getattr(detail, 'code', None) or exc.default_code,
            'message': str(detail),
            'field': None,
        }
    return response
