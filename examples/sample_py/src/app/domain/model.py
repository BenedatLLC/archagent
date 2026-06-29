from app.web import routes  # BND-001 violation: domain must not import web


def describe() -> str:
    print("computing description")  # STR-002 violation: no direct I/O in domain
    return routes.PREFIX
