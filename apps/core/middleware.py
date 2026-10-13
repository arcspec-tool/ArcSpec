from django.http import HttpResponse

from apps.core.modals import is_ajax

REDIRECT_STATUSES = (301, 302, 303, 307, 308)
REDIRECT_HEADER = 'X-Redirect-To'


class AjaxRedirectMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_ajax(request) and response.status_code in REDIRECT_STATUSES and response.has_header('Location'):
            replacement = HttpResponse(status=204)
            replacement[REDIRECT_HEADER] = response['Location']
            replacement['Cache-Control'] = 'no-store'
            replacement.cookies = response.cookies
            return replacement
        return response
