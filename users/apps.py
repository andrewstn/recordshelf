from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        import posthog
        from django.conf import settings
        from django.contrib.auth.signals import user_logged_in
        from django.dispatch import receiver

        posthog.api_key = settings.POSTHOG_PROJECT_TOKEN
        posthog.host = settings.POSTHOG_HOST

        if settings.POSTHOG_DISABLED:
            posthog.disabled = True

        if settings.DEBUG:
            posthog.debug = True

        @receiver(user_logged_in)
        def on_user_logged_in(sender, request, user, **kwargs):
            if settings.POSTHOG_DISABLED or not settings.POSTHOG_PROJECT_TOKEN:
                return

            with posthog.new_context():
                posthog.identify_context(str(user.id))
                posthog.capture('user_logged_in', properties={
                    'is_staff': user.is_staff,
                })
