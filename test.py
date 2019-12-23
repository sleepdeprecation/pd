from lib import pd

import requests

import readline
import code
import maya
import urllib
import json

from pathlib import Path

all_incidents = list(pd.pager.incidents.list(
    statuses = ["resolved"],
    urgencies = ["low"],
    since = maya.when("2019-02-01").datetime(),
))

print("got all incidents: {}".format(len(all_incidents)))

incidents = []
for idx, i in enumerate(all_incidents):
    if idx % 20 == 0:
        print("at index {}".format(idx))

    alerts = list(pd.pager.alerts.list(incident_id=i.id))
    if len(alerts) != 1:
        print("too many alerts on incident {}: {}".format(i.id, i.summary))
        print("\t{}".format(i.html_url))

    alert = alerts[0]
    if alert.alert_key.startswith("reboot-required:") or alert.alert_key.startswith("outdated-instance:"):
        incidents.append(i)

incidents.sort(key=lambda x: maya.parse(x.created_at).datetime())

# def _process_query_params(query_params):
#     new_qp = []
#     for key, value in query_params.items():
#         if isinstance(value, (list, set, tuple)):
#             for elem in value:
#                 new_qp.append(("{0}[]".format(key), elem))
#         else:
#             new_qp.append((key, value))

#     return urllib.parse.urlencode(new_qp)

# config_file = Path.home() / '.config' / 'pd.json'
# if not config_file.is_file():
#     raise Exception("No config file found at $HOME/.config/pd.json.")

# with config_file.open() as f:
#     conf = json.load(f)

# def request(path, params=None):
#     headers = {
#         "Accept": "application/vnd.pagerduty+json;version=2",
#         "Content-type": "application/json",
#         "Authorization": "Token token={}".format(conf["api_key"]),
#     }

#     url = "https://api.pagerduty.com{}".format(path)

#     if params:
#         params = _process_query_params(params)
#         url += "?{}".format(params)

#     return requests.get(url, headers=headers)

env = globals().copy()
env.update(locals())

shell = code.InteractiveConsole(env)
shell.interact()
