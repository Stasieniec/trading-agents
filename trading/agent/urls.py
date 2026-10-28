from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def norm(url: str) -> str:
    try:
        u = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = u.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    q = urlencode([(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith("utm_")])
    path = u.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, q, ""))
