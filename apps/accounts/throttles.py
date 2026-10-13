from rest_framework.throttling import SimpleRateThrottle

PERIOD_SECONDS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


class AddressThrottle(SimpleRateThrottle):

    def parse_rate(self, rate):
        count, period = rate.split('/')
        return int(count), int(period[:-1] or 1) * PERIOD_SECONDS[period[-1]]

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class EmailThrottle(AddressThrottle):

    def get_cache_key(self, request, view):
        email = request.POST.get('email', '').strip().lower()
        if not email:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': email}


class LoginAddressThrottle(AddressThrottle):
    scope = 'login_ip'


class LoginEmailThrottle(EmailThrottle):
    scope = 'login_email'


class ForgotAddressThrottle(AddressThrottle):
    scope = 'forgot_ip'


class ForgotEmailThrottle(EmailThrottle):
    scope = 'forgot_email'


def throttled(request, *throttles):
    return not all(throttle().allow_request(request, None) for throttle in throttles)
