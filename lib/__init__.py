from .pagerduty import Pagerduty, Incident

import os
import re
from datetime import timedelta

TIMEDELTA_REGEX = (r'((?P<days>-?\d+)d)?'
                   r'((?P<hours>-?\d+)h)?'
                   r'((?P<minutes>-?\d+)m)?')
TIMEDELTA_PATTERN = re.compile(TIMEDELTA_REGEX, re.IGNORECASE)

MAX_SNOOZE_DURATION = 7 * 24 * 60 * 60

def duration_parse(delta):
    match = TIMEDELTA_PATTERN.match(delta)
    if not match:
        print("{} is not a valid duration, must be in format #d#h#m".format(delta))
        os.exit(2)
    parts = {k: int(v) for k, v in match.groupdict().items() if v}
    duration = int(timedelta(**parts).total_seconds())

    if duration > MAX_SNOOZE_DURATION:
        print("{} is too long, maximum snooze duration is 7 days".format(delta))
        os.exit(2)

    return duration
