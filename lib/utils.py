import os
import re
from datetime import timedelta

TIMEDELTA_REGEX = (r'((?P<days>-?\d+)d)?'
                   r'((?P<hours>-?\d+)h)?'
                   r'((?P<minutes>-?\d+)m)?')
TIMEDELTA_PATTERN = re.compile(TIMEDELTA_REGEX, re.IGNORECASE)


def duration_seconds(duration):
    duration = int(duration_delta(duration).total_seconds())

    return duration

def duration_delta(duration):
    match = TIMEDELTA_PATTERN.match(duration)
    if not match:
        print("{} is not a valid duration, must be in format #d#h#m".format(duration))
        os.exit(2)
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    return timedelta(**parts)

