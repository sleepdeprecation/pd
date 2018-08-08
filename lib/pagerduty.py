import json
import pygerduty.v2
import parse
import sys

class Pagerduty():
    def __init__(self, api_key, email):
        self.pager = pygerduty.v2.PagerDuty(api_key)
        self.email = email

    @property
    def me(self):
        if not hasattr(self, '_me'):
            self._me = self.user(self.email)
        return self._me

    def incidents_by_user(self, user_id, triggered = False):
        args = {
            'statuses': ['triggered'],
            'user_ids': [user_id],
            'date_range': 'all',
        }

        if not triggered:
            args['statuses'].append('acknowledged')

        incidents = self.pager.incidents.list(**args)
        return incidents

    def user(self, name):
        users = list(self.pager.users.list(query=name))

        if len(users) == 0:
            print("No users found with the name \"{}\"".format(name))
            sys.exit(2)

        if len(users) > 1:
            print("Too many users found with name \"{}\"".format(name))
            for user in users:
                print("\t{} <{}>".format(user.name, user.email))
            sys.exit(2)

        return users[0]

    def summary(self, user_id = None, triggered = False):
        if not user_id:
            user_id = self.user_id
        raw_incidents = self.incidents_by_user(user_id, triggered = triggered)
        incidents = map(lambda x: Incident(self.pager, x), raw_incidents)

        by_class = {}
        for incident in incidents:
            if incident.summary in by_class:
                by_class[incident.summary].append(incident)
            else:
                by_class[incident.summary] = [incident]

        return by_class

    def snooze(self, _id, delta=(24*60*60)):
        incident = self.pager.incidents.show(_id)
        if incident.status == "resolved":
            print("already resolved: {}".format(incident.summary))
            return

        if incident.status == "triggered":
            incident.acknowledge(self.email)

        print("snoozing {}".format(incident.summary))
        incident.snooze(self.email, delta)

    def ack(self, _id):
        incident = self.pager.incidents.show(_id)
        if incident.status != "triggered":
            print("Incident {} is not triggered".format(_id))
            sys.exit(2)
        incident.acknowledge(self.email)

    def resolve(self, _id):
        incident = self.pager.incidents.show(_id)
        if incident.status == "resolved":
            print("Incident {} is already resolved".format(_id))
            return
        incident.resolve(self.email)

    def show(self, _id):
        return Incident(self.pager, self.pager.incidents.show(_id))


class Incident():
    classifications = {
        "Outdated running instance": "outdated instance",
        "Plan does not match remote state for": "terraform plan",
    }

    def __init__(self, pager, raw_incident):
        self.pager = pager
        self.raw = raw_incident
        self.classify()
        self._parse()

        # set some useful things from raw incident
        self.id = self.raw.incident_number
        self.time = self.raw.created_at
        self.status = self.raw.status
        self.urgency = self.raw.urgency

    def classify(self):
        for prefix, klass in Incident.classifications.items():
            if self.raw.title.startswith(prefix):
                self.type = klass
                return
        self.type = None

    def _parse(self):
        if not self.type:
            self.parsed = {}
        elif self.type == "outdated instance":
            self.parsed = parse.parse(
                "Outdated running instance ({simple_name} - {instance_id}) found in {environment}",
                self.raw.title
            ).named

            if self.parsed['simple_name'][-10:-1] == "us-east-1":
                self.parsed['simple_name'] = self.parsed['simple_name'][:-11]

            self._summary = "outdated instance: {}".format(self.parsed['simple_name'])
        elif self.type == "terraform plan":
            self.parsed = parse.parse(
                "Plan does not match remote state for: {repo} in Workspace: {workspace}",
                self.raw.title
            ).named
            self._summary = "terraform plan: {}".format(self.parsed['repo'])

    @property
    def summary(self):
        if hasattr(self, '_summary'):
            return self._summary
        return self.raw.title

    @property
    def alerts(self):
        if not hasattr(self, '_alerts'):
            self._alerts = list(map(Alert, self.pager.alerts.list(incident_id = self.raw.id)))
        return self._alerts

    @property
    def dedup_key(self):
        if not hasattr(self, '_dedup_key'):
            self._dedup_key = self.alerts[0].alert_key
        return self._dedup_key

    @property
    def assignee(self):
        if not hasattr(self, '_assignee'):
            self._assignee = self.raw.assignments[0].assignee.summary
        return self._assignee

    def dict(self, show_user = False):
        out = {
            'id': self.id,
            'dedup_key': self.dedup_key,
            'title': self.summary,
            'time': self.time,
            'status': self.status,
            'urgency': self.urgency,
            'type': self.type,
        }

        if show_user:
            out['user'] = self.raw.assignments[0].assignee.summary

        return out

class Alert():
    def __init__(self, raw_alert):
        self.raw = raw_alert
        self.alert_key = self.raw.alert_key
        self.body = self.raw.body.details


    def __str__(self):
        if isinstance(self.body, str):
            return self.body
        else:
            return json.dumps(self.body, cls=ContainerEncoder, indent=4)

class ContainerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pygerduty.v2.Container):
            return obj._kwargs
        return super().default(obj)
