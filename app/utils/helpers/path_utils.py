"""Path helper placeholders."""


def resolve_artifact_path(*segments):
    """Build a path under artifacts directory.

    TODO: Centralize base path discovery + OS handling.
    """
    return None


def sanitize_filename(name):
    """Return a safe filename for uploads/export.

    TODO: Strip dangerous characters + reserved words.
    """
    return name
