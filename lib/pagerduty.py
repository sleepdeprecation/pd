import json
import maya
import parse
import pygerduty.v2
import sys
import tzlocal

from pathlib import Path

class Pagerduty():
    MAX_SNOOZE_DURATION = 7 * 24 * 60 * 60

    @classmethod
    def from_config(cls):
        config_file = Path.home() / '.config' / 'pd.json'
        if not config_file.is_file():
            raise Exception("No config file found at $HOME/.config/pd.json.")

        with config_file.open() as f:
            conf = json.load(f)
        api_key = conf['api_key']
        email = conf['email']

        return cls(api_key, email)

    def __init__(self, api_key, email):
        self.pager = pygerduty.v2.PagerDuty(api_key)
        self.email = email

    @property
    def me(self):
        if not hasattr(self, '_me'):
            self._me = self.user(self.email)
        return self._me

    def incidents(self, user_id = None, triggered = False):
        args = {
            'statuses': ['triggered'],
            'date_range': 'all',
        }

        if user_id:
            args['user_ids'] = [user_id]

        if not triggered:
            args['statuses'].append('acknowledged')

        def make_incident(raw):
            return Incident(self, raw)

        incidents = map(make_incident, self.pager.incidents.list(**args))
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

    def oncalls(self):
        raw_policies = list(Oncalls(self.pager).list())
        policies = {}

        for policy in raw_policies:
            policy_id = policy.escalation_policy.id
            if policy_id not in policies:
                policies[policy_id] = {
                    "name": policy.escalation_policy.summary,
                    "id": policy_id,
                    "levels": []
                }

            policies[policy_id]["levels"].append({
                "level": policy.escalation_level,
                "policy_name": policy.escalation_policy.summary,
                "person": policy.user.summary,
            })

        for _, policy in policies.items():
            policy["levels"].sort(key=lambda x: x['level'])

        return policies

    def summary(self, user_id = None, triggered = False):
        # if not user_id:
        #     user_id = self.user(self.email).id
        incidents = self.incidents(user_id = user_id, triggered = triggered)

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

    def reassign(self, _id, user):
        return self.pager.incidents.show(_id).reassign([user.id], self.email)

    def schedule(self, name):
        schedules = list(self.pager.schedules.list(query = name))

        if len(schedules) == 0:
            print("No schedule found with name \"{}\"".format(name))
            sys.exit(2)

        if len(schedules) > 1:
            print("Too many schedules found with name \"{}\"".format(name))
            for schedule in schedules:
                print("\t({}) {}".format(schedule.id, schedule.name))
            sys.exit(2)

        return schedules[0]

    def schedule_at(self, _id, start, end=None):
        args = { "since": start }
        if end:
            args["until"] = end

        return self.pager.schedules.show(_id, **args)

    def create_override(self, schedule_id, user_id, start, end):
        schedule = self.pager.schedules.show(schedule_id)
        schedule.overrides.create(start = start, end = end, user_id = user_id)


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
        self.created_at = maya.parse(self.time).datetime(to_timezone=str(tzlocal.get_localzone()))
        self.date = self.created_at.strftime("%Y-%m-%d")

        self.url = self.raw.html_url

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
    def raw_summary(self):
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
            assignments = self.raw.assignments
            if assignments:
                self._assignee = self.raw.assignments[0].assignee.summary
            else:
                self._assignee = "(none)"
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

    def acknowledge(self, email):
        self.raw.acknowledge(email)

class Alert():
    class AlertBody():
        def __init__(self, body):
            self.details = body.details
            self.contexts = body.contexts

        def details_str(self):
            if isinstance(self.details, str):
                return self.details
            return json.dumps(self.details, cls=ContainerEncoder, indent=4)

    def __init__(self, raw_alert):
        self.raw = raw_alert
        self.alert_key = self.raw.alert_key
        self.body = Alert.AlertBody(self.raw.body)
        self.contexts = self.raw.body.contexts


class ContainerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pygerduty.v2.Container):
            return obj._kwargs
        return super().default(obj)

class Oncall(pygerduty.v2.Container):
    pass

class Oncalls(pygerduty.v2.Collection):
    container = Oncall

    def _list_no_pagination(self, **kwargs):
        data = pygerduty.v2.Collection._list_no_pagination(self, **kwargs)
        def add_id(container):
            fake_id = "{}-{}".format(container.escalation_policy.id, container.escalation_level)
            container._kwargs["id"] = fake_id
            return container

        return list(map(add_id, data))
