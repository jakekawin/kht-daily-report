"""
KHT Daily Report — LINE Messaging API Notifier
รันทุกวัน 15:00 และ 17:15 (Bangkok) ผ่าน GitHub Actions
ส่งแจ้งเตือนถ้ามีทีมยังไม่ส่งรายงาน
"""
import os
import json
import random
import requests
from datetime import date, datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

BKK = timezone(timedelta(hours=7))

# ─── Config ────────────────────────────────────────────────
SHEET_ID        = os.environ.get('SHEET_ID', '1PbxKOycC5aGIF2P98BKXoWhLmH7wCS8YEDjc-lEYn5A')
LINE_TOKEN      = os.environ['LINE_CHANNEL_TOKEN']
LINE_GROUP_ID   = os.environ['LINE_GROUP_ID']
LINE_PUSH_URL   = 'https://api.line.me/v2/bot/message/push'
APP_URL         = 'https://kht-report.streamlit.app'

TH_MO = {1:'ม.ค.',2:'ก.พ.',3:'มี.ค.',4:'เม.ย.',5:'พ.ค.',6:'มิ.ย.',
          7:'ก.ค.',8:'ส.ค.',9:'ก.ย.',10:'ต.ค.',11:'พ.ย.',12:'ธ.ค.'}

# ─── Helpers ───────────────────────────────────────────────
def norm_date(v) -> str:
    """ทำให้วันที่อยู่ในรูป 'YYYY-MM-DD' เสมอ ไม่ว่าจะมาจาก str ISO,
    str แบบ d/m/y หรือ m/d/y, หรือชนิด date/datetime ที่ Google Sheets คืนมา"""
    if v is None:
        return ''
    if isinstance(v, (datetime, date)):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    if not s:
        return ''
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d/%m/%y', '%m/%d/%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return s

def thd(d: str) -> str:
    """2026-06-15  →  15 มิ.ย. 2569"""
    dt = date.fromisoformat(norm_date(d))
    return f"{dt.day} {TH_MO[dt.month]} {dt.year + 543}"

def load_db():
    """โหลด teams + reports + projects จาก Google Sheet"""
    creds_raw = os.environ['GOOGLE_CREDENTIALS']
    creds_dict = json.loads(creds_raw)
    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)

    teams    = sh.worksheet('teams').get_all_records()
    reports  = sh.worksheet('reports').get_all_records()
    projects = sh.worksheet('projects').get_all_records()
    return teams, reports, projects

def send_line(messages: list) -> bool:
    """ส่ง messages (list of LINE message objects) ไปยัง LINE group
    LINE รองรับสูงสุด 5 messages ต่อ 1 push call → แบ่ง batch อัตโนมัติ
    คืน True ถ้าส่งครบทุก batch, False ถ้าโดน 429 (โควต้าหมด) กลางทาง"""
    headers = {
        'Authorization': f'Bearer {LINE_TOKEN}',
        'Content-Type':  'application/json',
    }
    for i in range(0, len(messages), 5):
        batch = messages[i:i+5]
        payload = {'to': LINE_GROUP_ID, 'messages': batch}
        r = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=10)
        print(f"LINE API batch[{i}] → {r.status_code}: {r.text[:200]}")
        if r.status_code == 429:
            print("⚠️ LINE monthly quota exceeded — หยุดส่ง batch ที่เหลือ")
            return False
        r.raise_for_status()
    return True

# ─── Main ──────────────────────────────────────────────────
def main():
    now_bkk   = datetime.now(BKK)
    time_str  = now_bkk.strftime("%H:%M")
    today     = now_bkk.date().isoformat()
    today_th  = thd(today)

    print(f"Checking reports for {today} ({today_th}) …")

    teams, reports, projects = load_db()

    proj_map = {str(p['id']): p['name'] for p in projects}

    # กรองเฉพาะทีม Online
    active_teams  = [t for t in teams if str(t.get('active', '1')) != '0']
    # report วันนี้ → dict by teamId (coerce เป็น str + normalize date กัน type ไม่ตรง)
    today_reports = {str(r['teamId']): r for r in reports if norm_date(r.get('date')) == today}
    submitted_ids = set(today_reports.keys())

    submitted = [t for t in active_teams if str(t['id']) in submitted_ids]
    missing   = [t for t in active_teams if str(t['id']) not in submitted_ids]

    def team_detail(t):
        """สร้างบรรทัดรายละเอียดของทีมที่ส่งแล้ว"""
        r       = today_reports[str(t['id'])]
        workers = int(r.get('workers', 0) or 0)
        # items อาจเป็น JSON string หรือ list
        raw_items = r.get('items', [])
        if isinstance(raw_items, str):
            try:    raw_items = json.loads(raw_items)
            except: raw_items = []
        note = str(r.get('note', '') or '').strip()
        lines = [f"  ✅ {t['name']} ({workers} คน)"]
        if note:
            lines.append(f"     📝 {note}")
        if raw_items:
            for it in raw_items:
                qty  = float(it.get('qty', 0) or 0)
                unit = it.get('unit', '')
                pn   = proj_map.get(str(it.get('pid', '')), '?')
                prod = round(qty / workers, 2) if workers and qty > 0 else 0
                qty_str  = int(qty) if qty == int(qty) else qty
                prod_str = int(prod) if prod == int(prod) else prod
                lines.append(f"     • {pn}: {qty_str} {unit} | Prod {prod_str}/คน")
        if not note and not raw_items:
            lines.append("     (ไม่มีรายการงาน)")
        return '\n'.join(lines)

    submitted_lines = '\n'.join(team_detail(t) for t in submitted) or "  (ยังไม่มี)"
    missing_lines   = '\n'.join(f"  🔴 {t['name']}" for t in missing)

    # รวมจำนวนคนทำงานทั้งหมดวันนี้
    total_workers = sum(
        int(today_reports[str(t['id'])].get('workers', 0) or 0)
        for t in submitted
    )

    header = (
        f"📲 ลงรายงาน: {APP_URL}\n\n"
        f"{'✅' if not missing else '⏰'} KHT Daily Report — {time_str} น.\n"
        f"วันที่ {today_th}"
    )

    worker_summary = f"👷 รวมคนงานวันนี้: {total_workers} คน"

    # ข้อความท้าย ปรับตามรอบเวลา (รอบ 17:15 ไม่บอก "ก่อน 17:00")
    deadline_note = (
        "⚠️ กรุณาส่งรายงานก่อน 17:00 น."
        if now_bkk.hour < 17
        else "⚠️ เลยกำหนด 17:00 น. แล้ว — ทีมที่ยังไม่ส่งกรุณาส่งโดยด่วน"
    )

    if not missing:
        msg = (
            f"{header}\n\n"
            f"ทุกทีมส่งรายงานครบแล้ว 🎉\n"
            f"{worker_summary}\n\n"
            f"📋 ส่งแล้ว ({len(submitted)}/{len(active_teams)} ทีม):\n"
            f"{submitted_lines}"
        )
    else:
        msg = (
            f"{header}\n\n"
            f"{worker_summary}\n\n"
            f"📋 ส่งแล้ว ({len(submitted)}/{len(active_teams)} ทีม):\n"
            f"{submitted_lines}\n\n"
            f"🔴 ยังไม่ส่ง ({len(missing)} ทีม):\n"
            f"{missing_lines}\n\n"
            f"{deadline_note}"
        )

    print("─" * 40)
    print(msg)
    print("─" * 40)

    # ── รวบรวมรูปภาพจากทุกทีมที่ส่งแล้ว ─────────────────────
    photo_msgs = []
    for t in submitted:
        rep    = today_reports[str(t['id'])]
        raw_ph = rep.get('photos', [])
        if isinstance(raw_ph, str):
            try:    raw_ph = json.loads(raw_ph)
            except: raw_ph = []
        for ph in raw_ph:
            if ph.get('url'):
                photo_msgs.append({
                    "type":               "image",
                    "originalContentUrl": ph['url'],
                    "previewImageUrl":    ph.get('thumb') or ph['url'],
                })

    # สุ่มรูปแล้วจำกัด 4 รูป (1 text + 4 image = 5 msg = 1 batch = ประหยัด quota)
    random.shuffle(photo_msgs)
    photo_msgs = photo_msgs[:4]
    print(f"Photos to send: {len(photo_msgs)}")

    # ── ส่ง text ก่อน (สำคัญสุด) แล้วค่อยส่งรูปแยก push ──────────
    # กัน text หายถ้าโควต้า LINE หมดตอนส่งรูป (รูป quota เท่ากันไม่ว่าจะรวมหรือแยก batch)
    if not send_line([{"type": "text", "text": msg}]):
        print("❌ ส่งข้อความหลักไม่สำเร็จ (โควต้า LINE หมด)")
    elif photo_msgs:
        if send_line(photo_msgs):
            print(f"ส่งรูปแล้ว {len(photo_msgs)} รูป")
        else:
            print("⚠️ ส่งข้อความหลักแล้ว แต่รูปไม่ได้ส่ง (โควต้าหมด)")
    print("Done ✓")

if __name__ == '__main__':
    main()
