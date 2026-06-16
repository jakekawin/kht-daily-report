"""
preview_notify.py — แสดงตัวอย่างข้อความ LINE ที่จะส่งวันนี้ (ไม่ส่งจริง)
รัน: python3 preview_notify.py
"""
import json, sys
import gspread
from datetime import date, datetime, timezone, timedelta
from google.oauth2.service_account import Credentials

SHEET_ID = "1PbxKOycC5aGIF2P98BKXoWhLmH7wCS8YEDjc-lEYn5A"
BKK = timezone(timedelta(hours=7))
TH_MO = {1:'ม.ค.',2:'ก.พ.',3:'มี.ค.',4:'เม.ย.',5:'พ.ค.',6:'มิ.ย.',
          7:'ก.ค.',8:'ส.ค.',9:'ก.ย.',10:'ต.ค.',11:'พ.ย.',12:'ธ.ค.'}

SECRETS_PATH = "../Daily Report/.streamlit/secrets.toml"

# ─── load credentials ───────────────────────────────────
def load_creds():
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            print("❌ ต้องการ tomllib (Python 3.11+) หรือ pip install tomli")
            sys.exit(1)
    with open(SECRETS_PATH, "rb") as f:
        s = tomllib.load(f)
    return s["gcp_service_account"]

# ─── helpers ─────────────────────────────────────────────
def thd(d):
    dt = date.fromisoformat(str(d))
    return f"{dt.day} {TH_MO[dt.month]} {dt.year+543}"

def load_db(creds_dict):
    scopes = ['https://spreadsheets.google.com/feeds',
              'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    teams    = sh.worksheet('teams').get_all_records()
    reports  = sh.worksheet('reports').get_all_records()
    projects = sh.worksheet('projects').get_all_records()
    return teams, reports, projects

# ─── build message ────────────────────────────────────────
def build_msg(teams, reports, projects):
    proj_map = {str(p['id']): p['name'] for p in projects}

    now_bkk  = datetime.now(BKK)
    time_str = now_bkk.strftime("%H:%M")
    today    = now_bkk.date().isoformat()
    today_th = thd(today)

    active_teams  = [t for t in teams if str(t.get('active','1')) != '0']
    today_reports = {str(r['teamId']): r for r in reports if str(r.get('date','')) == today}
    submitted_ids = set(today_reports.keys())

    submitted = [t for t in active_teams if str(t['id']) in submitted_ids]
    missing   = [t for t in active_teams if str(t['id']) not in submitted_ids]

    def team_detail(t):
        r = today_reports[str(t['id'])]
        workers = int(r.get('workers', 0) or 0)
        raw_items = r.get('items', [])
        if isinstance(raw_items, str):
            try:    raw_items = json.loads(raw_items)
            except: raw_items = []
        lines = [f"  ✅ {t['name']} ({workers} คน)"]
        for it in raw_items:
            qty  = float(it.get('qty', 0) or 0)
            unit = it.get('unit', '')
            pn   = proj_map.get(str(it.get('pid','')), '?')
            prod = round(qty / workers, 2) if workers and qty > 0 else 0
            qty_s  = int(qty)  if qty  == int(qty)  else qty
            prod_s = int(prod) if prod == int(prod) else prod
            lines.append(f"     • {pn}: {qty_s} {unit} | Prod {prod_s}/คน")
        return '\n'.join(lines)

    submitted_lines = '\n'.join(team_detail(t) for t in submitted) or "  (ยังไม่มี)"
    missing_lines   = '\n'.join(f"  🔴 {t['name']}" for t in missing)
    header = f"{'✅' if not missing else '⏰'} KHT Daily Report — {time_str} น.\nวันที่ {today_th}"

    if not missing:
        return (f"{header}\n\nทุกทีมส่งรายงานครบแล้ว 🎉\n\n"
                f"📋 ส่งแล้ว ({len(submitted)}/{len(active_teams)} ทีม):\n{submitted_lines}")
    else:
        return (f"{header}\n\n"
                f"📋 ส่งแล้ว ({len(submitted)}/{len(active_teams)} ทีม):\n{submitted_lines}\n\n"
                f"🔴 ยังไม่ส่ง ({len(missing)} ทีม):\n{missing_lines}\n\n"
                f"⚠️ กรุณาส่งรายงานก่อน 17:00 น.")

# ─── main ─────────────────────────────────────────────────
if __name__ == '__main__':
    print("⏳ กำลังโหลดข้อมูลจาก Google Sheets …")
    creds_dict = load_creds()
    teams, reports, projects = load_db(creds_dict)
    msg = build_msg(teams, reports, projects)
    print("\n" + "═"*50)
    print(msg)
    print("═"*50)
