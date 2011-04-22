def update(cur, value, op=None):
    if cur is None:
        return value
    if op is not None:
        return op(cur, value)
    return cur + value
