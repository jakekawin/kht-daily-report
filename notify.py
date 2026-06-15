"""
KHT Daily Report — LINE Messaging API Notifier
รันทุกวัน 15:00 (Bangkok) ผ่าน GitHub Actions
ส่งแจ้งเตือนถ้ามีทีมยังไม่ส่งรายงาน
"""
import os
import json
import requests
from datetime import date
import gspread
from google.oauth2.service_account import Credentials

# ─── Config ────────────────────────────────────────────────
SHEET_ID        = os.environ.get('SHEET_ID', '1PbxKOycC5aGIF2P98BKXoWhLmH7wCS8YEDjc-lEYn5A')
LINE_TOKEN      = os.environ['LINE_CHANNEL_TOKEN']
LINE_GROUP_ID   = os.environ['LINE_GROUP_ID']
LINE_PUSH_URL   = 'https://api.line.me/v2/bot/message/push'

TH_MO = {1:'ม.ค.',2:'ก.พ.',3:'มี.ค.',4:'เม.ย.',5:'พ.ค.',6:'มิ.ย.',
          7:'ก.ค.',8:'ส.ค.',9:'ก.ย.',10:'ต.ค.',11:'พ.ย.',12:'ธ.ค.'}

# ─── Helpers ───────────────────────────────────────────────
def thd(d: str) -> str:
    """2026-06-15  →  15 มิ.ย. 2569"""
    dt = date.fromisoformat(d)
    return f"{dt.day} {TH_MO[dt.month]} {dt.year + 543}"

def load_db():
    """โหลด teams + reports จาก Google Sheet"""
    creds_raw = os.environ['GOOGLE_CREDENTIALS']
    creds_dict = json.loads(creds_raw)
    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)

    teams   = sh.worksheet('teams').get_all_records()
    reports = sh.worksheet('reports').get_all_records()
    return teams, reports

def send_line(text: str):
    """ส่งข้อความไปยัง LINE group"""
    headers = {
        'Authorization': f'Bearer {LINE_TOKEN}',
        'Content-Type':  'application/json',
    }
    payload = {
        'to': LINE_GROUP_ID,
        'messages': [{'type': 'text', 'text': text}],
    }
    r = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=10)
    print(f"LINE API → {r.status_code}: {r.text}")
    r.raise_for_status()

# ─── Main ──────────────────────────────────────────────────
def main():
    today     = date.today().isoformat()
    today_th  = thd(today)

    print(f"Checking reports for {today} ({today_th}) …")

    teams, reports = load_db()

    # กรองเฉพาะทีม Online
    active_teams   = [t for t in teams if str(t.get('active', '1')) != '0']
    # ทีมที่ส่งรายงานวันนี้
    submitted_ids  = {r['teamId'] for r in reports if r.get('date') == today}
    # ทีมที่ยังไม่ส่ง
    missing        = [t for t in active_teams if t['id'] not in submitted_ids]
    submitted_count = len(active_teams) - len(missing)

    if not missing:
        msg = (
            f"✅ KHT Daily Report\n"
            f"วันที่ {today_th}\n\n"
            f"ทุกทีมส่งรายงานครบแล้ว 🎉\n"
            f"({submitted_count}/{len(active_teams)} ทีม)"
        )
    else:
        names = '\n'.join(f"  🔴 {t['name']}" for t in missing)
        msg = (
            f"⏰ KHT Daily Report — แจ้งเตือน 15:00 น.\n"
            f"วันที่ {today_th}\n\n"
            f"📋 ยังไม่ส่งรายงาน ({len(missing)} ทีม):\n"
            f"{names}\n\n"
            f"✅ ส่งแล้ว {submitted_count}/{len(active_teams)} ทีม\n"
            f"⚠️ กรุณาส่งรายงานก่อน 17:00 น."
        )

    print("─" * 40)
    print(msg)
    print("─" * 40)
    send_line(msg)
    print("Done ✓")

if __name__ == '__main__':
    main()
