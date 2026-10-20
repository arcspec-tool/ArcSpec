class ToolRefusal(Exception):
    pass


def validation_text(errors, prefix=''):
    parts = []
    for error in errors:
        location = '.'.join(str(part) for part in error.get('loc', ()))
        parts.append(f'{prefix}{location}: {error["msg"]}' if location else error['msg'])
    return '; '.join(parts)
