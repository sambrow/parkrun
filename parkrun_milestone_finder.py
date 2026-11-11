# Scrape parkrun html pages for a given venue to look for
# people with upcoming milestones.
#
# NOTE: This is fragile since parkrun could easily change the
# syntax of their HTML pages and break the pattern matching
# done here.
#
# NOTE: This is not burdensome to the parkrun web server. It only
# makes a few calls based on the MOST_RECENT_EVENTS_COUNT value.

import datetime
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# Event we should study. Used in HTTP URLs.
VENUE_NAME = "lillie"

# id used for unknown runners (we prune these)
UNKNOWN_ID = "2214"

# We'll study this many of the most recent events.
MOST_RECENT_EVENTS_COUNT = 5

# People this close to a milestone will be printed.
MILESTONE_THRESHOLD = 5

# parkrun website only wants to talk to "browsers"
COMMON_HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
}


@dataclass
class Person:
    id: str
    name: str
    agegroup: str
    runs: int
    vols: int
    last_event_date: str

    def milestone_age(self) -> int:
        # grab the first number from the agegroup description
        match = re.search(r"\d+", self.agegroup)
        return int(match.group()) if match else 18


@dataclass
class Milestone:
    count: int
    max_age: int = 1000


@dataclass
class UpcomingMilesone:
    name: str
    gap: int
    milestone: str
    projected_date: str
    count_on_last_event: str


MILESTONES = [
    Milestone(10, 17),
    Milestone(25),
    Milestone(50),
    Milestone(100),
    Milestone(200),
    Milestone(250),
    Milestone(300),
    Milestone(400),
    Milestone(500),
    Milestone(600),
    Milestone(700),
    Milestone(800),
    Milestone(900),
    Milestone(1000),
]


def http_get(url: str, headers: dict):
    @dataclass
    class HttpResponse:
        status_code: int
        text: str

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.status
            text = response.read().decode("utf-8", errors="replace")
            return HttpResponse(status_code, text)
    except urllib.error.HTTPError as e:
        status_code = e.code
        text = e.read().decode("utf-8", errors="replace")
        return HttpResponse(status_code, text)


def get_nth_upcoming_saturday(gap: int) -> str:
    if gap < 1:
        raise ValueError("gap must be at least 1")

    today = datetime.date.today()
    weekday = today.weekday()  # Monday is 0, Saturday is 5

    # If today is Saturday, it doesn't count, so the first upcoming Saturday is 7 days away.
    # Otherwise, calculate days until the next Saturday using modulo arithmetic.
    if weekday == 5:
        days_to_first = 7
    else:
        days_to_first = (5 - weekday) % 7

    # Add 7 days for each additional gap beyond the first
    total_days = days_to_first + 7 * (gap - 1)
    target_date = today + datetime.timedelta(days=total_days)

    return target_date.strftime("%Y-%m-%d")


def get_latest_event_info():
    # This page redirects to a page that contains the latest event number.
    url = f"https://www.parkrun.us/{VENUE_NAME}/results/latestresults/"
    response = http_get(url, headers=COMMON_HEADERS)
    if response.status_code != 200:
        print(f"Error retrieving {url}: {response.status_code}")
        sys.exit(1)

    html_content = response.text

    # Tease out the event number on this page.
    match = re.search(r"<span>#(\d+)", html_content)
    if match:
        num_events = int(match.group(1))
    else:
        print("Event number not found!")
        sys.exit(1)

    return num_events, html_content


def get_event_date(html_content: str):
    date_match = re.search(r'<span class="format-date">([^<]+)<', html_content)
    if date_match:
        return date_match.group(1)
    else:
        return ""


def get_runners(html_content: str):
    runners_by_id = {}

    event_date = get_event_date(html_content)

    # Step 1: Find every row container block
    row_pattern = re.compile(r'<tr class="Results-table-row"[^>]*?>.*?</tr>', re.DOTALL)

    for row_match in row_pattern.finditer(html_content):
        row_html = row_match.group(0)

        # Step 2: Extract individual attributes and the ID safely
        name_match = re.search(r'data-name="([^"]*)"', row_html)
        agegroup_match = re.search(r'data-agegroup="([^"]*)"', row_html)
        runs_match = re.search(r'data-runs="(\d+)"', row_html)
        vols_match = re.search(r'data-vols="(\d+)"', row_html)

        # Extract ID from the parkrunner URL pattern
        id_match = re.search(r'href="[^"]*?/parkrunner/(\d+)"', row_html)

        if name_match and id_match:
            id = id_match.group(1)
            if id != UNKNOWN_ID:
                runners_by_id[id] = Person(
                    id=id,
                    name=name_match.group(1),
                    agegroup=agegroup_match.group(1) if agegroup_match else "",
                    runs=int(runs_match.group(1)) if runs_match else 0,
                    vols=int(vols_match.group(1)) if vols_match else 0,
                    last_event_date=event_date,
                )

    return runners_by_id


def get_volunteers(html_content: str):
    volunteers_by_id = {}

    event_date = get_event_date(html_content)

    # Step 1: Find every volunteer row container block
    row_pattern = re.compile(
        r'<tr class="Volunteers-table-row"[^>]*?>.*?</tr>', re.DOTALL
    )

    for row_match in row_pattern.finditer(html_content):
        row_html = row_match.group(0)

        # Step 2: Extract the required attributes and the ID using targeted regex
        name_match = re.search(r'data-name="([^"]*)"', row_html)
        vols_match = re.search(r'data-volunteercredits="(\d+)"', row_html)
        id_match = re.search(r'href="[^"]*?/parkrunner/(\d+)"', row_html)

        if name_match and id_match:
            id = id_match.group(1)
            volunteers_by_id[id] = Person(
                id=id,
                name=name_match.group(1),
                vols=int(vols_match.group(1)) if vols_match else 0,
                agegroup="",
                runs=0,
                last_event_date=event_date,
            )

    return volunteers_by_id


def get_people_from_html_content(html_content: str):
    people_by_id = get_runners(html_content)
    volunteers_by_id = get_volunteers(html_content)

    # Prefer the runners item since this includes both
    # runs and volunteer counts.  Only add in a volunteer
    # item if we have no runner item.
    for id in volunteers_by_id:
        if id not in people_by_id:
            people_by_id[id] = volunteers_by_id[id]

    return people_by_id


def get_people_for_one_event(event_number: int):
    url = f"https://www.parkrun.us/{VENUE_NAME}/results/{event_number}/"
    response = http_get(url, headers=COMMON_HEADERS)
    if response.status_code != 200:
        print(f"Error retrieving {url}: {response.status_code}")
        sys.exit(1)

    html_content = response.text
    return get_people_from_html_content(html_content)


def get_people():
    event_number, html_content = get_latest_event_info()
    total_people_by_id = get_people_from_html_content(html_content)

    # Having gotten the latest results, we now study a few recent
    # results to gather up more people.
    for back in range(1, MOST_RECENT_EVENTS_COUNT):
        people_by_id = get_people_for_one_event(event_number - back)
        for id in people_by_id:
            if id not in total_people_by_id:
                total_people_by_id[id] = people_by_id[id]
            elif people_by_id[id].runs > 0 and total_people_by_id[id].runs == 0:
                # So far, we only had this person as a volunteer only.
                # Swap this record out for a "run Person" which will have
                # accurate counts for both runs and vols.
                last_event_date = total_people_by_id[id].last_event_date
                total_people_by_id[id] = people_by_id[id]
                # preserve the original most-recent last_event_date
                total_people_by_id[id].last_event_date = last_event_date

    unsorted_people = [total_people_by_id[id] for id in total_people_by_id]
    people = sorted(unsorted_people, key=lambda x: x.name)
    return people


def collect_milestone(
    person: Person,
    milestone_type: str,
    count: int,
    upcoming_milestones: list[UpcomingMilesone],
):
    for milestone in MILESTONES:
        if person.milestone_age() <= milestone.max_age:
            if (milestone.count - MILESTONE_THRESHOLD) <= count < milestone.count:
                gap = milestone.count - count
                if gap == 1:
                    projected_date = "NEXT"
                else:
                    projected_date = get_nth_upcoming_saturday(gap)

                upcoming_milestone = UpcomingMilesone(
                    name=person.name,
                    gap=gap,
                    milestone=f"{milestone_type}{milestone.count}",
                    projected_date=projected_date,
                    count_on_last_event=f"{count} on {person.last_event_date}",
                )
                upcoming_milestones.append(upcoming_milestone)


def collect_milestones(person: Person, upcoming_milestones: list[UpcomingMilesone]):
    milestone_type = "r"
    count = person.runs
    collect_milestone(person, milestone_type, count, upcoming_milestones)

    milestone_type = "v"
    count = person.vols
    collect_milestone(person, milestone_type, count, upcoming_milestones)


def main():
    people = get_people()
    upcoming_milestones = []
    for person in people:
        collect_milestones(person, upcoming_milestones)

    sorted_upcoming_milestones = sorted(upcoming_milestones, key=lambda x: x.gap)

    for um in sorted_upcoming_milestones:
        print(
            f"{um.name}, {um.milestone}, {um.projected_date}, {um.count_on_last_event}"
        )


if __name__ == "__main__":
    main()
