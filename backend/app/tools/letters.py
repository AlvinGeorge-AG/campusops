import os
from strands import tool
from ..config import INSTITUTION_NAME, INSTITUTION_PLACE, DEFAULT_CHAIRPERSON, DEFAULT_STAFF

# Templates now built dynamically per org - see _get_templates()

def _get_templates(org: str = ""):
    """Resolve institution name/place dynamically from org settings, fallback to env config."""
    inst_name = INSTITUTION_NAME
    inst_place = INSTITUTION_PLACE
    if org:
        try:
            from ..state import get_org_settings
            s = get_org_settings(org)
            if s.institution_name:
                inst_name = s.institution_name
            if s.institution_place:
                inst_place = s.institution_place
        except:
            pass
    perm_tmpl = f"""To,
The Principal,
{inst_name},
{inst_place}.

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

    onfoot_tmpl = f"""To,
The Principal,
{inst_name},
{inst_place}.

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
    return perm_tmpl, onfoot_tmpl

def _resolve_defaults(org, chairperson, staff):
    """Pull chairperson/staff from org settings if not provided."""
    if (not chairperson or not staff) and org:
        try:
            from ..state import get_org_settings
            s = get_org_settings(org)
            if not chairperson and s.chairperson:
                chairperson = s.chairperson
            if not staff and s.staff_in_charge:
                staff = s.staff_in_charge
        except:
            pass
    chairperson = chairperson or DEFAULT_CHAIRPERSON
    staff = staff or DEFAULT_STAFF
    return chairperson, staff

def _build_letters(org, title, date, start, end, room, speaker, purpose, chairperson, staff):
    start = start or "10:00 AM"
    end = end or "12:00 PM"
    speaker_line = f"The session will be delivered by {speaker}." if speaker else ""
    purpose_line = purpose if purpose else f"The event aims to provide valuable learning and engagement for students."
    if speaker and "Alumni" in speaker:
        speaker_para = f"Through this interactive session, students will gain valuable insights from the speaker's academic and professional journey, along with practical advice on career growth, industry expectations, and opportunities beyond college. The session aims to inspire students by connecting them with a distinguished guest and encouraging meaningful interaction."
    elif speaker:
        speaker_para = f"The session will feature {speaker}, who will share experiences and valuable insights with students, providing practical guidance and inspiration as they prepare for their own academic and professional careers."
    else:
        speaker_para = ""
    chairperson, staff = _resolve_defaults(org, chairperson, staff)
    perm_tmpl, onfoot_tmpl = _get_templates(org)
    perm = perm_tmpl.format(title=title, org=org, date=date, start=start, end=end, room=room, speaker_line=speaker_line, purpose_line=purpose_line, speaker_para=speaker_para, chairperson=chairperson, staff=staff)
    onfoot = onfoot_tmpl.format(title=title, org=org, date=date, start=start, end=end, room=room, speaker_line=speaker_line, purpose_line=purpose_line, speaker_para=speaker_para, chairperson=chairperson, staff=staff)
    return perm.strip(), onfoot.strip()

@tool
def generate_permission_letter(organization: str, event_title: str, date: str, start_time: str, end_time: str, room: str, speaker: str = "", purpose: str = "", chairperson: str = "", staff_in_charge: str = "") -> str:
    """Generate high-quality permission letter for principal. Returns the letter text."""
    perm, _ = _build_letters(organization, event_title, date, start_time, end_time, room, speaker, purpose, chairperson, staff_in_charge)
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
