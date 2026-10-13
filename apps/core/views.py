from django.db import DatabaseError, connection
from django.http import Http404, JsonResponse
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.core import modals
from apps.core.mixins import LoginRequiredMixin


@never_cache
@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return JsonResponse({'status': 'error', 'database': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


class ModalView(LoginRequiredMixin, View):

    def get(self, request, name):
        if not modals.is_ajax(request):
            raise Http404
        spec = modals.get(name)
        if spec is None:
            raise Http404
        params = {key: request.GET.get(key) for key in spec.params if key in request.GET}
        return modals.render_modal(request, name, spec.context(request, params))
