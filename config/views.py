from django.http import HttpResponse


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /search/",
        "Disallow: /collection/search/",
        "Disallow: /collection/album/",
        "Disallow: /admin/",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
