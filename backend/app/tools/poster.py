import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
from strands import tool
import os

def _get_font(size=40, bold=False):
    # Try system fonts, fallback to default
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()

def _generate_bytes(title, org, date, room, start, end, form_link, size=(1080,1080)):
    W,H = size
    # Colors: charcoal bg, lime accent
    bg = (10,10,10)
    lime = (198,255,0)
    white = (255,255,255)
    muted = (160,160,160)
    img = Image.new("RGB", (W,H), bg)
    draw = ImageDraw.Draw(img)
    # Accent bar top
    draw.rectangle([0,0,W,12], fill=lime)
    # Title block
    pad = 48
    y = 48
    # Org badge
    font_org = _get_font(24, False)
    draw.text((pad, y), org.upper(), fill=lime, font=font_org)
    y += 40
    # Title
    font_title = _get_font(56, True)
    # Wrap title
    words = title.split()
    lines = []
    cur = ""
    for w in words:
        test = cur + " " + w if cur else w
        if draw.textlength(test, font=font_title) < W-2*pad:
            cur = test
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    for line in lines[:3]:
        draw.text((pad, y), line, fill=white, font=font_title)
        y += 64
    y += 12
    # Divider
    draw.line([(pad,y),(W-pad,y)], fill=(40,40,40), width=2)
    y += 24
    # Details
    font_det = _get_font(28, False)
    font_lab = _get_font(20, False)
    details = [
        ("DATE", date),
        ("TIME", f"{start} – {end}" if start and end else (start or end or "")),
        ("VENUE", room),
    ]
    for lab, val in details:
        if not val: continue
        draw.text((pad, y), lab, fill=muted, font=font_lab)
        y+=22
        draw.text((pad, y), val, fill=white, font=font_det)
        y+=40
    # QR code bottom
    if form_link and "http" in form_link:
        try:
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=1)
            qr.add_data(form_link); qr.make(fit=True)
            qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            qsize = 220 if W==1080 and H==1080 else 260
            qimg = qimg.resize((qsize,qsize), Image.NEAREST)
            # Card behind QR
            qx = W - pad - qsize - 12
            qy = H - pad - qsize - 12
            # white card
            draw.rounded_rectangle([qx-12, qy-12, qx+qsize+12, qy+qsize+12], radius=16, fill=(255,255,255))
            img.paste(qimg, (qx, qy))
            # Label under QR
            draw.text((qx, qy+qsize+16), "Scan to Register", fill=lime, font=_get_font(18, True))
        except Exception as e:
            draw.text((pad, H-80), f"Register: {form_link[:40]}", fill=muted, font=_get_font(16))

    # Footer
    draw.text((pad, H-40), "CampusOps  •  Govt. Model Engineering College", fill=muted, font=_get_font(16))
    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

@tool
def generate_event_poster(event_id: str, variant: str = "square") -> str:
    """
    Generate a shareable poster for WhatsApp/Instagram.
    Args:
        event_id: Event UUID
        variant: square (1080x1080) or story (1080x1920)
    Returns:
        JSON with poster link or error.
    """
    import json as _j
    from ..state import get_event
    from ..config import BASE_DIR
    ev = get_event(event_id)
    if not ev:
        return _j.dumps({"error": "Event not found"})
    # Determine size
    size = (1080,1920) if variant=="story" else (1080,1080)
    link = ev.form_link or "https://campusops.mec.ac.in"
    data = _generate_bytes(ev.title or "Campus Event", ev.org or "CampusOps", ev.date or "", ev.room or "TBD", ev.start_time or "", ev.end_time or "", link, size=size)
    # Save to frontend public or backend data/posters
    out_dir = BASE_DIR / "data" / "posters"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{event_id}_{variant}.png"
    fpath = out_dir / fname
    with open(fpath, "wb") as f:
        f.write(data)
    # Also try to save to Drive if per-club creds available
    drive_link = ""
    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        creds = get_credentials(ev.org)
        if creds:
            drive = build("drive","v3", credentials=creds)
            # Find or create CampusOps Posters folder
            folder_id = None
            q = "name='CampusOps Posters' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res = drive.files().list(q=q, fields="files(id,name)").execute()
            if res.get("files"):
                folder_id = res["files"][0]["id"]
            else:
                folder = drive.files().create(body={"name":"CampusOps Posters","mimeType":"application/vnd.google-apps.folder"}, fields="id").execute()
                folder_id = folder["id"]
            media = MediaIoBaseUpload(io.BytesIO(data), mimetype="image/png")
            file = drive.files().create(body={"name": fname, "parents": [folder_id]}, media_body=media, fields="id,webViewLink").execute()
            drive_link = file.get("webViewLink","")
            # Make shareable
            try: drive.permissions().create(fileId=file["id"], body={"type":"anyone","role":"reader"}).execute()
            except: pass
    except Exception as e:
        pass
    return _j.dumps({"event_id": event_id, "variant": variant, "file": str(fpath), "drive_link": drive_link, "form_link": link, "size": size})

def poster_bytes_for_event(event_id: str, variant: str = "square") -> bytes:
    from ..state import get_event
    ev = get_event(event_id)
    if not ev: raise ValueError("Event not found")
    size = (1080,1920) if variant=="story" else (1080,1080)
    return _generate_bytes(ev.title or "Campus Event", ev.org or "CampusOps", ev.date or "", ev.room or "TBD", ev.start_time or "", ev.end_time or "", ev.form_link or "", size=size)
