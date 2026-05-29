def posthog_distinct_id(request):
    if request.user.is_authenticated:
        return str(request.user.id)

    if not request.session.session_key:
        request.session.create()

    return f"anon:{request.session.session_key}"
