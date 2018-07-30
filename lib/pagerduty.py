import pygerduty.v2
import parse
import os

class Pagerduty():
    def __init__(self, api_key, email):
        self.pager = pygerduty.v2.PagerDuty(api_key)
        self.email = email

        # self.me = self.user(self.email)

    def incidents_by_user(self, user_id, triggered = False):
        args = {
            'statuses': ['triggered'],
            'user_ids': [user_id],
        }

        if not triggered:
            args['statuses'].append('acknowledged')

        incidents = self.pager.incidents.list(**args)
        return incidents

    def user(self, name):
        users = list(self.pager.users.list(query=name))

        if len(users) == 0:
            print("No users found with the name \"{}\"".format(name))
            os.exit(2)

        if len(users) > 1:
            print("Too many users found with name \"{}\"".format(name))
            for user in users:
                print("\t{} <{}>".format(user.name, user.email))
            os.exit(2)

        return users[0]

    def summary(self, user_id = None, triggered = False):
        if not user_id:
            user_id = self.user_id
        raw_incidents = self.incidents_by_user(user_id, triggered = triggered)
        incidents = map(Incident, raw_incidents)

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


class Incident():
    classifications = {
        "Outdated running instance": "outdated instance",
        "Plan does not match remote state for": "terraform plan",
    }

    def __init__(self, raw_incident):
        self.raw = raw_incident
        self.classify()
        self._parse()

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

    def dict(self, show_user = False):
        out = {
            'id': self.raw.incident_number,
            'title': self.summary,
            'time': self.raw.created_at,
            'status': self.raw.status,
            'urgency': self.raw.urgency,
            'type': self.type,
        }

        if show_user:
            out['user'] = self.raw.assignments[0].assignee.summary

        return out

    def same_class(self, incident):
        if self.type == None:
            return self.raw.title == incident.raw.title

        if self.type == "outdated incident":
            return self.simple_name == incident.simple_name

        if self.type == "terraform plan":
            return self.repo == incident.repo

        return False
