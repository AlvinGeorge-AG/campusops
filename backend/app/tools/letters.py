import os
from strands import tool
from ..config import INSTITUTION_NAME, INSTITUTION_PLACE, DEFAULT_CHAIRPERSON, DEFAULT_STAFF

# High-quality templates based on real MACS letters provided by user
PERMISSION_TEMPLATE = f"""To,
The Principal,
{INSTITUTION_NAME},
{INSTITUTION_PLACE}.

Subject: Request for permission to host "{{title}}"

Respected Sir/Madam,

I am writing to request permission to conduct "{{title}}", organized by {{org}}, on {{date}} from {{start}} to {{end}} at {{room}}.
{{speaker_line}}
{{purpose_line}}
{{speaker_para}}

We appreciate your consideration of this request and thank you for your continued support.
Thank you.

With regards,
Chairperson {{org}}
{{chairperson}}

Staff In Charge {{org}}
{{staff}}
"""

ONFOOT_TEMPLATE = f"""To,
The Principal,
{INSTITUTION_NAME},
{INSTITUTION_PLACE}.

Subject: Request for On-foot Publicity for "{{title}}"

Respected Sir/Madam,

I am writing to request permission to conduct on-foot publicity for the "{{title}}", organized by {{org}}, scheduled for {{date}} from {{start}} to {{end}} at {{room}}.
{{speaker_line}}
{{purpose_line}}
{{speaker_para}}
We request permission to carry out on-foot publicity within the campus to effectively inform and encourage students to participate in this valuable session.

We sincerely appreciate your consideration of this request and thank you for your continued support.
Thank you.

With regards,
Chairperson {{org}}
{{chairperson}}

Staff In Charge {{org}}
{{staff}}
"""

def _build_letters(org, title, date, start, end, room, speaker, purpose, chairperson, staff):
    start = start or "10:00 AM"
    end = end or "12:00 PM"
    speaker_line = f"The session will be delivered by {speaker}." if speaker else ""
    purpose_line = purpose if purpose else f"The event aims to provide valuable learning and engagement for students."
    # More detailed speaker para if speaker present
    if speaker and "Alumni" in speaker:
        speaker_para = f"Through this interactive session, students will gain valuable insights from the speaker's academic and professional journey, along with practical advice on career growth, industry expectations, and opportunities beyond college. The session aims to inspire students by connecting them with a distinguished guest and encouraging meaningful interaction."
    elif speaker:
        speaker_para = f"The session will feature {speaker}, who will share experiences and valuable insights with students, providing practical guidance and inspiration as they prepare for their own academic and professional careers."
    else:
        speaker_para = ""
    chairperson = chairperson or DEFAULT_CHAIRPERSON
    staff = staff or DEFAULT_STAFF
    perm = PERMISSION_TEMPLATE.format(title=title, org=org, date=date, start=start, end=end, room=room, speaker_line=speaker_line, purpose_line=purpose_line, speaker_para=speaker_para, chairperson=chairperson, staff=staff)
    onfoot = ONFOOT_TEMPLATE.format(title=title, org=org, date=date, start=start, end=end, room=room, speaker_line=speaker_line, purpose_line=purpose_line, speaker_para=speaker_para, chairperson=chairperson, staff=staff)
    return perm.strip(), onfoot.strip()

@tool
def generate_permission_letter(organization: str, event_title: str, date: str, start_time: str, end_time: str, room: str, speaker: str = "", purpose: str = "", chairperson: str = "", staff_in_charge: str = "") -> str:
    """Generate high-quality permission letter for principal. Returns the letter text."""
    perm, _ = _build_letters(organization, event_title, date, start_time, end_time, room, speaker, purpose, chairperson, staff_in_charge)
    # Also persist to latest event
    try:
        from ..state import get_latest_event, save_event
        ev = get_latest_event()
        if ev:
            ev.permission_letter = perm
            ev.chairperson = chairperson or ev.chairperson
            ev.staff_in_charge = staff_in_charge or ev.staff_in_charge
            ev.speaker = speaker or ev.speaker
            ev.purpose = purpose or ev.purpose
            ev.start_time = start_time or ev.start_time
            ev.end_time = end_time or ev.end_time
            save_event(ev)
    except:
        pass
    return perm

@tool
def generate_onfoot_letter(organization: str, event_title: str, date: str, start_time: str, end_time: str, room: str, speaker: str = "", purpose: str = "", chairperson: str = "", staff_in_charge: str = "") -> str:
    """Generate on-foot publicity permission letter. Returns letter text."""
    _, onfoot = _build_letters(organization, event_title, date, start_time, end_time, room, speaker, purpose, chairperson, staff_in_charge)
    try:
        from ..state import get_latest_event, save_event
        ev = get_latest_event()
        if ev:
            ev.onfoot_letter = onfoot
            save_event(ev)
    except:
        pass
    return onfoot

@tool
def generate_announcement_preview(organization: str, event_title: str, date: str, room: str, expected_headcount: int, description: str = "") -> str:
    """Generate announcement preview for students. Returns announcement text."""
    desc = description or f"Join us for {event_title} - an exciting session organized by {organization}."
    ann = f"""Hello,

We are excited to announce: {event_title} by {organization}

Date: {date}
Venue: {room}
Expected: {expected_headcount} students

{desc}

Registration will open after approval - form link to be attached.

Seats are limited. Please register soon.
- CampusOps"""
    try:
        from ..state import get_latest_event, save_event
        ev = get_latest_event()
        if ev:
            ev.announcement_draft = ann
            save_event(ev)
    except:
        pass
    return ann
