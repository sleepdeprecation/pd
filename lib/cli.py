import argparse
import crayons
import json
import maya
import os
import sys
import textwrap
from .pagerduty import Pagerduty, Incident
from .utils import duration_seconds, duration_delta
# from dateutil.parser import parse as date_parse
from tabulate import tabulate
from urllib.parse import urlparse
from webbrowser import open as webopen

status_colors = {
    "triggered": crayons.red,
    "acknowledged": crayons.yellow,
    "resolved": crayons.green,
}

def indent(text):
    return textwrap.indent(str(text), ' ' * 4)


class Cli():
    @property
    def client(self):
        if not hasattr(self, '_pd_client'):
            self._pd_client = Pagerduty.from_config()
        return self._pd_client

    def main(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="cmd")

        list_parser = subparsers.add_parser("summary", help="Print summary of pagerduty incidents")
        list_parser.set_defaults(func=self.summary)
        list_parser.add_argument("--user", "-u", metavar="query", help="show summary for a specific user by name or email address")
        list_parser.add_argument("--triggered", help="show only triggered incidents", action="store_true", default=False)
        list_parser.add_argument("--long", "-l", help="show long form summary", dest="show_long", action="store_true", default=False)
        list_parser.add_argument("--short", "-s", help="show short form summary", dest="show_short", action="store_true", default=False)
        list_parser.add_argument("--all", "-a", help="show all open incidents", dest="show_all", action="store_true", default=False)

        show_parser = subparsers.add_parser("show", help="Show a pagerduty incident")
        show_parser.set_defaults(func=self.show)
        show_parser.add_argument("id", help="ID of incident to show")

        ack_parser = subparsers.add_parser("ack", help="Ack a pagerduty incident")
        ack_parser.set_defaults(func=self.ack)
        ack_parser.add_argument("ids", nargs="+", help="IDs of incident to ack")

        ackall_parser = subparsers.add_parser("ackall", help="Ack all pagerduty incidents")
        ackall_parser.set_defaults(func=self.ackall)

        assign_parser = subparsers.add_parser("assign", help="(re)assign an incident to another pagerduty user")
        assign_parser.set_defaults(func=self.assign)
        assign_parser.add_argument("id", help="ID of incident to assign")
        assign_parser.add_argument("user", metavar="query", help="user to reassign incident to (by name or email)")

        snooze_parser = subparsers.add_parser("snooze", help="Snooze pagerduty incidents (also acks them first)")
        snooze_parser.set_defaults(func=self.snooze)
        snooze_parser.add_argument("--duration", "-d", help="length of time to snooze, in 2d6h3m format", default="24h", metavar="time")
        snooze_parser.add_argument("ids", nargs="+", help="IDs of incidents to snooze")

        resolve_parser = subparsers.add_parser("resolve", help="Resolve pagerduty incidents")
        resolve_parser.set_defaults(func=self.resolve)
        resolve_parser.add_argument("ids", nargs="+", help="IDs of incidents to resolve")

        who_parser = subparsers.add_parser("who", help="Find out who's on call")
        who_parser.set_defaults(func=self.who)

        open_parser = subparsers.add_parser("open", help="Open pagerduty issues in your web browser")
        open_parser.set_defaults(func=self.open)
        open_parser.add_argument("id", help="ID of incident to open", default=-1)

        override_parser = subparsers.add_parser("override", help="Schedule an override")
        override_parser.set_defaults(func=self.override)
        override_parser.add_argument("schedule", help="Schedule name or ID")
        override_parser.add_argument("user", help="User who is taking the override")
        override_parser.add_argument("start", help="Start of override (date time, in the schedule's timezone)")
        override_parser.add_argument("duration", help="length of override, in 2d6h3m format")


        args = parser.parse_args()

        if 'func' not in args:
            parser.print_help()
            sys.exit(1)

        args.func(args)

    def summary(self, args):
        if args.show_all:
            user_id = None
        else:
            if args.user:
                userquery = args.user
            else:
                userquery = self.client.email

            user_id = self.client.user(userquery).id

        if args.show_short and not args.show_all:
            summary = self.client.summary(user_id, triggered=args.triggered)

            keys = list(summary.keys())
            keys.sort()

            for key in keys:
                items = summary[key]

                incident_numbers = []
                for incident in items:
                    incident_numbers.append(
                        str(status_colors[incident.status](incident.id, bold=True))
                    )

                print("[{incidents}] {title}".format(
                    incidents = ", ".join(incident_numbers),
                    title = key,
                ))

        else:
            incidents = self.client.incidents(user_id = user_id, triggered=args.triggered)

            output_str = "{number} {date} {title}"
            if args.show_all:
                output_str += " ({owner})"
            if args.show_long:
                output_str += "\n\t{url}\n"

            for incident in incidents:
                color = status_colors[incident.status]
                print(output_str.format(
                    number = color("[{}]".format(incident.id)),
                    date = color(incident.date),
                    title = incident.raw_summary,
                    url = incident.url,
                    owner = incident.assignee,
                ))

    def snooze(self, args):
        delta = duration_seconds(args.duration)
        if delta > self.client.MAX_SNOOZE_DURATION:
            print("{} is too long, maximum snooze duration is 7 days".format(args.duration))
            os.exit(2)

        for _id in args.ids:
            self.client.snooze(_id, delta)

    def ack(self, args):
        for _id in args.ids:
            self.client.ack(_id)

    def show(self, args):
        incident = self.client.show(args.id)

        # prime alerts, so printing happens quickly
        incident.alerts

        color = status_colors[incident.status]
        print(color(incident.raw.summary, bold=True))
        print(indent(color("{status}\t{assignee}\t{dedup_key}\n{url}".format(
            status = incident.status,
            assignee = incident.assignee,
            dedup_key = incident.dedup_key,
            url = incident.url,
        ))))

        for i, alert in enumerate(incident.alerts):
            print(indent(crayons.white("\nAlert {}".format(i), bold=True)))
            print(indent(indent(alert.body.details_str())))
            print()

            for context in alert.body.contexts:
                print(indent(indent(crayons.white(context.text, bold=True))))
                print(indent(indent(indent(context.href))))

    def ackall(self, args):
        for incident in self.client.incidents(user_id = self.client.me.id, triggered=True):
            print("acking {}".format(incident.summary))
            incident.acknowledge(self.client.email)
        else:
            print("You don't own any triggered incidents")
            sys.exit(1)

    def assign(self, args):
        user = self.client.user(args.user)
        self.client.reassign(args.id, user)


    def resolve(self, args):
        for _id in args.ids:
            self.client.resolve(_id)

    def who(self, args):
        oncalls = self.client.oncalls()

        table = []
        for _, team in oncalls.items():
            row = [team["name"]]
            row.extend(map(lambda t: t["person"], team["levels"]))
            table.append(row)
        table.sort(key=lambda r: r[0])

        longest = len(max(table, key=lambda r: len(r))) - 1
        header = ["Rotation"]
        for i in range(longest):
            header.append("Level {}".format(i + 1))

        print(tabulate(table, headers=header))

    def open(self, args):
        if args.id == -1:
            incident = self.client.show(1)
            url = urlparse(incident.url)
            page = "{}://{}".format(url.scheme, url.netloc)
        else:
            incident = self.client.show(args.id)
            page = incident.url

        webopen(page)

    def override(self, args):
        schedule = self.client.schedule(args.schedule)
        user = self.client.user(args.user)

        tz = schedule.time_zone

        start = maya.parse(args.start, timezone=schedule.time_zone).datetime(to_timezone=tz)
        delta = duration_delta(args.duration)
        end = start + delta

        existing_schedule = self.client.schedule_at(schedule.id, start, end)#.final_schedule

        print("You will be overriding:")
        for entry in existing_schedule.final_schedule.rendered_schedule_entries:
            username = entry.user.summary
            override_start = maya.parse(entry.start).datetime(to_timezone=tz)
            override_end = maya.parse(entry.end).datetime(to_timezone=tz)
            print("\t{}, from {} to {}".format(username, override_start, override_end))

        correct = input("Is this correct [yN]? ")
        if correct[0] not in ["y", "Y"]:
            sys.exit(1)

        self.client.create_override(schedule.id, user.id, start, end)

