from urllib.parse import urlparse, parse_qs, parse_qsl, urlencode, urlunparse
from django import template


register = template.Library()


def _with_origin(embed_url: str) -> str:
    parsed = urlparse(embed_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params['origin'] = 'http://127.0.0.1:8000'
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(params),
        parsed.fragment,
    ))


@register.filter
def youtube_embed(url: str) -> str:
    """Convert a standard YouTube URL to an embeddable URL."""
    if not url:
        return ''

    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if 'youtube.com' in host:
        if parsed.path.startswith('/embed/'):
            return _with_origin(url)
        video_id = parse_qs(parsed.query).get('v', [''])[0]
        if video_id:
            return _with_origin(f'https://www.youtube.com/embed/{video_id}')

    if 'youtu.be' in host:
        video_id = parsed.path.strip('/').split('/')[0]
        if video_id:
            return _with_origin(f'https://www.youtube.com/embed/{video_id}')

    return url
