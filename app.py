import streamlit as st
import json, calendar
from datetime import date, datetime, timedelta
from collections import defaultdict
import uuid
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ─── PAGE CONFIG ─────────────────────────────────────
st.set_page_config(
    page_title="KHT Daily Report",
    page_icon="🛠️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── CONSTANTS ───────────────────────────────────────
SHEET_ID   = "1PbxKOycC5aGIF2P98BKXoWhLmH7wCS8YEDjc-lEYn5A"
ROLE_ADMIN = "admin"
ROLE_SUPER = "supervisor"
ROLE_VIEW  = "viewer"
TH_MO   = ['','มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
            'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
TH_MO_S = ['','ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.',
            'ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']
SHEET_HEADERS = {
    "teams":         ["id", "name", "contractTypeId", "note", "active", "password"],
    "contractTypes": ["id", "name", "calcMode", "manRate"],
    "projects":      ["id", "name", "unit", "unitRate", "description", "active", "target"],
    "reports":       ["id", "date", "teamId", "workers", "note", "items", "posItems", "photos", "total"],
    "payments":      ["id", "tid", "y", "mo", "p", "paid", "paidDate", "note"],
    "positions":     ["id", "name", "dailyRate"],
}
CALC_MODES = {"unit_rate": "คิดตาม Unit Rate (ปริมาณ × ราคา)",
              "by_workers": "คิดตามจำนวนคน (คน × เรท)"}

# ─── CSS ─────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] > div:first-child { background-color:#1e3a5f !important; }
  [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,[data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label,[data-testid="stSidebar"] span { color:white !important; }
  [data-testid="stSidebar"] hr { border-color:rgba(255,255,255,0.2) !important; }
  [data-testid="stSidebar"] .stButton button {
    background:rgba(255,255,255,0.15); color:white;
    border:1px solid rgba(255,255,255,0.3); }
  .b-paid   { background:#d4edda; color:#155724; padding:3px 10px;
    border-radius:12px; font-size:0.78rem; font-weight:600; display:inline-block; }
  .b-unpaid { background:#f8d7da; color:#721c24; padding:3px 10px;
    border-radius:12px; font-size:0.78rem; font-weight:600; display:inline-block; }
  .period-hdr { background:#1e3a5f; color:white; padding:12px 18px;
    border-radius:8px 8px 0 0; font-weight:700; }
  div[data-testid="stMetric"] { background:white; border-radius:10px;
    padding:14px; box-shadow:0 2px 8px rgba(0,0,0,0.07); }
  div[data-testid="stMetric"] label { font-size:0.82rem !important; color:#777 !important; }
  div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size:1.6rem !important; color:#1e3a5f !important; }

  /* ── Mobile responsive ── */
  @media (max-width: 768px) {
    /* Stack columns vertically on small screens */
    [data-testid="column"] {
      width: 100% !important;
      min-width: 100% !important;
      flex: 1 1 100% !important;
    }
    /* More breathing room for content */
    .block-container {
      padding-left: 0.8rem !important;
      padding-right: 0.8rem !important;
      padding-top: 1rem !important;
    }
    /* Bigger touch targets for buttons */
    button {
      min-height: 48px !important;
      font-size: 1rem !important;
    }
    /* Full-width sidebar overlay on mobile */
    [data-testid="stSidebar"] {
      min-width: 80vw !important;
      max-width: 90vw !important;
    }
    /* Number inputs & text inputs easier to tap */
    input, select, textarea {
      font-size: 16px !important;
    }
    /* Metric cards: 1 per row */
    div[data-testid="stMetric"] {
      margin-bottom: 0.5rem;
    }
    /* ซ่อน sidebar บนมือถือ (top nav ทำหน้าที่แทน) */
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"]  { display: none !important; }
  }
</style>
""", unsafe_allow_html=True)

# ─── HELPERS ─────────────────────────────────────────
def _f(v):
    try: return float(v or 0)
    except: return 0.0

def _i(v):
    try: return int(v or 0)
    except: return 0

def uid(): return str(uuid.uuid4())[:8]

def next_id(table):
    """Return next sequential integer ID for a table (as string: '1','2','3',...)"""
    records = st.session_state.db.get(table, []) if 'db' in st.session_state else []
    nums = [int(r['id']) for r in records if str(r.get('id', '')).isdigit()]
    return str(max(nums) + 1) if nums else "1"
def N(n):  return f"{float(n or 0):,.2f}"
def today_str(): return date.today().isoformat()

def thd(s):
    if not s: return '-'
    try:
        y, m, d = s.split('-')
        return f"{int(d)} {TH_MO_S[int(m)]} {int(y)+543}"
    except: return s

def pdates(yr, mo, p):
    m = str(mo).zfill(2)
    if p == 1: return f"{yr}-{m}-01", f"{yr}-{m}-15"
    last = calendar.monthrange(yr, mo)[1]
    return f"{yr}-{m}-16", f"{yr}-{m}-{str(last).zfill(2)}"

# ─── GOOGLE SHEETS ────────────────────────────────────
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def _ws(sh, name):
    try: return sh.worksheet(name)
    except: return sh.add_worksheet(title=name, rows=2000, cols=20)

# ─── IMGBB PHOTO UPLOAD ────────────────────────────────
def upload_photo(file_bytes, filename, date_str):
    import base64, requests
    api_key = st.secrets.get("IMGBB_API_KEY", "")
    if not api_key:
        raise Exception("ไม่พบ IMGBB_API_KEY ใน secrets — กรุณาเพิ่มที่ Streamlit Cloud → Settings → Secrets")
    b64 = base64.b64encode(file_bytes).decode()
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": api_key, "image": b64, "name": filename},
        timeout=30,
    )
    data = resp.json()
    if not data.get("success"):
        raise Exception(data.get("error", {}).get("message", "อัปโหลดล้มเหลว"))
    d = data["data"]
    return {
        "id":    d["id"],
        "url":   d["url"],
        "thumb": d.get("thumb", {}).get("url") or d.get("medium", {}).get("url") or d["url"],
        "name":  filename,
    }

def load_db():
    try:
        gc = get_gc()
        sh = gc.open_by_key(SHEET_ID)
        def rws(name):
            try: return _ws(sh, name).get_all_records(default_blank='')
            except: return []

        teams         = rws("teams")
        contractTypes = rws("contractTypes")
        projects      = rws("projects")
        payments      = rws("payments")
        positions     = rws("positions")

        for p in projects:
            p['unitRate'] = _f(p.get('unitRate', 0))
            p['target']   = _f(p.get('target',   0))
        for pay in payments:
            raw = pay.get('paid', '')
            pay['paid'] = str(raw).upper() in ('TRUE', '1', 'YES')
            pay['y']  = _i(pay.get('y',  0))
            pay['mo'] = _i(pay.get('mo', 0))
            pay['p']  = _i(pay.get('p',  0))

        reports = []
        for r in rws("reports"):
            rec = dict(r)
            try: rec['items'] = json.loads(rec.get('items') or '[]')
            except: rec['items'] = []
            try: rec['posItems'] = json.loads(rec.get('posItems') or '[]')
            except: rec['posItems'] = []
            try: rec['photos'] = json.loads(rec.get('photos') or '[]')
            except: rec['photos'] = []
            rec['workers'] = _i(rec.get('workers', 0))
            rec['total']   = _f(rec.get('total', 0))
            for it in rec['items']:
                it['qty']  = _f(it.get('qty',  0))
                it['amt']  = _f(it.get('amt',  0))
                it['rate'] = _f(it.get('rate', 0))
            reports.append(rec)

        for pos in positions:
            pos['dailyRate'] = _f(pos.get('dailyRate', 0))

        return {"teams": teams, "contractTypes": contractTypes,
                "projects": projects, "reports": reports,
                "payments": payments, "positions": positions}
    except Exception as e:
        st.error(f"❌ โหลดข้อมูลไม่ได้: {e}")
        return {"teams": [], "projects": [], "reports": [], "payments": [],
                "contractTypes": [], "positions": []}

def save_db(tables=None):
    try:
        gc = get_gc()
        sh = gc.open_by_key(SHEET_ID)
        DB = st.session_state.db
        if tables is None: tables = list(SHEET_HEADERS.keys())
        elif isinstance(tables, str): tables = [tables]
        for tname in tables:
            headers = SHEET_HEADERS[tname]
            ws = _ws(sh, tname)
            ws.clear()
            rows = [headers]
            for item in DB.get(tname, []):
                row = []
                for h in headers:
                    val = item.get(h, '')
                    if isinstance(val, list):
                        val = json.dumps(val, ensure_ascii=False)
                    if isinstance(val, bool): val = str(val).upper()
                    if val is None: val = ''
                    row.append(val)
                rows.append(row)
            ws.update(rows)
    except Exception as e:
        st.error(f"❌ บันทึกไม่สำเร็จ: {e}")

# ─── DB ACCESSORS ─────────────────────────────────────
def get_team(tid):
    return next((x for x in st.session_state.db['teams'] if x['id'] == tid),
                {'name': '?', 'note': '', 'contractTypeId': ''})

def get_contract_type(ctid):
    return next((x for x in st.session_state.db.get('contractTypes', []) if x['id'] == ctid),
                {'name': '-', 'calcMode': 'unit_rate', 'manRate': 0})

def get_proj(pid):
    return next((x for x in st.session_state.db['projects'] if x['id'] == pid),
                {'name': '?', 'unit': '', 'unitRate': 0})

def period_total(tid, yr, mo, p):
    s, e = pdates(yr, mo, p)
    return sum(_f(r['total']) for r in st.session_state.db['reports']
               if r['teamId'] == tid and s <= r['date'] <= e)

def get_payment(tid, yr, mo, p):
    return next((x for x in st.session_state.db['payments']
                 if x['tid']==tid and _i(x['y'])==yr and
                    _i(x['mo'])==mo and _i(x['p'])==p), None)

# ─── EXCEL EXPORT ─────────────────────────────────────
def _build_period_excel(yr, mo):
    """สร้าง Excel สรุปรายงวด (2 งวด) + รายละเอียด + สรุปเดือน"""
    import io
    buf = io.BytesIO()
    m_str = str(mo).zfill(2)

    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for period in [1, 2]:
            s, e = pdates(yr, mo, period)
            sday = 1 if period == 1 else 16
            eday = 15 if period == 1 else calendar.monthrange(yr, mo)[1]

            sum_rows, detail_rows = [], []
            for t in st.session_state.db.get('teams', []):
                rpts_t = [r for r in st.session_state.db.get('reports', [])
                          if r['teamId'] == t['id'] and s <= r['date'] <= e]
                tot    = sum(_f(r.get('total', 0)) for r in rpts_t)
                manday = sum(_i(r.get('workers', 0)) for r in rpts_t)
                pay    = get_payment(t['id'], yr, mo, period)
                ip     = bool(pay and pay.get('paid'))

                sum_rows.append({
                    "ทีม":           t['name'],
                    "วันทำงาน":     len(rpts_t),
                    "คน-วัน":       manday,
                    "ยอดรวม (฿)":   round(tot, 2),
                    "สถานะ":         "จ่ายแล้ว" if ip else "ยังไม่จ่าย",
                    "วันที่จ่าย":   pay.get('paidDate', '') if pay else '',
                    "หมายเหตุ":      pay.get('note', '') if pay else '',
                })
                for r in sorted(rpts_t, key=lambda x: x['date']):
                    tname_r = t['name']
                    for it in r.get('items', []):
                        qty = _f(it.get('qty', 0))
                        if qty <= 0: continue
                        detail_rows.append({
                            "วันที่":        r['date'],
                            "ทีม":          tname_r,
                            "คนงาน":        r['workers'],
                            "ประเภทงาน":   get_proj(it['pid']).get('name', '?'),
                            "ปริมาณ":       qty,
                            "หน่วย":        it.get('unit', ''),
                            "ต้นทุน (฿)":  round(_f(r.get('total', 0)), 2),
                        })

            sheet_s = f"สรุปงวด{period}"
            sheet_d = f"รายละเอียดงวด{period}"
            pd.DataFrame(sum_rows).to_excel(writer, sheet_name=sheet_s, index=False)
            if detail_rows:
                pd.DataFrame(detail_rows).to_excel(writer, sheet_name=sheet_d, index=False)

        # ── Monthly summary ──
        cum_rows = []
        for t in st.session_state.db.get('teams', []):
            trpts = [r for r in st.session_state.db.get('reports', [])
                     if r['teamId'] == t['id'] and r['date'].startswith(f"{yr}-{m_str}")]
            tot    = sum(_f(r['total']) for r in trpts)
            manday = sum(_i(r['workers']) for r in trpts)
            pd_tot = 0.0
            for pp in [1, 2]:
                pay2 = get_payment(t['id'], yr, mo, pp)
                if pay2 and pay2.get('paid'):
                    s2, e2 = pdates(yr, mo, pp)
                    pd_tot += sum(_f(r['total']) for r in st.session_state.db.get('reports', [])
                                  if r['teamId'] == t['id'] and s2 <= r['date'] <= e2)
            cum_rows.append({
                "ทีม":          t['name'],
                "คน-วัน":      manday,
                "ยอดรวม (฿)":  round(tot, 2),
                "จ่ายแล้ว (฿)": round(pd_tot, 2),
                "ค้าง (฿)":    round(tot - pd_tot, 2),
            })
        if cum_rows:
            pd.DataFrame(cum_rows).to_excel(writer, sheet_name="สรุปรายเดือน", index=False)

    buf.seek(0)
    return buf.getvalue()

# ─── AUTH ─────────────────────────────────────────────
def check_login(role_key, pw):
    try: return pw == st.secrets["passwords"][role_key]
    except: return False

@st.cache_data(ttl=300)
def load_teams_for_login():
    """โหลดทีมจาก Sheet สำหรับ dropdown ตอน Login (cache 5 นาที)"""
    try:
        gc = get_gc()
        sh = gc.open_by_key(SHEET_ID)
        return sh.worksheet('teams').get_all_records(default_blank='')
    except:
        return []

def check_team_login(team_obj, pw):
    """ตรวจ password ของทีมจาก column 'password' ใน Sheet"""
    if not team_obj or not pw:
        return False
    raw = team_obj.get('password', '')
    # gspread อาจส่งตัวเลขเป็น int หรือ float
    if isinstance(raw, float) and raw == int(raw):
        stored = str(int(raw))
    else:
        stored = str(raw).strip()
    return bool(stored) and pw.strip() == stored

def login_page():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:40px 0 20px 0">
          <div style="font-size:3.5rem">🛠️</div>
          <h2 style="color:#1e3a5f;margin:8px 0 4px 0">KHT Daily Report</h2>
          <p style="color:#888;font-size:0.9rem">ระบบบันทึกการทำงาน</p>
        </div>
        """, unsafe_allow_html=True)

        LOGIN_OPTIONS = ["🔧 หัวหน้างาน", "👑 ผู้บริหาร (Admin)", "👁️ ดูข้อมูล"]
        role_display = st.selectbox("ระดับผู้ใช้งาน", LOGIN_OPTIONS, key="_login_role")

        # ── ถ้าเลือกหัวหน้างาน ให้เลือกทีมก่อน ──
        sel_team_obj  = None
        if role_display == "🔧 หัวหน้างาน":
            _tfl = load_teams_for_login()
            _active_tfl = [t for t in _tfl if str(t.get('active', '1')) != '0']
            if _active_tfl:
                _tfl_names = [t['name'] for t in _active_tfl]
                _chosen_tn = st.selectbox("👥 เลือกทีมงาน *", _tfl_names, key="_login_team")
                sel_team_obj = next((t for t in _active_tfl if t['name'] == _chosen_tn), None)
            else:
                st.warning("⚠️ ยังไม่มีทีม — กรุณาติดต่อ Admin")

        with st.form("login_form"):
            pw  = st.text_input("🔑 รหัสผ่าน", type="password")
            sub = st.form_submit_button("เข้าสู่ระบบ", type="primary", use_container_width=True)

        if sub:
            rmap = {
                "👑 ผู้บริหาร (Admin)": ROLE_ADMIN,
                "🔧 หัวหน้างาน":       ROLE_SUPER,
                "👁️ ดูข้อมูล":         ROLE_VIEW,
            }
            rk = rmap[role_display]
            if rk == ROLE_SUPER:
                ok = check_team_login(sel_team_obj, pw)
            else:
                ok = check_login(rk, pw)

            if ok:
                st.session_state.logged_in  = True
                st.session_state.role       = rk
                st.session_state.team_id    = sel_team_obj['id']   if sel_team_obj else None
                st.session_state.team_name  = sel_team_obj['name'] if sel_team_obj else None
                with st.spinner("⏳ กำลังโหลดข้อมูล..."):
                    st.session_state.db = load_db()
                st.session_state.wi = []
                st.session_state.edit_id = None
                st.session_state.page_key = None
                st.rerun()
            else:
                st.error("❌ รหัสผ่านไม่ถูกต้อง")

# ─── SESSION STATE INIT ───────────────────────────────
for k, v in [('logged_in', False), ('role', None), ('wi', []),
              ('pos_items', []), ('photos', []), ('upload_key', 0),
              ('_photo_edit', None), ('edit_id', None), ('page_key', None),
              ('_save_msg', None), ('_sidebar_nav', None), ('_pending_nav', None),
              ('_top_nav', None), ('team_id', None), ('team_name', None)]:
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.logged_in:
    login_page()
    st.stop()

if 'db' not in st.session_state:
    with st.spinner("⏳ กำลังโหลดข้อมูล..."):
        st.session_state.db = load_db()

DB            = st.session_state.db
role          = st.session_state.role
can_edit      = role in [ROLE_ADMIN, ROLE_SUPER]
can_see_money = role == ROLE_ADMIN
can_summary   = role == ROLE_ADMIN
can_settings  = role == ROLE_ADMIN

ROLE_LABEL = {ROLE_ADMIN:"👑 ผู้บริหาร", ROLE_SUPER:"🔧 หัวหน้างาน", ROLE_VIEW:"👁️ ดูข้อมูล"}

# ─── SIDEBAR ─────────────────────────────────────────
pages_map = {}
pages_map["📊 Dashboard"]           = "dashboard"
if can_edit:    pages_map["➕ บันทึกงานประจำวัน"] = "add"
pages_map["🔍 ดูข้อมูลรายวัน"]      = "view"
if can_summary: pages_map["📈 สรุปรายงวด"]       = "summary"
if can_edit:    pages_map["📉 Productivity"]       = "productivity"
if can_settings:pages_map["⚙️ ตั้งค่าระบบ"]      = "settings"

# Validate stored page_key
if st.session_state.page_key not in pages_map:
    st.session_state.page_key = list(pages_map.keys())[0]
# Sync sidebar radio with page_key on first load or when invalid
if st.session_state.get('_sidebar_nav') not in pages_map:
    st.session_state['_sidebar_nav'] = st.session_state.page_key
# Apply pending programmatic navigation BEFORE the radio widget is created
if st.session_state.get('_pending_nav') in pages_map:
    st.session_state['_sidebar_nav'] = st.session_state['_pending_nav']
    st.session_state['_pending_nav'] = None

with st.sidebar:
    st.markdown(f"""
    <div style="padding:4px 0 14px 0">
      <div style="font-size:1.25rem;font-weight:700">🪖 KHT Daily Report</div>
      <div style="font-size:0.78rem;color:#e07b2b">ระบบบันทึกการทำงาน</div>
      <div style="font-size:0.75rem;color:rgba(255,255,255,0.55);margin-top:5px">
        {ROLE_LABEL[role]}{f" · {st.session_state.get('team_name','')}" if st.session_state.get('team_name') else ''}</div>
    </div>
    """, unsafe_allow_html=True)

    chosen  = st.radio("เมนู", list(pages_map.keys()),
                        key="_sidebar_nav", label_visibility="collapsed")
    st.session_state.page_key = chosen
    PAGE = pages_map[chosen]

    st.markdown("---")
    if st.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
        with st.spinner("กำลังโหลด..."):
            st.session_state.db = load_db()
        st.rerun()

    if can_see_money:
        export_bytes = json.dumps(DB, ensure_ascii=False, indent=2).encode('utf-8')
        st.download_button("📥 Export JSON", data=export_bytes,
                           file_name=f"kht-{today_str()}.json",
                           mime="application/json", use_container_width=True)

    st.markdown("---")
    if st.button("🚪 ออกจากระบบ", use_container_width=True):
        for k in ['logged_in','role','db','wi','edit_id','page_key','_sidebar_nav',
                   'team_id','team_name']:
            st.session_state.pop(k, None)
        st.rerun()

# ─── TOP NAV BAR (mobile-primary, desktop-secondary) ────────────
_pages_list = list(pages_map.keys())
st.session_state['_top_nav'] = st.session_state.page_key   # sync before widget
_tn1, _tn2, _tn3 = st.columns([4, 1, 1])
with _tn1:
    _top_pg = st.selectbox("📍", _pages_list, key="_top_nav",
                           label_visibility="collapsed")
    if _top_pg != st.session_state.page_key:
        st.session_state['_pending_nav'] = _top_pg
        st.rerun()
with _tn2:
    if st.button("🔄", use_container_width=True, help="รีเฟรชข้อมูล"):
        with st.spinner("..."):
            st.session_state.db = load_db()
        st.rerun()
with _tn3:
    if st.button("🚪", use_container_width=True, help="ออกจากระบบ"):
        for k in ['logged_in','role','db','wi','edit_id','page_key',
                  '_sidebar_nav','team_id','team_name']:
            st.session_state.pop(k, None)
        st.rerun()
st.markdown("---")

# ═══════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════
if PAGE == "dashboard":
    now  = date.today()
    yr, mo, dy = now.year, now.month, now.day

    # ── Date picker: เลือกวันที่ดู (default = วันนี้) ──
    dh1, dh2 = st.columns([1, 3])
    with dh1:
        sel_date = st.date_input("📅 เลือกวันที่", value=now, label_visibility="collapsed",
                                 key="dash_date")
    with dh2:
        is_today = (sel_date == now)
        lbl_date = "วันนี้" if is_today else thd(sel_date.isoformat())
        st.markdown(f"<div style='padding-top:0.5rem;color:#555'>ดูข้อมูลวันที่ <b>{lbl_date}</b></div>",
                    unsafe_allow_html=True)

    sd_yr, sd_mo, sd_dy = sel_date.year, sel_date.month, sel_date.day
    p_cur = 1 if sd_dy <= 15 else 2
    ps, pe = pdates(sd_yr, sd_mo, p_cur)
    ms = f"{sd_yr}-{str(sd_mo).zfill(2)}-01"
    me = f"{sd_yr}-{str(sd_mo).zfill(2)}-31"
    sel_str = sel_date.isoformat()

    period_lbl = f"งวดที่ {p_cur}: {'1–15' if p_cur==1 else '16–สิ้นเดือน'} {TH_MO[sd_mo]} {sd_yr+543}"
    st.markdown(f"### 📊 Dashboard &nbsp;<span style='font-size:0.85rem;color:#777'>{period_lbl}</span>",
                unsafe_allow_html=True)

    sel_rpts    = [r for r in DB['reports'] if r['date'] == sel_str]
    period_rpts = [r for r in DB['reports'] if ps <= r['date'] <= pe]
    month_rpts  = [r for r in DB['reports'] if ms <= r['date'] <= me]

    if can_see_money:
        sel_tot    = sum(_f(r['total']) for r in sel_rpts)
        period_tot = sum(_f(r['total']) for r in period_rpts)
        month_tot  = sum(_f(r['total']) for r in month_rpts)
        unpaid = sum(
            period_total(t['id'], yr, mo, p)
            for t in DB['teams'] for p in [1,2]
            if not (lambda pay: pay and pay.get('paid'))(get_payment(t['id'],yr,mo,p))
        )
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric(f"📅 ยอด{lbl_date}",  f"฿ {N(sel_tot)}")
        with c2: st.metric("📆 ยอดงวดนี้",        f"฿ {N(period_tot)}")
        with c3: st.metric("🗓️ ยอดเดือนนี้",      f"฿ {N(month_tot)}")
        with c4: st.metric("⚠️ ค้างชำระ",          f"฿ {N(unpaid)}")
    else:
        c1,c2,c3 = st.columns(3)
        with c1: st.metric(f"📅 รายงาน{lbl_date}",  f"{len(sel_rpts)} รายการ")
        with c2: st.metric("📆 รายงานงวดนี้",         f"{len(period_rpts)} รายการ")
        with c3: st.metric("🗓️ รายงานเดือนนี้",       f"{len(month_rpts)} รายการ")

    st.markdown("---")
    # ── ทีมที่ยังไม่ส่งรายงาน ──────────────────────────
    active_teams   = [t for t in DB['teams'] if str(t.get('active','1')) != '0']
    submitted_tids = {r['teamId'] for r in sel_rpts}
    missing_teams  = [t for t in active_teams if t['id'] not in submitted_tids]
    n_submitted    = len(active_teams) - len(missing_teams)
    pct_submit     = int(n_submitted / len(active_teams) * 100) if active_teams else 0

    col_miss, col_met1, col_met2, col_met3 = st.columns([2.5, 1, 1, 1])
    with col_miss:
        if missing_teams:
            names_str = " · ".join(f"🔴 {t['name']}" for t in missing_teams)
            st.markdown(
                f"<div style='background:#fff3cd;border-left:4px solid #ffc107;"
                f"padding:10px 14px;border-radius:6px;font-size:0.9rem'>"
                f"<b>⏳ ยังไม่ส่งรายงาน{lbl_date}:</b><br>{names_str}</div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div style='background:#d4edda;border-left:4px solid #28a745;"
                f"padding:10px 14px;border-radius:6px;font-size:0.9rem'>"
                f"✅ <b>ทุกทีมส่งรายงาน{lbl_date}แล้ว</b></div>",
                unsafe_allow_html=True)
    with col_met1: st.metric("✅ ส่งรายงาน", f"{n_submitted}/{len(active_teams)} ทีม",
                              f"{pct_submit}%")
    with col_met2: st.metric("👥 ทีม Online", len(active_teams))
    with col_met3: st.metric("🔧 ประเภทงาน", len([p for p in DB['projects'] if str(p.get('active','1')) != '0']))

    # ── Burn Rate + Period Progress (Admin) ──────────────
    if can_see_money:
        st.markdown("---")
        eday_p  = 15 if p_cur == 1 else calendar.monthrange(sd_yr, sd_mo)[1]
        sday_p  = 1  if p_cur == 1 else 16
        days_el = max(sd_dy - sday_p + 1, 1)
        days_tot= eday_p - sday_p + 1
        pct_pgr = min(days_el / days_tot * 100, 100)
        cost_pd = period_tot / days_el if days_el else 0
        # week cost vs prev week
        wk_s    = sel_date - timedelta(days=6)
        wk_ps   = wk_s    - timedelta(days=7)
        wk_pe   = wk_s    - timedelta(days=1)
        wk_cost = sum(_f(r['total']) for r in DB['reports']
                      if wk_s.isoformat() <= r['date'] <= sel_str)
        wk_prev = sum(_f(r['total']) for r in DB['reports']
                      if wk_ps.isoformat() <= r['date'] <= wk_pe.isoformat())
        delta_w = wk_cost - wk_prev
        period_manday = sum(_i(r['workers']) for r in period_rpts)
        cpmd    = period_tot / period_manday if period_manday else 0

        bk1, bk2, bk3, bk4 = st.columns(4)
        with bk1:
            st.metric("⏱️ ผ่านไปในงวด",
                      f"{days_el}/{days_tot} วัน",
                      f"{pct_pgr:.0f}% ของงวด")
        with bk2:
            st.metric("💸 เฉลี่ย/วัน (งวดนี้)", f"฿ {N(cost_pd)}")
        with bk3:
            st.metric("📊 สัปดาห์นี้ (7 วัน)",
                      f"฿ {N(wk_cost)}",
                      f"{'+' if delta_w >= 0 else ''}{N(delta_w)} vs สัปดาห์ก่อน",
                      delta_color="inverse")
        with bk4:
            st.metric("👷 ฿/Man-day (งวดนี้)", f"฿ {N(cpmd)}")

    # ── 14-day Cost Bar Chart (Admin) ────────────────────
    if can_see_money:
        st.markdown("---")
        st.markdown("#### 📊 ต้นทุนย้อนหลัง 14 วัน")
        dates_14  = [(sel_date - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
        costs_14  = [sum(_f(r['total']) for r in DB['reports'] if r['date'] == d) for d in dates_14]
        labels_14 = [f"{d[8:]}/{d[5:7]}" for d in dates_14]
        chart14   = pd.DataFrame({"วันที่": labels_14, "ต้นทุน (฿)": costs_14}).set_index("วันที่")
        st.bar_chart(chart14)

    # ── Team Leaderboard งวดนี้ ─────────────────────────
    st.markdown("---")
    st.markdown(f"#### 🏆 สถิติทีม — งวดที่ {p_cur}")
    team_stats = []
    for t in active_teams:
        tot_t   = period_total(t['id'], sd_yr, sd_mo, p_cur)
        rpts_t  = [r for r in period_rpts if r['teamId'] == t['id']]
        manday_t= sum(_i(r['workers']) for r in rpts_t)
        days_t  = len(rpts_t)
        cpmd_t  = round(tot_t / manday_t, 0) if manday_t else 0
        sub_today = "✅" if t['id'] in submitted_tids else "⏳"
        row_t = {
            "ทีม":           t['name'],
            "ส่งวันนี้":     sub_today,
            "วันทำงาน":     days_t,
            "Man-days":      manday_t,
        }
        if can_see_money:
            row_t["ต้นทุนงวดนี้ (฿)"] = round(tot_t, 0)
            row_t["฿/Man-day"]         = cpmd_t
        team_stats.append(row_t)
    if can_see_money:
        team_stats.sort(key=lambda x: x.get("ต้นทุนงวดนี้ (฿)", 0), reverse=True)
    else:
        team_stats.sort(key=lambda x: x.get("Man-days", 0), reverse=True)
    if team_stats:
        st.dataframe(pd.DataFrame(team_stats), hide_index=True, use_container_width=True)

    # ── รายละเอียดผลงานวันที่เลือก ──────────────────────
    st.markdown("---")
    st.markdown(f"#### 📋 ผลงาน{lbl_date}")
    if not sel_rpts:
        st.info(f"ไม่มีข้อมูล{lbl_date}")
    else:
        rows = []
        for r in sel_rpts:
            items_str = " | ".join(
                f"{get_proj(it['pid'])['name']}: {it['qty']} {it['unit']}"
                + (f" = {N(it['amt'])}฿" if can_see_money else "")
                for it in r['items']
            )
            row = {"ทีม": get_team(r['teamId'])['name'], "คนงาน": r['workers'],
                   "รายการงาน": items_str}
            if can_see_money: row["รวม (฿)"] = N(r['total'])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════
# PAGE: ADD / EDIT REPORT
# ═══════════════════════════════════════════════════════
elif PAGE == "add" and can_edit:
    st.markdown("### ➕ บันทึกงานประจำวัน")

    edit_rec = None
    if st.session_state.edit_id:
        edit_rec = next((r for r in DB['reports'] if r['id']==st.session_state.edit_id), None)
        if edit_rec and not st.session_state.wi:
            st.session_state.wi = [dict(i) for i in edit_rec['items']]
        if edit_rec and not st.session_state.pos_items:
            _raw_pi = edit_rec.get('posItems', [])
            if isinstance(_raw_pi, str):
                try: _raw_pi = json.loads(_raw_pi or '[]')
                except: _raw_pi = []
            st.session_state.pos_items = [dict(i) for i in _raw_pi if isinstance(i, dict)]
        if edit_rec and st.session_state.get('_photo_edit') != st.session_state.edit_id:
            _raw_ph = edit_rec.get('photos', [])
            if isinstance(_raw_ph, str):
                try: _raw_ph = json.loads(_raw_ph or '[]')
                except: _raw_ph = []
            st.session_state.photos = [dict(p) for p in _raw_ph if isinstance(p, dict)]
            st.session_state['_photo_edit'] = st.session_state.edit_id
        if edit_rec:
            st.info(f"✏️ กำลังแก้ไข: {thd(edit_rec['date'])} — {get_team(edit_rec['teamId'])['name']}")

    col1, col2 = st.columns([1,1])
    with col1:
        default_dt = datetime.strptime(edit_rec['date'],'%Y-%m-%d').date() if edit_rec else date.today()
        r_date = st.date_input("📅 วันที่ *", value=default_dt)
    with col2:
        _all_teams  = DB['teams']
        _active_t   = [t for t in _all_teams if str(t.get('active','1')) != '0']
        _show_teams = _active_t if not (edit_rec and edit_rec.get('teamId') not in {t['id'] for t in _active_t}) else _all_teams
        tnames = [t['name'] for t in _show_teams]
        tids   = [t['id']   for t in _show_teams]
        if not tnames:
            st.warning("ยังไม่มีทีม — ขอให้ Admin เพิ่มทีมก่อน"); st.stop()

        _locked_tid = st.session_state.get('team_id')
        if role == ROLE_SUPER and _locked_tid and not edit_rec:
            # ล็อคทีมตามที่ Login — supervisor ไม่สามารถเปลี่ยนทีมได้
            _lock_obj = next((t for t in _all_teams if t['id'] == _locked_tid), None)
            if _lock_obj:
                st.text_input("👥 ทีมทำงาน *", value=_lock_obj['name'], disabled=True)
                r_tname = _lock_obj['name']
                r_tid   = _lock_obj['id']
            else:
                r_tname = st.selectbox("👥 ทีมทำงาน *", tnames)
                r_tid   = tids[tnames.index(r_tname)]
        else:
            def_ti = tids.index(edit_rec['teamId']) if edit_rec and edit_rec['teamId'] in tids else 0
            r_tname = st.selectbox("👥 ทีมทำงาน *", tnames, index=def_ti)
            r_tid   = tids[tnames.index(r_tname)]
    # ── Determine calc mode (needs r_tid already set in col2) ──
    _team_obj_pre = get_team(r_tid)
    _team_ct_pre  = get_contract_type(_team_obj_pre.get('contractTypeId', ''))
    calc_mode_pre = _team_ct_pre.get('calcMode', 'unit_rate')

    if calc_mode_pre == 'by_workers':
        st.caption("🧑‍🔧 คนงานรวม")
        workers_display = st.empty()
        r_workers = 0
    else:
        _wc1, _wc2 = st.columns([1, 2])
        with _wc1:
            r_workers = st.number_input("🧑‍🔧 จำนวนคนงาน *", min_value=0,
                                        value=_i(edit_rec['workers']) if edit_rec else 0)
    r_note = st.text_area("📝 รายงานการทำงาน",
                          value=edit_rec.get('note','') if edit_rec else '',
                          height=90,
                          placeholder="บันทึกรายละเอียดการทำงานประจำวัน...")

    # ── รูปภาพ ─────────────────────────────────────────
    if st.session_state.photos:
        st.markdown("**📷 รูปภาพที่แนบไว้**")
        _ph_cols = st.columns(min(len(st.session_state.photos), 3))
        _to_rm_ph = None
        for _i_ph, _ph in enumerate(st.session_state.photos):
            with _ph_cols[_i_ph % 3]:
                try:
                    st.image(_ph.get('url') or _ph.get('thumb', ''), use_container_width=True)
                except:
                    st.caption(_ph.get('name', f"รูป {_i_ph+1}"))
                st.caption(_ph.get('name',''))
                if st.button("🗑️ ลบ", key=f"rmph_{_i_ph}"):
                    _to_rm_ph = _i_ph
        if _to_rm_ph is not None:
            st.session_state.photos.pop(_to_rm_ph); st.rerun()
    _upload_key = st.session_state.get('upload_key', 0)
    new_photos = st.file_uploader(
        "📷 แนบรูปภาพ (อัปโหลดอัตโนมัติเมื่อบันทึก)",
        type=['jpg', 'jpeg', 'png', 'webp'],
        accept_multiple_files=True,
        key=f"photo_upload_{_upload_key}",
    )

    # ── Recheck: ตรวจว่ามีรายงานสำหรับวัน+ทีมนี้อยู่แล้วหรือยัง ──
    if not st.session_state.edit_id:
        existing = next((r for r in DB['reports']
                         if r['date'] == r_date.isoformat() and r['teamId'] == r_tid), None)
        if existing:
            st.warning(
                f"⚠️ มีรายงานของ **{r_tname}** วันที่ **{thd(r_date.isoformat())}** อยู่แล้ว",
                icon="⚠️"
            )
            if st.button("✏️ โหลดเพื่อแก้ไขรายงานนี้", type="secondary"):
                st.session_state.edit_id = existing['id']
                st.session_state.wi = []
                st.session_state.pos_items = []
                st.session_state.photos = []
                st.session_state['_photo_edit'] = None
                st.rerun()

    # ── Use precomputed calc mode ──
    team_obj  = _team_obj_pre
    team_ct   = _team_ct_pre
    calc_mode = calc_mode_pre
    man_rate  = _f(team_ct.get('manRate', 0))

    st.markdown("---")

    if calc_mode == 'by_workers':
        # ── Position-based cost: Σ(count × dailyRate) ──
        positions_list = DB.get('positions', [])
        pnames_pos     = [p['name'] for p in positions_list]
        pids_pos       = [p['id']   for p in positions_list]

        if not positions_list:
            st.warning("⚠️ ยังไม่มีตำแหน่งงาน — ขอให้ Admin เพิ่มในหน้าตั้งค่าระบบ > ตำแหน่งงาน")
        else:
            st.markdown("")
            st.markdown("**👷 ตำแหน่งงานและจำนวนคน**")
            to_rm_pos = None

            for idx, pi in enumerate(st.session_state.pos_items):
                pc1, pc2, pc3, pc4 = st.columns([3, 1.5, 1.2, 0.5])
                with pc1:
                    cur_pos_i = pids_pos.index(pi['posId']) if pi.get('posId') in pids_pos else 0
                    sel_pos = st.selectbox(f"ตำแหน่ง#{idx+1}", pnames_pos, index=cur_pos_i,
                                           key=f"possel_{idx}", label_visibility="collapsed")
                    sp2 = positions_list[pnames_pos.index(sel_pos)]
                    pi['posId']    = sp2['id']
                    pi['posName']  = sp2['name']
                    pi['dailyRate'] = sp2['dailyRate']
                with pc2:
                    if can_see_money:
                        st.text_input("Rate/วัน", value=f"฿{N(pi['dailyRate'])}", disabled=True,
                                      key=f"posrate_{idx}", label_visibility="collapsed")
                with pc3:
                    pi['count'] = st.number_input("จำนวนคน", min_value=0,
                                                  value=int(pi.get('count', 1)),
                                                  step=1, key=f"poscount_{idx}",
                                                  label_visibility="collapsed")
                with pc4:
                    if st.button("🗑️", key=f"posdel_{idx}"): to_rm_pos = idx

            if to_rm_pos is not None:
                st.session_state.pos_items.pop(to_rm_pos); st.rerun()

            ab2, _ = st.columns([1.8, 5])
            with ab2:
                if st.button("➕ เพิ่มตำแหน่งงาน"):
                    fp2 = positions_list[0]
                    st.session_state.pos_items.append({
                        'posId': fp2['id'], 'posName': fp2['name'],
                        'dailyRate': fp2['dailyRate'], 'count': 1
                    })
                    st.rerun()

        # ── Compute totals ──
        r_workers  = sum(int(pi.get('count', 0)) for pi in st.session_state.pos_items)
        auto_total = sum(int(pi.get('count', 0)) * _f(pi.get('dailyRate', 0))
                         for pi in st.session_state.pos_items)

        # Update col3 placeholder
        if st.session_state.pos_items:
            workers_display.metric("คนงานรวม", f"{r_workers} คน", label_visibility="collapsed")

        if can_see_money and st.session_state.pos_items:
            st.info(f"📋 **{team_ct['name']}** — คิดตามตำแหน่งงาน | "
                    f"คนงานรวม: **{r_workers} คน** | รวม: **฿{N(auto_total)}**")
        elif st.session_state.pos_items:
            st.info(f"📋 **{team_ct['name']}** — คิดตามตำแหน่งงาน | คนงานรวม: **{r_workers} คน**")

        st.markdown("")
        st.markdown("**📋 รายการงาน (สำหรับติดตาม Productivity)**")
        _active_projs = sorted([p for p in DB['projects'] if str(p.get('active','1')) != '0'],
                               key=lambda x: str(x.get('name', '')))
        if not _active_projs:
            st.warning("ยังไม่มีประเภทงาน Online — ขอให้ Admin เพิ่มหรือเปิดใช้งานก่อน")
        else:
            pnames = [p['name'] for p in _active_projs]
            pids   = [p['id']   for p in _active_projs]
            to_rm  = None

            for idx, item in enumerate(st.session_state.wi):
                c1, c2, c3, c4 = st.columns([3, 1, 1.5, 0.5])
                with c1:
                    cur_pi = pids.index(item['pid']) if item.get('pid') in pids else 0
                    sel = st.selectbox(f"งาน#{idx+1}", pnames, index=cur_pi,
                                       key=f"psel_{idx}", label_visibility="collapsed")
                    sp = _active_projs[pnames.index(sel)]
                    item['pid']  = sp['id']
                    item['unit'] = sp['unit']
                    item['rate'] = 0
                with c2:
                    st.text_input("หน่วย", value=item['unit'], disabled=True,
                                  key=f"unit_{idx}", label_visibility="collapsed")
                with c3:
                    item['qty'] = st.number_input("ปริมาณ", min_value=0.0,
                                                  value=float(item.get('qty', 0)),
                                                  step=0.01, key=f"qty_{idx}",
                                                  label_visibility="collapsed")
                    item['amt'] = 0
                with c4:
                    if st.button("🗑️", key=f"del_{idx}"): to_rm = idx

            if to_rm is not None:
                st.session_state.wi.pop(to_rm); st.rerun()

            ab, _ = st.columns([1, 5])
            with ab:
                if st.button("➕ เพิ่มรายการงาน"):
                    fp = DB['projects'][0]
                    st.session_state.wi.append({'id': uid(), 'pid': fp['id'],
                        'unit': fp['unit'], 'rate': 0, 'qty': 0, 'amt': 0})
                    st.rerun()

        st.markdown("---")
        s1, s2, _ = st.columns([1.2, 1, 5])
        with s1: save_btn = st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True)
        with s2:
            if st.button("🗑️ ล้างข้อมูล", use_container_width=True):
                st.session_state.wi = []
                st.session_state.pos_items = []
                st.session_state.photos = []
                st.session_state['_photo_edit'] = None
                st.session_state['upload_key'] = st.session_state.get('upload_key', 0) + 1
                st.session_state.edit_id = None
                st.rerun()

        if save_btn:
            if r_workers <= 0:
                st.error("กรุณาระบุตำแหน่งงานอย่างน้อย 1 ตำแหน่ง และจำนวนคนงาน")
            else:
                _rid = st.session_state.edit_id or next_id('reports')
                if new_photos:
                    with st.spinner(f"กำลังอัปโหลดรูปภาพ {len(new_photos)} รูป..."):
                        for _uf in new_photos:
                            try:
                                _ph = upload_photo(_uf.getvalue(), _uf.name, r_date.isoformat())
                                st.session_state.photos.append(_ph)
                            except Exception as _e:
                                st.warning(f"อัปโหลดรูป '{_uf.name}' ไม่สำเร็จ: {_e}")
                rec = {
                    'id':       _rid,
                    'date':     r_date.isoformat(),
                    'teamId':   r_tid,
                    'workers':  r_workers,
                    'note':     r_note,
                    'items':    [dict(w) for w in st.session_state.wi],
                    'posItems': json.dumps([dict(pi) for pi in st.session_state.pos_items]),
                    'photos':   list(st.session_state.photos),
                    'total':    auto_total,
                }
                with st.spinner("กำลังบันทึก..."):
                    if st.session_state.edit_id:
                        idx2 = next((i for i,r in enumerate(DB['reports']) if r['id']==rec['id']), None)
                        if idx2 is not None: DB['reports'][idx2] = rec
                        msg = "✅ แก้ไขสำเร็จ"
                    else:
                        DB['reports'].append(rec)
                        msg = "✅ บันทึกสำเร็จ"
                    save_db("reports")
                st.session_state['_save_msg'] = msg
                st.session_state.pos_items = []
                st.session_state.photos = []
                st.session_state['_photo_edit'] = None
                st.session_state['upload_key'] = st.session_state.get('upload_key', 0) + 1
                st.session_state.edit_id = None
                st.session_state.page_key = "🔍 ดูข้อมูลรายวัน"
                st.session_state['_pending_nav'] = "🔍 ดูข้อมูลรายวัน"
                st.rerun()

    else:
        # ── Unit-rate mode: items with qty × rate ──
        st.markdown("**📋 รายการงาน**")

        _active_projs2 = sorted([p for p in DB['projects'] if str(p.get('active','1')) != '0'],
                                key=lambda x: str(x.get('name', '')))
        if not _active_projs2:
            st.warning("ยังไม่มีประเภทงาน Online — ขอให้ Admin เพิ่มหรือเปิดใช้งานก่อน")
        else:
            pnames = [p['name'] for p in _active_projs2]
            pids   = [p['id']   for p in _active_projs2]
            to_rm  = None

            for idx, item in enumerate(st.session_state.wi):
                if can_see_money:
                    c1,c2,c3,c4,c5 = st.columns([2.5,1,1,1.2,0.5])
                else:
                    c1,c2,c4,c5 = st.columns([3,1.5,1.5,0.5])

                with c1:
                    cur_pi = pids.index(item['pid']) if item.get('pid') in pids else 0
                    sel = st.selectbox(f"งาน#{idx+1}", pnames, index=cur_pi,
                                       key=f"psel_{idx}", label_visibility="collapsed")
                    sp = _active_projs2[pnames.index(sel)]
                    item['pid']  = sp['id']
                    item['unit'] = sp['unit']
                    item['rate'] = _f(sp['unitRate'])
                with c2:
                    st.text_input("หน่วย", value=item['unit'], disabled=True,
                                  key=f"unit_{idx}", label_visibility="collapsed")
                if can_see_money:
                    with c3:
                        st.text_input("Rate", value=N(item['rate']), disabled=True,
                                      key=f"rate_{idx}", label_visibility="collapsed")
                with c4:
                    item['qty'] = st.number_input("ปริมาณ", min_value=0.0,
                                                  value=float(item.get('qty',0)),
                                                  step=0.01, key=f"qty_{idx}",
                                                  label_visibility="collapsed")
                    item['amt'] = item['qty'] * item['rate']
                with c5:
                    if st.button("🗑️", key=f"del_{idx}"): to_rm = idx

            if to_rm is not None:
                st.session_state.wi.pop(to_rm); st.rerun()

            ab, _ = st.columns([1,5])
            with ab:
                if st.button("➕ เพิ่มรายการงาน"):
                    fp = DB['projects'][0]
                    st.session_state.wi.append({'id':uid(),'pid':fp['id'],
                        'unit':fp['unit'],'rate':_f(fp['unitRate']),'qty':0,'amt':0})
                    st.rerun()

            if st.session_state.wi and can_see_money:
                grand = sum(w['amt'] for w in st.session_state.wi)
                st.markdown(f"**รวมทั้งหมด: <span style='color:#e07b2b;font-size:1.1rem'>฿ {N(grand)}</span>**",
                            unsafe_allow_html=True)

        st.markdown("---")
        s1,s2,_ = st.columns([1.2,1,5])
        with s1: save_btn = st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True)
        with s2:
            if st.button("🗑️ ล้างข้อมูล", use_container_width=True):
                st.session_state.wi = []
                st.session_state.photos = []
                st.session_state['_photo_edit'] = None
                st.session_state['upload_key'] = st.session_state.get('upload_key', 0) + 1
                st.session_state.edit_id = None
                st.rerun()

        if save_btn:
            if not st.session_state.wi:
                st.error("กรุณาเพิ่มรายการงานอย่างน้อย 1 รายการ")
            elif any(w['qty'] <= 0 for w in st.session_state.wi):
                st.error("กรุณาระบุปริมาณงานให้ครบทุกรายการ")
            else:
                total = sum(w['amt'] for w in st.session_state.wi)
                _rid = st.session_state.edit_id or next_id('reports')
                if new_photos:
                    with st.spinner(f"กำลังอัปโหลดรูปภาพ {len(new_photos)} รูป..."):
                        for _uf in new_photos:
                            try:
                                _ph = upload_photo(_uf.getvalue(), _uf.name, r_date.isoformat())
                                st.session_state.photos.append(_ph)
                            except Exception as _e:
                                st.warning(f"อัปโหลดรูป '{_uf.name}' ไม่สำเร็จ: {_e}")
                rec = {
                    'id':       _rid,
                    'date':     r_date.isoformat(),
                    'teamId':   r_tid,
                    'workers':  int(r_workers),
                    'note':     r_note,
                    'items':    [dict(w) for w in st.session_state.wi],
                    'posItems': json.dumps([]),
                    'photos':   list(st.session_state.photos),
                    'total':    total,
                }
                with st.spinner("กำลังบันทึก..."):
                    if st.session_state.edit_id:
                        idx2 = next((i for i,r in enumerate(DB['reports']) if r['id']==rec['id']), None)
                        if idx2 is not None: DB['reports'][idx2] = rec
                        msg = "✅ แก้ไขสำเร็จ"
                    else:
                        DB['reports'].append(rec)
                        msg = "✅ บันทึกสำเร็จ"
                    save_db("reports")
                st.session_state['_save_msg'] = msg
                st.session_state.wi = []
                st.session_state.photos = []
                st.session_state['_photo_edit'] = None
                st.session_state['upload_key'] = st.session_state.get('upload_key', 0) + 1
                st.session_state.edit_id = None
                st.session_state.page_key = "🔍 ดูข้อมูลรายวัน"
                st.session_state['_pending_nav'] = "🔍 ดูข้อมูลรายวัน"
                st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE: VIEW REPORTS
# ═══════════════════════════════════════════════════════
elif PAGE == "view":
    if st.session_state.get('_save_msg'):
        st.toast(st.session_state['_save_msg'], icon="✅")
        st.session_state['_save_msg'] = None
    st.markdown("### 🔍 ดูข้อมูลรายวัน")

    fc1,fc2,fc3 = st.columns([1.5,1,1])
    with fc1: ftype = st.selectbox("การค้นหา", ["ทั้งหมด","ระบุวันที่","ช่วงวันที่"], index=1)
    with fc2:
        topts = ["ทุกทีม"] + [t['name'] for t in DB['teams']]
        f_team = st.selectbox("ทีม", topts)
    with fc3: sort_dir = st.selectbox("เรียง", ["วันที่ล่าสุด","วันที่เก่าสุด"])

    f_date = f_start = f_end = None
    if ftype == "ระบุวันที่": f_date  = st.date_input("วันที่", value=date.today())
    elif ftype == "ช่วงวันที่":
        dc1,dc2 = st.columns(2)
        with dc1: f_start = st.date_input("จากวันที่")
        with dc2: f_end   = st.date_input("ถึงวันที่")

    rpts = list(DB['reports'])
    if f_team != "ทุกทีม":
        tid2 = next((t['id'] for t in DB['teams'] if t['name']==f_team), None)
        if tid2: rpts = [r for r in rpts if r['teamId']==tid2]
    if ftype=="ระบุวันที่" and f_date:
        rpts = [r for r in rpts if r['date']==f_date.isoformat()]
    elif ftype=="ช่วงวันที่":
        if f_start: rpts = [r for r in rpts if r['date']>=f_start.isoformat()]
        if f_end:   rpts = [r for r in rpts if r['date']<=f_end.isoformat()]
    rpts.sort(key=lambda r: r['date'], reverse=(sort_dir=="วันที่ล่าสุด"))

    total_sum = sum(_f(r['total']) for r in rpts)
    info_txt  = f"พบ **{len(rpts)}** รายการ"
    if can_see_money: info_txt += f" &nbsp;|&nbsp; รวม **฿ {N(total_sum)}**"
    st.markdown(info_txt, unsafe_allow_html=True)
    st.markdown("---")

    if not rpts:
        st.info("ไม่พบข้อมูล")
    else:
        for r in rpts:
            tname2 = get_team(r['teamId'])['name']
            hdr = f"📅 {thd(r['date'])}  —  {tname2}  —  👷 {r['workers']} คน"
            if can_see_money: hdr += f"  —  ฿ {N(r['total'])}"
            with st.expander(hdr):
                dc1,dc2 = st.columns([3,1])
                with dc1:
                    irows = []
                    for it in r['items']:
                        p2 = get_proj(it['pid'])
                        row2 = {"งาน": p2['name'], "หน่วย": it['unit'], "ปริมาณ": it['qty']}
                        if can_see_money:
                            row2["Rate(฿)"] = N(it['rate'])
                            row2["เงิน(฿)"] = N(it['amt'])
                        irows.append(row2)
                    st.dataframe(pd.DataFrame(irows), hide_index=True, use_container_width=True)
                    if r.get('note'): st.caption(f"📝 {r['note']}")
                    # ── แสดงรูปภาพ ──────────────────────────
                    _ph_list = r.get('photos') or []
                    if _ph_list:
                        st.markdown("**📷 รูปภาพ**")
                        _ph_cols2 = st.columns(min(len(_ph_list), 3))
                        for _i2, _ph2 in enumerate(_ph_list):
                            with _ph_cols2[_i2 % 3]:
                                if isinstance(_ph2, dict):
                                    _img_url = _ph2.get('url') or _ph2.get('thumb', '')
                                    _cap = _ph2.get('name', f"รูป {_i2+1}")
                                elif isinstance(_ph2, str) and _ph2.startswith('http'):
                                    _img_url, _cap = _ph2, f"รูป {_i2+1}"
                                else:
                                    continue
                                if _img_url:
                                    st.image(_img_url, use_container_width=True)
                                    st.caption(_cap)
                with dc2:
                    st.metric("คนงาน", r['workers'])
                    if can_see_money: st.metric("รวม (฿)", N(r['total']))
                    if can_edit:
                        eb1,eb2 = st.columns(2)
                        with eb1:
                            if st.button("✏️ แก้ไข", key=f"ed_{r['id']}"):
                                st.session_state.edit_id = r['id']
                                st.session_state.wi = []
                                st.session_state.pos_items = []
                                st.session_state.photos = []
                                st.session_state['_photo_edit'] = None
                                st.session_state.page_key = "➕ บันทึกงานประจำวัน"
                                st.session_state['_pending_nav'] = "➕ บันทึกงานประจำวัน"
                                st.rerun()
                        with eb2:
                            if st.button("🗑️ ลบ", key=f"dl_{r['id']}"):
                                DB['reports'] = [x for x in DB['reports'] if x['id']!=r['id']]
                                with st.spinner("กำลังบันทึก..."): save_db("reports")
                                st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE: PERIOD SUMMARY (Admin only)
# ═══════════════════════════════════════════════════════
elif PAGE == "summary" and can_summary:
    st.markdown("### 📈 สรุปรายงวด")
    sc1,sc2,sc3 = st.columns([1,1,1])
    with sc1: sel_year  = st.number_input("ปี (ค.ศ.)", min_value=2020, max_value=2035, value=date.today().year)
    with sc2: sel_month = st.selectbox("เดือน", list(range(1,13)),
                                        index=date.today().month-1,
                                        format_func=lambda m: TH_MO[m])
    yr2, mo2 = int(sel_year), int(sel_month)
    with sc3:
        st.markdown("<div style='padding-top:1.7rem'></div>", unsafe_allow_html=True)
        try:
            _excel_bytes = _build_period_excel(yr2, mo2)
            st.download_button(
                label="📥 Export Excel",
                data=_excel_bytes,
                file_name=f"KHT-Report-{yr2}-{str(mo2).zfill(2)}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as _ex:
            st.caption(f"Export ไม่ได้: {_ex}")

    def render_period(period):
        s,e   = pdates(yr2, mo2, period)
        eday  = 15 if period==1 else calendar.monthrange(yr2,mo2)[1]
        sday  = 1  if period==1 else 16
        ptot  = 0.0; paid = 0.0; rows_d = []
        for t in DB['teams']:
            tot  = period_total(t['id'], yr2, mo2, period)
            rpts = [r for r in DB['reports'] if r['teamId']==t['id'] and s<=r['date']<=e]
            pay  = get_payment(t['id'], yr2, mo2, period)
            ip   = bool(pay and pay.get('paid'))
            ptot += tot
            if ip: paid += tot
            rows_d.append((t, tot, rpts, pay, ip))

        st.markdown(
            f"<div class='period-hdr'>งวดที่ {period}: {sday}–{eday} {TH_MO[mo2]} {yr2+543} "
            f"&nbsp;|&nbsp; รวม ฿ {N(ptot)} &nbsp;|&nbsp; "
            f"<span style='color:#a8d8a8'>จ่ายแล้ว ฿ {N(paid)}</span> &nbsp;"
            f"<span style='color:#f8a9a9'>ค้าง ฿ {N(ptot-paid)}</span></div>",
            unsafe_allow_html=True)

        if not DB['teams']:
            st.info("ยังไม่มีทีม"); return

        # กรองออก: ทีม offline ที่ไม่มีข้อมูลในงวดนี้
        rows_d = [(t,tot,rpts,pay,ip) for t,tot,rpts,pay,ip in rows_d
                  if str(t.get('active','1')) != '0' or rpts]

        for t,tot,rpts,pay,ip in rows_d:
            days   = len(rpts)
            manday = sum(_i(r['workers']) for r in rpts)
            rc1,rc2,rc3 = st.columns([3,1.5,1.5])
            with rc1:
                st.markdown(f"**{t['name']}**")
                st.caption(f"{days} วันทำงาน | {manday} คน-วัน")
                if ip: st.caption(f"✅ จ่ายวันที่ {thd(pay.get('paidDate'))} {pay.get('note','')}")
            with rc2:
                st.metric("", f"฿ {N(tot)}")
            with rc3:
                sk = f"mark_{t['id']}_{period}"
                if ip:
                    st.markdown("<div class='b-paid'>✓ จ่ายแล้ว</div>", unsafe_allow_html=True)
                    if tot>0 and st.button("ยกเลิก", key=f"un_{t['id']}_{period}", use_container_width=True):
                        for px in DB['payments']:
                            if px['tid']==t['id'] and _i(px['y'])==yr2 and _i(px['mo'])==mo2 and _i(px['p'])==period:
                                px['paid']=False; px['paidDate']=''
                        with st.spinner("กำลังบันทึก..."): save_db("payments")
                        st.rerun()
                else:
                    if tot>0:
                        st.markdown("<div class='b-unpaid'>ยังไม่ได้จ่าย</div>", unsafe_allow_html=True)
                        if st.button("💰 จ่ายแล้ว", key=f"pk_{t['id']}_{period}", use_container_width=True):
                            st.session_state[sk] = True; st.rerun()
                    else:
                        st.caption("ไม่มีงาน")

            if st.session_state.get(f"mark_{t['id']}_{period}"):
                with st.form(key=f"pf_{t['id']}_{period}"):
                    pd_inp = st.date_input("วันที่จ่าย", value=date.today())
                    pn_inp = st.text_input("หมายเหตุ")
                    if st.form_submit_button("✅ ยืนยัน"):
                        prec = {'id':next_id('payments'),'tid':t['id'],'y':yr2,'mo':mo2,'p':period,
                                'paid':True,'paidDate':pd_inp.isoformat(),'note':pn_inp}
                        idx3 = next((i for i,px in enumerate(DB['payments'])
                                     if px['tid']==t['id'] and _i(px['y'])==yr2 and
                                        _i(px['mo'])==mo2 and _i(px['p'])==period), None)
                        if idx3 is not None: DB['payments'][idx3] = prec
                        else: DB['payments'].append(prec)
                        with st.spinner("กำลังบันทึก..."): save_db("payments")
                        st.session_state[f"mark_{t['id']}_{period}"] = False
                        st.rerun()
            st.markdown("<hr style='margin:6px 0;border-color:#f0f2f5'>", unsafe_allow_html=True)

    render_period(1)
    st.markdown("---")
    render_period(2)

    st.markdown("---")
    st.markdown(f"#### 📊 สรุปรวม {TH_MO[mo2]} {yr2+543}")
    m_str = str(mo2).zfill(2)
    cum_rows = []
    for t in DB['teams']:
        trpts = [r for r in DB['reports'] if r['teamId']==t['id']
                 and r['date'].startswith(f"{yr2}-{m_str}")]
        # ข้ามทีม offline ที่ไม่มีข้อมูลในเดือนนี้
        if str(t.get('active','1')) == '0' and not trpts:
            continue
        tot    = sum(_f(r['total']) for r in trpts)
        manday = sum(_i(r['workers']) for r in trpts)
        pd_tot = 0.0
        for pp in [1,2]:
            pay = get_payment(t['id'], yr2, mo2, pp)
            if pay and pay.get('paid'):
                s2,e2 = pdates(yr2, mo2, pp)
                pd_tot += sum(_f(r['total']) for r in DB['reports']
                              if r['teamId']==t['id'] and s2<=r['date']<=e2)
        cum_rows.append({"ทีม":t['name'],"คน-วัน":manday,
                         "ยอดรวม(฿)":N(tot),"จ่ายแล้ว(฿)":N(pd_tot),"ค้าง(฿)":N(tot-pd_tot)})
    if cum_rows:
        gt  = sum(_f(r["ยอดรวม(฿)"].replace(',',''))  for r in cum_rows)
        gp  = sum(_f(r["จ่ายแล้ว(฿)"].replace(',','')) for r in cum_rows)
        gmd = sum(r["คน-วัน"] for r in cum_rows)
        cum_rows.append({"ทีม":"รวมทั้งหมด","คน-วัน":gmd,
                         "ยอดรวม(฿)":N(gt),"จ่ายแล้ว(฿)":N(gp),"ค้าง(฿)":N(gt-gp)})
        st.dataframe(pd.DataFrame(cum_rows), hide_index=True, use_container_width=True)
    else:
        st.info("ไม่มีข้อมูลเดือนนี้")

# ═══════════════════════════════════════════════════════
# PAGE: SETTINGS (Admin only)
# ═══════════════════════════════════════════════════════
elif PAGE == "settings" and can_settings:
    st.markdown("### ⚙️ ตั้งค่าระบบ")
    tab_t, tab_ct, tab_p, tab_pos = st.tabs(["👥 ทีมทำงาน", "📋 ประเภทการจ้าง", "🔧 ประเภทงาน / Unit Rate", "🪪 ตำแหน่งงาน"])

    # ── helpers for contract type dropdown ──
    ct_list   = DB.get('contractTypes', [])
    ct_names  = [c['name'] for c in ct_list]
    ct_ids    = [c['id']   for c in ct_list]
    ct_opts   = ["— ไม่ระบุ —"] + ct_names   # index 0 = none

    def ct_idx(ctid):
        """Return dropdown index for a given contractTypeId (0 = none)."""
        try: return ct_ids.index(ctid) + 1
        except: return 0

    with tab_t:
        with st.expander("➕ เพิ่มทีมใหม่", expanded=(not DB['teams'])):
            with st.form("add_team"):
                t1,t2 = st.columns(2)
                with t1: tn = st.text_input("ชื่อทีม *")
                with t2: tnote = st.text_input("หมายเหตุ")
                t3,t4 = st.columns([2,1])
                with t3:
                    if ct_opts:
                        t_ct_sel = st.selectbox("ประเภทการจ้าง", ct_opts)
                    else:
                        st.info("ยังไม่มีประเภทการจ้าง — เพิ่มได้ที่ Tab 'ประเภทการจ้าง'")
                        t_ct_sel = "— ไม่ระบุ —"
                with t4:
                    t_active = st.selectbox("สถานะ", ["🟢 Online", "⭕ Offline"])
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not tn.strip(): st.error("กรุณาระบุชื่อทีม")
                    else:
                        new_ctid = ct_ids[ct_names.index(t_ct_sel)] if t_ct_sel != "— ไม่ระบุ —" else ''
                        DB['teams'].append({'id':next_id('teams'),'name':tn.strip(),
                                            'contractTypeId':new_ctid,'note':tnote.strip(),
                                            'active': '0' if 'Offline' in t_active else '1'})
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.success("✅ บันทึกทีมสำเร็จ"); st.rerun()
        st.markdown("---")
        if not DB['teams']: st.info("ยังไม่มีทีม")
        for t in DB['teams']:
            ct_name_disp = get_contract_type(t.get('contractTypeId','')).get('name','-') if t.get('contractTypeId') else '-'
            is_online = str(t.get('active','1')) != '0'
            status_icon = "🟢" if is_online else "⭕"
            with st.expander(f"{status_icon} **{t['name']}** — {ct_name_disp} — {t.get('note','-')}"):
                e1,e2 = st.columns(2)
                with e1: nn = st.text_input("ชื่อทีม", value=t['name'], key=f"tn_{t['id']}")
                with e2: nnt = st.text_input("หมายเหตุ", value=t.get('note',''), key=f"tnote_{t['id']}")
                e3,e4 = st.columns([2,1])
                with e3:
                    nct_sel = st.selectbox("ประเภทการจ้าง", ct_opts,
                                           index=ct_idx(t.get('contractTypeId','')),
                                           key=f"tct_{t['id']}")
                with e4:
                    active_opts = ["🟢 Online", "⭕ Offline"]
                    act_sel = st.selectbox("สถานะ", active_opts,
                                           index=0 if is_online else 1,
                                           key=f"tact_{t['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("💾 บันทึก", key=f"ts_{t['id']}", use_container_width=True):
                        t['name'] = nn; t['note'] = nnt
                        t['contractTypeId'] = ct_ids[ct_names.index(nct_sel)] if nct_sel != "— ไม่ระบุ —" else ''
                        t['active'] = '0' if 'Offline' in act_sel else '1'
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.success("บันทึกแล้ว"); st.rerun()
                with b2:
                    if st.button("🗑️ ลบ", key=f"td_{t['id']}", use_container_width=True):
                        DB['teams'] = [x for x in DB['teams'] if x['id']!=t['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.rerun()

    # ════════════════════════════════════════
    # TAB: ประเภทการจ้าง
    # ════════════════════════════════════════
    with tab_ct:
        with st.expander("➕ เพิ่มประเภทการจ้างใหม่", expanded=(not ct_list)):
            with st.form("add_ct"):
                ct1, ct2 = st.columns(2)
                with ct1: ctn = st.text_input("ชื่อประเภทการจ้าง * (เช่น บริษัท, ผรม)")
                with ct2:
                    cm_opts  = list(CALC_MODES.values())
                    cm_keys  = list(CALC_MODES.keys())
                    ctm_sel  = st.selectbox("วิธีคำนวณ *", cm_opts)
                ct_mr = st.number_input("Man Rate (฿/คน)", min_value=0.0, step=1.0, value=0.0,
                                        help="ใช้เมื่อวิธีคำนวณ = คิดตามจำนวนคน")
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not ctn.strip(): st.error("กรุณาระบุชื่อประเภทการจ้าง")
                    else:
                        new_cm = cm_keys[cm_opts.index(ctm_sel)]
                        DB.setdefault('contractTypes', []).append(
                            {'id':next_id('contractTypes'),'name':ctn.strip(),'calcMode':new_cm,'manRate':ct_mr})
                        with st.spinner("กำลังบันทึก..."): save_db("contractTypes")
                        st.success("✅ บันทึกสำเร็จ"); st.rerun()
        st.markdown("---")
        if not ct_list:
            st.info("ยังไม่มีประเภทการจ้าง — กด ➕ เพิ่มประเภทการจ้างใหม่")
        for ct in ct_list:
            cm_label = CALC_MODES.get(ct.get('calcMode','unit_rate'), '-')
            mr_disp  = f" | Man Rate ฿{N(ct.get('manRate',0))}/คน" if ct.get('calcMode')=='by_workers' else ''
            with st.expander(f"**{ct['name']}** — {cm_label}{mr_disp}"):
                ec1, ec2 = st.columns(2)
                with ec1: nctn = st.text_input("ชื่อ", value=ct['name'], key=f"ctn_{ct['id']}")
                with ec2:
                    cur_cm_idx = cm_keys.index(ct.get('calcMode','unit_rate')) if ct.get('calcMode') in cm_keys else 0
                    nctm_sel   = st.selectbox("วิธีคำนวณ", cm_opts, index=cur_cm_idx, key=f"ctm_{ct['id']}")
                nct_mr = st.number_input("Man Rate (฿/คน)", value=_f(ct.get('manRate',0)),
                                         min_value=0.0, step=1.0, key=f"ctmr_{ct['id']}",
                                         help="ใช้เมื่อวิธีคำนวณ = คิดตามจำนวนคน")
                eb1, eb2 = st.columns(2)
                with eb1:
                    if st.button("💾 บันทึก", key=f"cts_{ct['id']}", use_container_width=True):
                        ct['name']     = nctn
                        ct['calcMode'] = cm_keys[cm_opts.index(nctm_sel)]
                        ct['manRate']  = nct_mr
                        with st.spinner("กำลังบันทึก..."): save_db("contractTypes")
                        st.success("บันทึกแล้ว"); st.rerun()
                with eb2:
                    if st.button("🗑️ ลบ", key=f"ctd_{ct['id']}", use_container_width=True):
                        DB['contractTypes'] = [x for x in DB['contractTypes'] if x['id']!=ct['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("contractTypes")
                        st.rerun()

    with tab_p:
        with st.expander("➕ เพิ่มประเภทงานใหม่", expanded=(not DB['projects'])):
            with st.form("add_proj"):
                p1,p2 = st.columns(2)
                with p1: pn = st.text_input("ชื่องาน *")
                with p2: pd2 = st.text_input("คำอธิบาย")
                p3,p4,p5,p6 = st.columns([2,1.5,1.5,1])
                with p3: pu = st.text_input("หน่วย * (เช่น ม., kg)")
                with p4: pr = st.number_input("Unit Rate (฿/หน่วย)", min_value=0.0, step=0.01)
                with p5: pt = st.number_input("เป้าหมายรวม (qty)", min_value=0.0, step=1.0,
                                              help="ปริมาณงานทั้งหมดของ Scope งานนี้ (ใช้ติดตาม % แล้วเสร็จ)")
                with p6: p_active = st.selectbox("สถานะ", ["🟢 Online", "⭕ Offline"])
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not pn.strip() or not pu.strip():
                        st.error("กรุณากรอกข้อมูลให้ครบ")
                    else:
                        DB['projects'].append({'id':next_id('projects'),'name':pn.strip(),'unit':pu.strip(),
                                               'unitRate':pr,'description':pd2.strip(),'target':pt,
                                               'active': '0' if 'Offline' in p_active else '1'})
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.success("✅ บันทึกสำเร็จ"); st.rerun()
        st.markdown("---")
        if not DB['projects']: st.info("ยังไม่มีประเภทงาน")
        for p in sorted(DB['projects'], key=lambda x: str(x.get('name', ''))):
            p_online = str(p.get('active', '1')) != '0'
            p_icon   = "🟢" if p_online else "⭕"
            with st.expander(f"{p_icon} **{p['name']}** — {p['unit']} — ฿{N(p['unitRate'])}/หน่วย"):
                e1,e2,e3,e4,e5 = st.columns([2,1,1,1,1])
                with e1:
                    npn = st.text_input("ชื่องาน", value=p['name'], key=f"pn_{p['id']}")
                    npd = st.text_input("คำอธิบาย", value=p.get('description',''), key=f"pd_{p['id']}")
                with e2: npu = st.text_input("หน่วย", value=p['unit'], key=f"pu_{p['id']}")
                with e3: npr = st.number_input("Unit Rate", value=_f(p['unitRate']),
                                               min_value=0.0, step=0.01, key=f"pr_{p['id']}")
                with e4: npt = st.number_input("เป้าหมาย (qty)", value=_f(p.get('target',0)),
                                               min_value=0.0, step=1.0, key=f"ptgt_{p['id']}",
                                               help="ปริมาณงานทั้งหมดของ Scope")
                with e5:
                    p_act_opts = ["🟢 Online", "⭕ Offline"]
                    np_act = st.selectbox("สถานะ", p_act_opts,
                                         index=0 if p_online else 1,
                                         key=f"pact_{p['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("💾 บันทึก", key=f"ps_{p['id']}", use_container_width=True):
                        p['name']=npn; p['unit']=npu; p['unitRate']=npr; p['description']=npd
                        p['target'] = npt
                        p['active'] = '0' if 'Offline' in np_act else '1'
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.success("บันทึกแล้ว"); st.rerun()
                with b2:
                    if st.button("🗑️ ลบ", key=f"pdel_{p['id']}", use_container_width=True):
                        DB['projects'] = [x for x in DB['projects'] if x['id']!=p['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.rerun()

    # ════════════════════════════════════════
    # TAB: ตำแหน่งงาน
    # ════════════════════════════════════════
    with tab_pos:
        pos_list = DB.get('positions', [])
        with st.expander("➕ เพิ่มตำแหน่งงานใหม่", expanded=(not pos_list)):
            with st.form("add_pos"):
                pp1, pp2 = st.columns(2)
                with pp1: pos_name = st.text_input("ชื่อตำแหน่ง * (เช่น ช่างเชื่อม, ช่างท่อ)")
                with pp2: pos_rate = st.number_input("Rate ค่าจ้างต่อวัน (฿/วัน)",
                                                     min_value=0.0, step=50.0, value=0.0)
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not pos_name.strip():
                        st.error("กรุณาระบุชื่อตำแหน่ง")
                    else:
                        DB.setdefault('positions', []).append(
                            {'id': next_id('positions'), 'name': pos_name.strip(), 'dailyRate': pos_rate})
                        with st.spinner("กำลังบันทึก..."): save_db("positions")
                        st.success("✅ บันทึกสำเร็จ"); st.rerun()
        st.markdown("---")
        if not pos_list:
            st.info("ยังไม่มีตำแหน่งงาน — กด ➕ เพิ่มตำแหน่งงานใหม่")
        for pos in pos_list:
            with st.expander(f"**{pos['name']}** — ฿{N(pos.get('dailyRate', 0))}/วัน"):
                pe1, pe2 = st.columns(2)
                with pe1: npos_name = st.text_input("ชื่อตำแหน่ง", value=pos['name'],
                                                     key=f"posn_{pos['id']}")
                with pe2: npos_rate = st.number_input("Rate (฿/วัน)",
                                                       value=_f(pos.get('dailyRate', 0)),
                                                       min_value=0.0, step=50.0,
                                                       key=f"posr_{pos['id']}")
                pb1, pb2 = st.columns(2)
                with pb1:
                    if st.button("💾 บันทึก", key=f"poss_{pos['id']}", use_container_width=True):
                        pos['name']      = npos_name
                        pos['dailyRate'] = npos_rate
                        with st.spinner("กำลังบันทึก..."): save_db("positions")
                        st.success("บันทึกแล้ว"); st.rerun()
                with pb2:
                    if st.button("🗑️ ลบ", key=f"posd_{pos['id']}", use_container_width=True):
                        DB['positions'] = [x for x in DB['positions'] if x['id'] != pos['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("positions")
                        st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE: PRODUCTIVITY
# ═══════════════════════════════════════════════════════
elif PAGE == "productivity":
    st.markdown("### 📉 Productivity — ติดตามผลงาน")

    now = date.today()

    # ─── helpers ───────────────────────────────────────────────────────────
    def _proj_name(pid):
        return get_proj(pid).get('name', '?')

    def _team_name(tid):
        return get_team(tid).get('name', '?')

    def _ct_name(ctid):
        return next((c['name'] for c in DB['contractTypes'] if c['id'] == ctid), '?')

    def _team_ct(tid):
        t = get_team(tid)
        return _ct_name(t.get('contractTypeId', ''))

    def _apply_filters(rpts, f_team, f_ct, f_proj):
        out = rpts
        if f_team != "ทุกทีม":
            tid = next((t['id'] for t in DB['teams'] if t['name'] == f_team), None)
            out = [r for r in out if r['teamId'] == tid]
        if f_ct != "ทุกประเภทการจ้าง":
            out = [r for r in out if _team_ct(r['teamId']) == f_ct]
        if f_proj != "ทุกประเภทงาน":
            out = [r for r in out if any(
                _proj_name(it['pid']) == f_proj for it in r.get('items', [])
            )]
        return out

    def _render_detail_table(rpts_f, f_proj):
        """ตารางรายละเอียดแต่ละ record"""
        rows = []
        for r in sorted(rpts_f, key=lambda x: (x['date'], _team_name(x['teamId']))):
            tname   = _team_name(r['teamId'])
            ctname  = _team_ct(r['teamId'])
            workers = _i(r.get('workers', 0))
            total   = _f(r.get('total', 0))
            items   = r.get('items', [])
            items_f = [it for it in items if _f(it.get('qty', 0)) > 0
                       and (f_proj == "ทุกประเภทงาน" or _proj_name(it['pid']) == f_proj)]
            if items_f:
                for it in items_f:
                    qty = _f(it.get('qty', 0))
                    row_d = {
                        "วันที่":           thd(r['date']),
                        "ทีม":              tname,
                        "ประเภทการจ้าง":   ctname,
                        "คนงาน (คน)":      workers,
                        "ประเภทงาน":       _proj_name(it['pid']),
                        "ปริมาณ":          qty,
                        "หน่วย":           it.get('unit', ''),
                        "Prod/คน":         round(qty / workers, 3) if workers else 0,
                    }
                    if can_see_money:
                        row_d["ต้นทุน (บาท)"] = total if total else "—"
                    rows.append(row_d)
            else:
                row_d = {
                    "วันที่":           thd(r['date']),
                    "ทีม":              tname,
                    "ประเภทการจ้าง":   ctname,
                    "คนงาน (คน)":      workers,
                    "ประเภทงาน":       "—",
                    "ปริมาณ":          "—",
                    "หน่วย":           "",
                    "Prod/คน":         "—",
                }
                if can_see_money:
                    row_d["ต้นทุน (บาท)"] = total if total else "—"
                rows.append(row_d)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        return rows

    def _render_summary(rpts_f, label, f_proj="ทุกประเภทงาน"):
        """สรุปรายทีม + รายประเภทงาน + metrics"""
        if not rpts_f:
            st.info("ไม่มีข้อมูลในช่วงที่เลือก")
            return

        total_workers = sum(_i(r.get('workers', 0)) for r in rpts_f)
        total_cost    = sum(_f(r.get('total', 0))   for r in rpts_f)
        total_days    = len(set(r['date'] for r in rpts_f))
        total_records = len(rpts_f)

        if can_see_money:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc4.metric("💰 ต้นทุนรวม", f"{total_cost:,.0f} ฿")
        else:
            mc1, mc2, mc3 = st.columns(3)
        mc1.metric("📋 รายงาน", f"{total_records} รายการ")
        mc2.metric("📅 วันทำงาน", f"{total_days} วัน")
        mc3.metric("👷 Man-days รวม", f"{total_workers:,}")

        # ── สรุปรายทีม ──
        st.markdown("---")
        st.markdown("#### 👥 สรุปรายทีม")
        team_summary: dict = defaultdict(lambda: {"days": set(), "workers": 0, "cost": 0.0,
                                                   "items": defaultdict(lambda: {"qty": 0.0, "unit": ""})})
        for r in rpts_f:
            tid   = r['teamId']
            tname = _team_name(tid)
            team_summary[tname]["days"].add(r['date'])
            team_summary[tname]["workers"] += _i(r.get('workers', 0))
            team_summary[tname]["cost"]    += _f(r.get('total', 0))
            for it in r.get('items', []):
                qty = _f(it.get('qty', 0))
                if qty > 0:
                    pn = _proj_name(it['pid'])
                    team_summary[tname]["items"][pn]["qty"]  += qty
                    team_summary[tname]["items"][pn]["unit"]  = it.get('unit', '')

        t_rows = []
        for tname, v in team_summary.items():
            items_str = ", ".join(
                f"{k}: {round(v2['qty'],1)} {v2['unit']}"
                for k, v2 in v["items"].items()
            ) or "—"
            t_row = {
                "ทีม":                 tname,
                "วันทำงาน":           len(v["days"]),
                "Man-days รวม":        v["workers"],
            }
            if can_see_money:
                t_row["ต้นทุน (บาท)"] = round(v["cost"], 0)
            t_row["รายการงาน"] = items_str
            t_rows.append(t_row)
        if t_rows:
            st.dataframe(pd.DataFrame(t_rows), hide_index=True, use_container_width=True)

        # ── สรุปตามประเภทงาน ──
        st.markdown("---")
        st.markdown("#### 🔧 สรุปตามประเภทงาน")
        psum: dict = defaultdict(lambda: {"qty": 0.0, "unit": "", "workers": 0, "teams": set()})
        for r in rpts_f:
            w = _i(r.get('workers', 0))
            for it in r.get('items', []):
                qty = _f(it.get('qty', 0))
                if qty <= 0:
                    continue
                pn = _proj_name(it['pid'])
                psum[pn]["qty"]     += qty
                psum[pn]["unit"]     = it.get('unit', '')
                psum[pn]["workers"] += w
                psum[pn]["teams"].add(_team_name(r['teamId']))
        if psum:
            p_rows = [{
                "ประเภทงาน":              pn,
                "หน่วย":                  v["unit"],
                "ปริมาณรวม":              round(v["qty"], 2),
                "Man-days รวม":           v["workers"],
                "Productivity (หน่วย/คน)": round(v["qty"] / v["workers"], 3) if v["workers"] else 0,
                "ทีมที่ทำ":               ", ".join(sorted(v["teams"])),
            } for pn, v in psum.items()]
            st.dataframe(pd.DataFrame(p_rows), hide_index=True, use_container_width=True)
        else:
            st.info("ยังไม่มีรายการงานที่บันทึก")

        # ── Target vs Actual (ยอดสะสมทั้งโครงการ) ────────────────────────
        projs_with_target = [
            p for p in DB['projects']
            if _f(p.get('target', 0)) > 0
            and (f_proj == "ทุกประเภทงาน" or p['name'] == f_proj)
        ]
        if projs_with_target:
            st.markdown("---")
            st.markdown("#### 🎯 Target vs Actual (ยอดสะสมทั้งโครงการ)")
            end_date = max(r['date'] for r in rpts_f) if rpts_f else today_str()
            ta_rows = []
            for p in projs_with_target:
                target  = _f(p.get('target', 0))
                # สะสมทั้งหมดถึงวันสุดท้ายใน range
                actual_total = sum(
                    _f(it.get('qty', 0))
                    for r in DB['reports'] if r['date'] <= end_date
                    for it in r.get('items', [])
                    if it.get('pid') == p['id']
                )
                # เฉพาะช่วงที่เลือก
                actual_range = sum(
                    _f(it.get('qty', 0))
                    for r in rpts_f
                    for it in r.get('items', [])
                    if it.get('pid') == p['id']
                )
                pct       = min(actual_total / target * 100, 100) if target else 0
                remaining = max(0.0, target - actual_total)
                ta_rows.append({
                    "ประเภทงาน":        p['name'],
                    "หน่วย":            p['unit'],
                    "เป้าหมายรวม":      target,
                    "ทำแล้ว (สะสม)":   round(actual_total, 2),
                    "ช่วงนี้":          round(actual_range, 2),
                    "% แล้วเสร็จ":      f"{pct:.1f}%",
                    "คงเหลือ":          round(remaining, 2),
                })
            if ta_rows:
                st.dataframe(pd.DataFrame(ta_rows), hide_index=True, use_container_width=True)

        # ── Cumulative Cost Chart (Admin only) ────────────────────────────
        if can_see_money:
            st.markdown("---")
            st.markdown("#### 📈 ต้นทุนสะสมรายวัน")
            daily_cost: dict = defaultdict(float)
            for r in rpts_f:
                daily_cost[r['date']] += _f(r.get('total', 0))
            if daily_cost:
                dates_sorted = sorted(daily_cost.keys())
                running = 0.0
                cum_data = []
                for d in dates_sorted:
                    running += daily_cost[d]
                    cum_data.append({
                        "วันที่":         d,
                        "ต้นทุนสะสม (฿)": running,
                        "รายวัน (฿)":    daily_cost[d],
                    })
                chart_df = pd.DataFrame(cum_data).set_index("วันที่")
                st.area_chart(chart_df[["ต้นทุนสะสม (฿)"]])
                # แสดงตารางขนาดย่อ
                with st.expander("📋 ตารางต้นทุนรายวัน", expanded=False):
                    disp_df = pd.DataFrame(cum_data)
                    disp_df["วันที่"] = disp_df["วันที่"].apply(thd)
                    st.dataframe(disp_df, hide_index=True, use_container_width=True)

    # ─── filter options ────────────────────────────────────────────────────
    all_teams   = ["ทุกทีม"]  + [t['name'] for t in DB['teams']]
    all_cts     = ["ทุกประเภทการจ้าง"] + [c['name'] for c in DB['contractTypes']]
    all_projs   = ["ทุกประเภทงาน"]     + [p['name'] for p in DB['projects']]

    tab_day, tab_range, tab_period, tab_trend = st.tabs(["📅 เลือกวัน", "📆 ช่วงวันที่", "📊 รายงวด", "📈 Trend"])

    # ════════════════════════════════════════════════
    # TAB 1: เลือกวันเดียว
    # ════════════════════════════════════════════════
    with tab_day:
        fc1, fc2, fc3, fc4 = st.columns([1.2, 1.5, 1.5, 1.5])
        with fc1:
            day_sel = st.date_input("📅 วันที่", value=now, key="pday_date",
                                    format="DD/MM/YYYY")
        with fc2:
            ft_day  = st.selectbox("👥 ทีม", all_teams, key="pday_team")
        with fc3:
            fct_day = st.selectbox("📋 ประเภทการจ้าง", all_cts, key="pday_ct")
        with fc4:
            fp_day  = st.selectbox("🔧 ประเภทงาน", all_projs, key="pday_proj")

        day_str  = day_sel.isoformat()
        rpts_day = [r for r in DB['reports'] if r['date'] == day_str]
        rpts_day = _apply_filters(rpts_day, ft_day, fct_day, fp_day)

        st.markdown(f"**{thd(day_str)}** — พบ {len(rpts_day)} รายงาน")
        st.markdown("---")

        if rpts_day:
            _render_detail_table(rpts_day, fp_day)
            st.markdown("---")
            _render_summary(rpts_day, thd(day_str), fp_day)
        else:
            st.info("ไม่มีข้อมูลในวันที่เลือก")

    # ════════════════════════════════════════════════
    # TAB 2: ช่วงวันที่ (from–to)
    # ════════════════════════════════════════════════
    with tab_range:
        rc1, rc2 = st.columns(2)
        with rc1:
            from_date = st.date_input("📅 จากวันที่", value=now.replace(day=1),
                                      key="pr_from", format="DD/MM/YYYY")
        with rc2:
            to_date   = st.date_input("📅 ถึงวันที่", value=now,
                                      key="pr_to",   format="DD/MM/YYYY")

        rf1, rf2, rf3 = st.columns(3)
        with rf1:
            ft_rng  = st.selectbox("👥 ทีม", all_teams, key="pr_team")
        with rf2:
            fct_rng = st.selectbox("📋 ประเภทการจ้าง", all_cts, key="pr_ct")
        with rf3:
            fp_rng  = st.selectbox("🔧 ประเภทงาน", all_projs, key="pr_proj")

        if from_date > to_date:
            st.warning("⚠️ วันเริ่มต้นต้องไม่มากกว่าวันสิ้นสุด")
        else:
            fs  = from_date.isoformat()
            fe  = to_date.isoformat()
            rpts_rng = [r for r in DB['reports'] if fs <= r['date'] <= fe]
            rpts_rng = _apply_filters(rpts_rng, ft_rng, fct_rng, fp_rng)

            st.markdown(f"**{thd(fs)} – {thd(fe)}** — พบ {len(rpts_rng)} รายงาน")
            st.markdown("---")

            if rpts_rng:
                with st.expander("📋 รายละเอียดรายวัน", expanded=False):
                    _render_detail_table(rpts_rng, fp_rng)
                st.markdown("---")
                _render_summary(rpts_rng, f"{thd(fs)} – {thd(fe)}", fp_rng)
            else:
                st.info("ไม่มีข้อมูลในช่วงที่เลือก")

    # ════════════════════════════════════════════════
    # TAB 3: รายงวด (preset ครึ่งเดือน)
    # ════════════════════════════════════════════════
    with tab_period:
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            sel_yr_p = st.selectbox("ปี (พ.ศ.)", [now.year+543-i for i in range(4)],
                                    key="pp_yr", format_func=lambda x: str(x))
        with pc2:
            sel_mo_p = st.selectbox("เดือน", list(range(1, 13)), index=now.month - 1,
                                    format_func=lambda x: TH_MO[x], key="pp_mo")
        with pc3:
            sel_pp   = st.selectbox("งวด", [1, 2],
                                    format_func=lambda x: f"งวดที่ {x} ({'1–15' if x==1 else '16–สิ้นเดือน'})",
                                    key="pp_p")

        pf1, pf2, pf3 = st.columns(3)
        with pf1:
            ft_per  = st.selectbox("👥 ทีม", all_teams, key="pp_team")
        with pf2:
            fct_per = st.selectbox("📋 ประเภทการจ้าง", all_cts, key="pp_ct")
        with pf3:
            fp_per  = st.selectbox("🔧 ประเภทงาน", all_projs, key="pp_proj")

        yr_ad_p = sel_yr_p - 543
        ps_date, pe_date = pdates(yr_ad_p, sel_mo_p, sel_pp)
        rpts_per = [r for r in DB['reports'] if ps_date <= r['date'] <= pe_date]
        rpts_per = _apply_filters(rpts_per, ft_per, fct_per, fp_per)

        period_lbl = f"งวดที่ {sel_pp} ({'1–15' if sel_pp==1 else '16–สิ้นเดือน'}) {TH_MO[sel_mo_p]} {sel_yr_p}"
        st.markdown(f"**{period_lbl}** ({thd(ps_date)} – {thd(pe_date)}) — พบ {len(rpts_per)} รายงาน")
        st.markdown("---")

        if rpts_per:
            with st.expander("📋 รายละเอียดรายวัน", expanded=False):
                _render_detail_table(rpts_per, fp_per)
            st.markdown("---")
            _render_summary(rpts_per, period_lbl, fp_per)
        else:
            st.info("ไม่มีข้อมูลในงวดที่เลือก")

    # ════════════════════════════════════════════════
    # TAB 4: Trend — รายสัปดาห์
    # ════════════════════════════════════════════════
    with tab_trend:
        from datetime import timedelta

        st.markdown("#### 📈 แนวโน้มรายสัปดาห์ (8 สัปดาห์ย้อนหลัง)")

        # ── filter ──
        tf1, tf2 = st.columns([1.5, 1.5])
        with tf1:
            ft_trend = st.selectbox("👥 ทีม", all_teams, key="pt_team")
        with tf2:
            fct_trend = st.selectbox("📋 ประเภทการจ้าง", all_cts, key="pt_ct")

        # ── build 8-week buckets ──
        WEEKS = 8
        today_td = date.today()
        # วันจันทร์ของสัปดาห์นี้
        monday_this = today_td - timedelta(days=today_td.weekday())

        wk_labels, wk_costs, wk_mandays = [], [], []
        for i in range(WEEKS - 1, -1, -1):
            wk_start = monday_this - timedelta(weeks=i)
            wk_end   = wk_start + timedelta(days=6)
            wk_rpts  = [r for r in DB['reports']
                        if wk_start.isoformat() <= r['date'] <= wk_end.isoformat()]
            wk_rpts  = _apply_filters(wk_rpts, ft_trend, fct_trend, "ทุกประเภทงาน")
            wk_cost  = sum(_f(r.get('total', 0)) for r in wk_rpts)
            wk_md    = sum(_i(r.get('workers', 0)) for r in wk_rpts)
            label    = f"W{wk_start.strftime('%d/%m')}"
            wk_labels.append(label)
            wk_costs.append(round(wk_cost, 0))
            wk_mandays.append(wk_md)

        wk_cpmd = [round(wk_costs[i] / wk_mandays[i], 0) if wk_mandays[i] else 0
                   for i in range(WEEKS)]

        # ── Chart 1: Cost per week ──
        if can_see_money:
            st.markdown("**💸 ต้นทุนรวมรายสัปดาห์ (฿)**")
            cost_df = pd.DataFrame({"สัปดาห์": wk_labels, "ต้นทุน (฿)": wk_costs}).set_index("สัปดาห์")
            st.bar_chart(cost_df)

        # ── Chart 2: Man-days per week ──
        st.markdown("**👷 Man-days รายสัปดาห์**")
        md_df = pd.DataFrame({"สัปดาห์": wk_labels, "Man-days": wk_mandays}).set_index("สัปดาห์")
        st.bar_chart(md_df)

        # ── Chart 3: ฿/Man-day trend (admin) ──
        if can_see_money:
            st.markdown("**📊 ฿/Man-day รายสัปดาห์**")
            cpmd_df = pd.DataFrame({"สัปดาห์": wk_labels, "฿/Man-day": wk_cpmd}).set_index("สัปดาห์")
            st.line_chart(cpmd_df)

        # ── Summary table ──
        with st.expander("📋 ตารางสรุปรายสัปดาห์", expanded=False):
            rows_t = []
            for i in range(WEEKS):
                row_t = {"สัปดาห์": wk_labels[i], "Man-days": wk_mandays[i]}
                if can_see_money:
                    row_t["ต้นทุน (฿)"]  = wk_costs[i]
                    row_t["฿/Man-day"] = wk_cpmd[i]
                rows_t.append(row_t)
            st.dataframe(pd.DataFrame(rows_t), hide_index=True, use_container_width=True)
