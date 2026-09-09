import logging
import uuid

from django.contrib import messages
from django.db import DatabaseError
from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)


class AdminExceptionMiddleware(MiddlewareMixin):
    """Show a safe admin message for unexpected errors and retain the traceback."""

    def process_exception(self, request, exception):
        if request.method != 'POST' or not request.path.startswith('/admin/'):
            return None

        reference = uuid.uuid4().hex[:8].upper()
        logger.exception('Admin request failed [reference=%s]', reference, exc_info=exception)

        if isinstance(exception, (OSError, PermissionError)):
            explanation = (
                'The server could not store the uploaded file. '
                'Please ask an administrator to check media storage permissions.'
            )
        elif isinstance(exception, DatabaseError):
            explanation = 'The database could not save this record. Please try again or contact an administrator.'
        else:
            explanation = 'The record could not be saved because of an unexpected server problem.'

        messages.error(request, f'{explanation} Error reference: {reference}.')
        return HttpResponseRedirect(request.path)
