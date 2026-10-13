def unread_notification_count(request):
    if request.user.is_authenticated:
        if not hasattr(request, '_unread_notification_count'):
            request._unread_notification_count = request.user.notifications.filter(is_read=False).count()
        return {'unread_notification_count': request._unread_notification_count}
    return {'unread_notification_count': 0}


def system_settings(request):
    if not hasattr(request, '_system_settings'):
        from apps.accounts.auth_methods import current
        from apps.administration.models import SystemSettings
        request._system_settings = SystemSettings.load()
        request._auth_methods = current(request._system_settings)
    return {'system_settings': request._system_settings, 'auth_methods': request._auth_methods}
