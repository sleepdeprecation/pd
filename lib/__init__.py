from .pagerduty import Pagerduty, Incident
from .cli import Cli

pd = Pagerduty.from_config()
