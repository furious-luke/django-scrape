def flatten(value):
    if hasattr(value, '__iter__') and not isinstance(value, dict):
        return sum(map(flatten, value))
    else:
        return value
