import re


DISCOGS_ARTIST_SUFFIX_RE = re.compile(r"\s+\(\d+\)$")


def clean_artist_name(name):
    if not name:
        return name
    return DISCOGS_ARTIST_SUFFIX_RE.sub("", name).strip()
