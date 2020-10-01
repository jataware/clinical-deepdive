def deep_get(d, path, default=None):
    """
    Take array or string as the path to a dict item and return the item or default if path does not exist.
    """
    if not d or not path:
        return d

    parts = path.split(".") if isinstance(path, str) else path
    return (
        deep_get(d.get(parts[0]), parts[1:], default)
        if d.get(parts[0]) is not None
        else default
    )
