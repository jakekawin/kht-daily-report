import streamlit as st
import json, calendar
from datetime import date, datetime
import uuid
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# âââ PAGE CONFIG âââââââââââââââââââââââââââââââââââââ
st.set_page_config(
    page_title="KHT Daily Report",
    page_icon="âï¸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# âââ CONSTANTS âââââââââââââââââââââââââââââââââââââââ
SHEET_ID   = "1PbxKOycC5aGIF2P98BKXoWhLmH7wCS8YEDjc-lEYn5A"
ROLE_ADMIN = "admin"
ROLE_SUPER = "supervisor"
ROLE_VIEW  = "viewer"
TH_MO   = ['','à¸¡à¸à¸£à¸²à¸à¸¡','à¸à¸¸à¸¡à¸ à¸²à¸à¸±à¸à¸à¹','à¸¡à¸µà¸à¸²à¸à¸¡','à¹à¸¡à¸©à¸²à¸¢à¸','à¸à¸¤à¸©à¸ à¸²à¸à¸¡','à¸¡à¸´à¸à¸¸à¸à¸²à¸¢à¸',
            'à¸à¸£à¸à¸à¸²à¸à¸¡','à¸ªà¸´à¸à¸«à¸²à¸à¸¡','à¸à¸±à¸à¸¢à¸²à¸¢à¸','à¸à¸¸à¸¥à¸²à¸à¸¡','à¸à¸¤à¸¨à¸à¸´à¸à¸²à¸¢à¸','à¸à¸±à¸à¸§à¸²à¸à¸¡']
TH_MO_S = ['','à¸¡.à¸.','à¸.à¸.','à¸¡à¸µ.à¸.','à¹à¸¡.à¸¢.','à¸.à¸.','à¸¡à¸´.à¸¢.',
            'à¸.à¸.','à¸ª.à¸.','à¸.à¸¢.','à¸.à¸.','à¸.à¸¢.','à¸.à¸.']
SHEET_HEADERS = {
    "teams":         ["id", "name", "contractTypeId", "note"],
    "contractTypes": ["id", "name", "calcMode"],
    "projects":      ["id", "name", "unit", "unitRate", "description"],
    "reports":       ["id", "date", "teamId", "workers", "note", "items", "total"],
    "payments":      ["id", "tid", "y", "mo", "p", "paid", "paidDate", "note"],
}
CALC_MODES = {"unit_rate": "à¸à¸´à¸à¸à¸²à¸¡ Unit Rate (à¸à¸£à¸´à¸¡à¸²à¸ Ã à¸£à¸²à¸à¸²)",
              "by_workers": "à¸à¸´à¸à¸à¸²à¸¡à¸à¸³à¸à¸§à¸à¸à¸ (à¸à¸ Ã à¸§à¸±à¸ Ã à¸£à¸²à¸à¸²)"}

# âââ CSS âââââââââââââââââââââââââââââââââââââââââââââ
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
</style>
""", unsafe_allow_html=True)

# âââ HELPERS âââââââââââââââââââââââââââââââââââââââââ
def _f(v):
    try: return float(v or 0)
    except: return 0.0

def _i(v):
    try: return int(v or 0)
    except: return 0

def uid(): return str(uuid.uuid4())[:8]
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

# âââ GOOGLE SHEETS ââââââââââââââââââââââââââââââââââââ
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

        for p in projects:
            p['unitRate'] = _f(p.get('unitRate', 0))
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
            rec['workers'] = _i(rec.get('workers', 0))
            rec['total']   = _f(rec.get('total', 0))
            for it in rec['items']:
                it['qty']  = _f(it.get('qty',  0))
                it['amt']  = _f(it.get('amt',  0))
                it['rate'] = _f(it.get('rate', 0))
            reports.append(rec)

        return {"teams": teams, "contractTypes": contractTypes,
                "projects": projects, "reports": reports, "payments": payments}
    except Exception as e:
        st.error(f"â à¹à¸«à¸¥à¸à¸à¹à¸­à¸¡à¸¹à¸¥à¹à¸¡à¹à¹à¸à¹: {e}")
        return {"teams": [], "projects": [], "reports": [], "payments": []}

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
                    if h == 'items' and isinstance(val, list):
                        val = json.dumps(val, ensure_ascii=False)
                    if isinstance(val, bool): val = str(val).upper()
                    if val is None: val = ''
                    row.append(val)
                rows.append(row)
            ws.update(rows)
    except Exception as e:
        st.error(f"â à¸à¸±à¸à¸à¸¶à¸à¹à¸¡à¹à¸ªà¸³à¹à¸£à¹à¸: {e}")

# âââ DB ACCESSORS âââââââââââââââââââââââââââââââââââââ
def get_team(tid):
    return next((x for x in st.session_state.db['teams'] if x['id'] == tid),
                {'name': '?', 'note': '', 'contractTypeId': ''})

def get_contract_type(ctid):
    return next((x for x in st.session_state.db.get('contractTypes', []) if x['id'] == ctid),
                {'name': '-', 'calcMode': 'unit_rate'})

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

# âââ AUTH âââââââââââââââââââââââââââââââââââââââââââââ
def check_login(role_key, pw):
    try: return pw == st.secrets["passwords"][role_key]
    except: return False

def login_page():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:40px 0 20px 0">
          <div style="font-size:3.5rem">âï¸</div>
          <h2 style="color:#1e3a5f;margin:8px 0 4px 0">KHT Daily Report</h2>
          <p style="color:#888;font-size:0.9rem">à¸£à¸°à¸à¸à¸à¸±à¸à¸à¸¶à¸à¸à¸¥à¸à¸²à¸à¸à¸¹à¹à¸£à¸±à¸à¹à¸«à¸¡à¸²</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            role_display = st.selectbox(
                "à¸£à¸°à¸à¸±à¸à¸à¸¹à¹à¹à¸à¹à¸à¸²à¸",
                ["ð à¸à¸¹à¹à¸à¸£à¸´à¸«à¸²à¸£ (Admin)", "ð§ à¸«à¸±à¸§à¸«à¸à¹à¸²à¸à¸²à¸", "ðï¸ à¸à¸¹à¸à¹à¸­à¸¡à¸¹à¸¥"]
            )
            pw = st.text_input("ð à¸£à¸«à¸±à¸ªà¸à¹à¸²à¸", type="password")
            sub = st.form_submit_button("à¹à¸à¹à¸²à¸ªà¸¹à¹à¸£à¸°à¸à¸", type="primary", use_container_width=True)

        if sub:
            rmap = {
                "ð à¸à¸¹à¹à¸à¸£à¸´à¸«à¸²à¸£ (Admin)": ROLE_ADMIN,
                "ð§ à¸«à¸±à¸§à¸«à¸à¹à¸²à¸à¸²à¸":       ROLE_SUPER,
                "ðï¸ à¸à¸¹à¸à¹à¸­à¸¡à¸¹à¸¥":         ROLE_VIEW,
            }
            rk = rmap[role_display]
            if check_login(rk, pw):
                st.session_state.logged_in = True
                st.session_state.role = rk
                with st.spinner("â³ à¸à¸³à¸¥à¸±à¸à¹à¸«à¸¥à¸à¸à¹à¸­à¸¡à¸¹à¸¥..."):
                    st.session_state.db = load_db()
                st.session_state.wi = []
                st.session_state.edit_id = None
                st.session_state.page_key = None
                st.rerun()
            else:
                st.error("â à¸£à¸«à¸±à¸ªà¸à¹à¸²à¸à¹à¸¡à¹à¸à¸¹à¸à¸à¹à¸­à¸")

# âââ SESSION STATE INIT âââââââââââââââââââââââââââââââ
for k, v in [('logged_in', False), ('role', None), ('wi', []),
              ('edit_id', None), ('page_key', None)]:
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.logged_in:
    login_page()
    st.stop()

if 'db' not in st.session_state:
    with st.spinner("â³ à¸à¸³à¸¥à¸±à¸à¹à¸«à¸¥à¸à¸à¹à¸­à¸¡à¸¹à¸¥..."):
        st.session_state.db = load_db()

DB            = st.session_state.db
role          = st.session_state.role
can_edit      = role in [ROLE_ADMIN, ROLE_SUPER]
can_see_money = role == ROLE_ADMIN
can_summary   = role == ROLE_ADMIN
can_settings  = role == ROLE_ADMIN

ROLE_LABEL = {ROLE_ADMIN:"ð à¸à¸¹à¹à¸à¸£à¸´à¸«à¸²à¸£", ROLE_SUPER:"ð§ à¸«à¸±à¸§à¸«à¸à¹à¸²à¸à¸²à¸", ROLE_VIEW:"ðï¸ à¸à¸¹à¸à¹à¸­à¸¡à¸¹à¸¥"}

# âââ SIDEBAR âââââââââââââââââââââââââââââââââââââââââ
pages_map = {}
pages_map["ð Dashboard"]           = "dashboard"
if can_edit:    pages_map["â à¸à¸±à¸à¸à¸¶à¸à¸à¸²à¸à¸à¸£à¸°à¸à¸³à¸§à¸±à¸"] = "add"
pages_map["ð à¸à¸¹à¸à¹à¸­à¸¡à¸¹à¸¥à¸£à¸²à¸¢à¸§à¸±à¸"]      = "view"
if can_summary: pages_map["ð à¸ªà¸£à¸¸à¸à¸£à¸²à¸¢à¸à¸§à¸"]       = "summary"
if can_settings:pages_map["âï¸ à¸à¸±à¹à¸à¸à¹à¸²à¸£à¸°à¸à¸"]      = "settings"

# Validate stored page_key
if st.session_state.page_key not in pages_map:
    st.session_state.page_key = list(pages_map.keys())[0]

with st.sidebar:
    st.markdown(f"""
    <div style="padding:4px 0 14px 0">
      <div style="font-size:1.25rem;font-weight:700">âï¸ KHT Daily Report</div>
      <div style="font-size:0.78rem;color:#e07b2b">à¸£à¸°à¸à¸à¸à¸±à¸à¸à¸¶à¸à¸à¸¥à¸à¸²à¸à¸à¸¹à¹à¸£à¸±à¸à¹à¸«à¸¡à¸²</div>
      <div style="font-size:0.75rem;color:rgba(255,255,255,0.55);margin-top:5px">
        {ROLE_LABEL[role]}</div>
    </div>
    """, unsafe_allow_html=True)

    cur_idx = list(pages_map.keys()).index(st.session_state.page_key)
    chosen  = st.radio("à¹à¸¡à¸à¸¹", list(pages_map.keys()),
                        index=cur_idx, label_visibility="collapsed")
    st.session_state.page_key = chosen
    PAGE = pages_map[chosen]

    st.markdown("---")
    if st.button("ð à¸£à¸µà¹à¸à¸£à¸à¸à¹à¸­à¸¡à¸¹à¸¥", use_container_width=True):
        with st.spinner("à¸à¸³à¸¥à¸±à¸à¹à¸«à¸¥à¸..."):
            st.session_state.db = load_db()
        st.rerun()

    if can_see_money:
        export_bytes = json.dumps(DB, ensure_ascii=False, indent=2).encode('utf-8')
        st.download_button("ð¥ Export JSON", data=export_bytes,
                           file_name=f"kht-{today_str()}.json",
                           mime="application/json", use_container_width=True)

    st.markdown("---")
    if st.button("ðª à¸­à¸­à¸à¸à¸²à¸à¸£à¸°à¸à¸", use_container_width=True):
        for k in ['logged_in','role','db','wi','edit_id','page_key']:
            st.session_state.pop(k, None)
        st.rerun()

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE: DASHBOARD
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
if PAGE == "dashboard":
    now  = date.today()
    yr, mo, dy = now.year, now.month, now.day
    p_cur = 1 if dy <= 15 else 2
    ps, pe = pdates(yr, mo, p_cur)
    ms = f"{yr}-{str(mo).zfill(2)}-01"
    me = f"{yr}-{str(mo).zfill(2)}-31"
    today = today_str()

    period_lbl = f"à¸à¸§à¸à¸à¸µà¹ {p_cur}: {'1â15' if p_cur==1 else '16âà¸ªà¸´à¹à¸à¹à¸à¸·à¸­à¸'} {TH_MO[mo]} {yr+543}"
    st.markdown(f"### ð Dashboard &nbsp;<span style='font-size:0.85rem;color:#777'>{period_lbl}</span>",
                unsafe_allow_html=True)

    today_rpts  = [r for r in DB['reports'] if r['date'] == today]
    period_rpts = [r for r in DB['reports'] if ps <= r['date'] <= pe]
    month_rpts  = [r for r in DB['reports'] if ms <= r['date'] <= me]

    if can_see_money:
        today_tot  = sum(_f(r['total']) for r in today_rpts)
        period_tot = sum(_f(r['total']) for r in period_rpts)
        month_tot  = sum(_f(r['total']) for r in month_rpts)
        unpaid = sum(
            period_total(t['id'], yr, mo, p)
            for t in DB['teams'] for p in [1,2]
            if not (lambda pay: pay and pay.get('paid'))(get_payment(t['id'],yr,mo,p))
        )
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("ð à¸¢à¸­à¸à¸§à¸±à¸à¸à¸µà¹",   f"à¸¿ {N(today_tot)}")
        with c2: st.metric("ð à¸¢à¸­à¸à¸à¸§à¸à¸à¸µà¹",   f"à¸¿ {N(period_tot)}")
        with c3: st.metric("ðï¸ à¸¢à¸­à¸à¹à¸à¸·à¸­à¸à¸à¸µà¹", f"à¸¿ {N(month_tot)}")
        with c4: st.metric("â ï¸ à¸à¹à¸²à¸à¸à¸³à¸£à¸°",    f"à¸¿ {N(unpaid)}")
    else:
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("ð à¸£à¸²à¸¢à¸à¸²à¸à¸§à¸±à¸à¸à¸µà¹",    f"{len(today_rpts)} à¸£à¸²à¸¢à¸à¸²à¸£")
        with c2: st.metric("ð à¸£à¸²à¸¢à¸à¸²à¸à¸à¸§à¸à¸à¸µà¹",    f"{len(period_rpts)} à¸£à¸²à¸¢à¸à¸²à¸£")
        with c3: st.metric("ðï¸ à¸£à¸²à¸¢à¸à¸²à¸à¹à¸à¸·à¸­à¸à¸à¸µà¹",  f"{len(month_rpts)} à¸£à¸²à¸¢à¸à¸²à¸£")

    st.markdown("---")
    ca, cb = st.columns(2)
    with ca: st.metric("ð¥ à¸à¸³à¸à¸§à¸à¸à¸µà¸¡",   len(DB['teams']))
    with cb: st.metric("ð§ à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸", len(DB['projects']))

    st.markdown("---")
    st.markdown("#### ð à¸à¸¥à¸à¸²à¸à¸§à¸±à¸à¸à¸µà¹")
    if not today_rpts:
        st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¹à¸­à¸¡à¸¹à¸¥à¸§à¸±à¸à¸à¸µà¹")
    else:
        rows = []
        for r in today_rpts:
            items_str = " | ".join(
                f"{get_proj(it['pid'])['name']}: {it['qty']} {it['unit']}"
                + (f" = {N(it['amt'])}à¸¿" if can_see_money else "")
                for it in r['items']
            )
            row = {"à¸à¸µà¸¡": get_team(r['teamId'])['name'], "à¸à¸à¸à¸²à¸": r['workers'],
                   "à¸£à¸²à¸¢à¸à¸²à¸£à¸à¸²à¸": items_str}
            if can_see_money: row["à¸£à¸§à¸¡ (à¸¿)"] = N(r['total'])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE: ADD / EDIT REPORT
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
elif PAGE == "add" and can_edit:
    st.markdown("### â à¸à¸±à¸à¸à¸¶à¸à¸à¸²à¸à¸à¸£à¸°à¸à¸³à¸§à¸±à¸")

    edit_rec = None
    if st.session_state.edit_id:
        edit_rec = next((r for r in DB['reports'] if r['id']==st.session_state.edit_id), None)
        if edit_rec and not st.session_state.wi:
            st.session_state.wi = [dict(i) for i in edit_rec['items']]
        if edit_rec:
            st.info(f"âï¸ à¸à¸³à¸¥à¸±à¸à¹à¸à¹à¹à¸: {thd(edit_rec['date'])} â {get_team(edit_rec['teamId'])['name']}")

    col1, col2, col3 = st.columns([1.5,1.5,1])
    with col1:
        default_dt = datetime.strptime(edit_rec['date'],'%Y-%m-%d').date() if edit_rec else date.today()
        r_date = st.date_input("ð à¸§à¸±à¸à¸à¸µà¹ *", value=default_dt)
    with col2:
        tnames = [t['name'] for t in DB['teams']]
        tids   = [t['id']   for t in DB['teams']]
        if not tnames:
            st.warning("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸µà¸¡ â à¸à¸­à¹à¸«à¹ Admin à¹à¸à¸´à¹à¸¡à¸à¸µà¸¡à¸à¹à¸­à¸"); st.stop()
        def_ti = tids.index(edit_rec['teamId']) if edit_rec and edit_rec['teamId'] in tids else 0
        r_tname = st.selectbox("ð¥ à¸à¸µà¸¡à¸à¸¹à¹à¸£à¸±à¸à¹à¸«à¸¡à¸² *", tnames, index=def_ti)
        r_tid   = tids[tnames.index(r_tname)]
    with col3:
        r_workers = st.number_input("ð§âð§ à¸à¸³à¸à¸§à¸à¸à¸à¸à¸²à¸ *", min_value=0,
                                    value=_i(edit_rec['workers']) if edit_rec else 0)
    r_note = st.text_input("ð à¸«à¸¡à¸²à¸¢à¹à¸«à¸à¸¸", value=edit_rec.get('note','') if edit_rec else '')

    st.markdown("---")
    st.markdown("**ð à¸£à¸²à¸¢à¸à¸²à¸£à¸à¸²à¸**")

    if not DB['projects']:
        st.warning("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸ â à¸à¸­à¹à¸«à¹ Admin à¹à¸à¸´à¹à¸¡à¸à¹à¸­à¸")
    else:
        pnames = [p['name'] for p in DB['projects']]
        pids   = [p['id']   for p in DB['projects']]
        to_rm  = None

        for idx, item in enumerate(st.session_state.wi):
            if can_see_money:
                c1,c2,c3,c4,c5 = st.columns([2.5,1,1,1.2,0.5])
            else:
                c1,c2,c4,c5 = st.columns([3,1.5,1.5,0.5])

            with c1:
                cur_pi = pids.index(item['pid']) if item.get('pid') in pids else 0
                sel = st.selectbox(f"à¸à¸²à¸#{idx+1}", pnames, index=cur_pi,
                                   key=f"psel_{idx}", label_visibility="collapsed")
                sp = DB['projects'][pnames.index(sel)]
                item['pid']  = sp['id']
                item['unit'] = sp['unit']
                item['rate'] = _f(sp['unitRate'])
            with c2:
                st.text_input("à¸«à¸à¹à¸§à¸¢", value=item['unit'], disabled=True,
                              key=f"unit_{idx}", label_visibility="collapsed")
            if can_see_money:
                with c3:
                    st.text_input("Rate", value=N(item['rate']), disabled=True,
                                  key=f"rate_{idx}", label_visibility="collapsed")
            with c4:
                item['qty'] = st.number_input("à¸à¸£à¸´à¸¡à¸²à¸", min_value=0.0,
                                              value=float(item.get('qty',0)),
                                              step=0.01, key=f"qty_{idx}",
                                              label_visibility="collapsed")
                item['amt'] = item['qty'] * item['rate']
            with c5:
                if st.button("ðï¸", key=f"del_{idx}"): to_rm = idx

        if to_rm is not None:
            st.session_state.wi.pop(to_rm); st.rerun()

        ab, _ = st.columns([1,5])
        with ab:
            if st.button("â à¹à¸à¸´à¹à¸¡à¸£à¸²à¸¢à¸à¸²à¸£à¸à¸²à¸"):
                fp = DB['projects'][0]
                st.session_state.wi.append({'id':uid(),'pid':fp['id'],
                    'unit':fp['unit'],'rate':_f(fp['unitRate']),'qty':0,'amt':0})
                st.rerun()

        if st.session_state.wi and can_see_money:
            grand = sum(w['amt'] for w in st.session_state.wi)
            st.markdown(f"**à¸£à¸§à¸¡à¸à¸±à¹à¸à¸«à¸¡à¸: <span style='color:#e07b2b;font-size:1.1rem'>à¸¿ {N(grand)}</span>**",
                        unsafe_allow_html=True)

        st.markdown("---")
        s1,s2,_ = st.columns([1.2,1,5])
        with s1: save_btn = st.button("ð¾ à¸à¸±à¸à¸à¸¶à¸à¸à¹à¸­à¸¡à¸¹à¸¥", type="primary", use_container_width=True)
        with s2:
            if st.button("ðï¸ à¸¥à¹à¸²à¸à¸à¹à¸­à¸¡à¸¹à¸¥", use_container_width=True):
                st.session_state.wi = []; st.session_state.edit_id = None; st.rerun()

        if save_btn:
            if not st.session_state.wi:
                st.error("à¸à¸£à¸¸à¸à¸²à¹à¸à¸´à¹à¸¡à¸£à¸²à¸¢à¸à¸²à¸£à¸à¸²à¸à¸­à¸¢à¹à¸²à¸à¸à¹à¸­à¸¢ 1 à¸£à¸²à¸¢à¸à¸²à¸£")
            elif any(w['qty'] <= 0 for w in st.session_state.wi):
                st.error("à¸à¸£à¸¸à¸à¸²à¸£à¸°à¸à¸¸à¸à¸£à¸´à¸¡à¸²à¸à¸à¸²à¸à¹à¸«à¹à¸à¸£à¸à¸à¸¸à¸à¸£à¸²à¸¢à¸à¸²à¸£")
            else:
                total = sum(w['amt'] for w in st.session_state.wi)
                rec = {
                    'id':      st.session_state.edit_id or uid(),
                    'date':    r_date.isoformat(),
                    'teamId':  r_tid,
                    'workers': int(r_workers),
                    'note':    r_note,
                    'items':   [dict(w) for w in st.session_state.wi],
                    'total':   total,
                }
                with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."):
                    if st.session_state.edit_id:
                        idx2 = next((i for i,r in enumerate(DB['reports']) if r['id']==rec['id']), None)
                        if idx2 is not None: DB['reports'][idx2] = rec
                        msg = "â à¹à¸à¹à¹à¸à¸ªà¸³à¹à¸£à¹à¸"
                    else:
                        DB['reports'].append(rec)
                        msg = "â à¸à¸±à¸à¸à¸¶à¸à¸ªà¸³à¹à¸£à¹à¸"
                    save_db("reports")
                st.success(msg)
                st.session_state.wi = []; st.session_state.edit_id = None
                st.rerun()

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE: VIEW REPORTS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
elif PAGE == "view":
    st.markdown("### ð à¸à¸¹à¸à¹à¸­à¸¡à¸¹à¸¥à¸£à¸²à¸¢à¸§à¸±à¸")

    fc1,fc2,fc3 = st.columns([1.5,1,1])
    with fc1: ftype = st.selectbox("à¸à¸²à¸£à¸à¹à¸à¸«à¸²", ["à¸à¸±à¹à¸à¸«à¸¡à¸","à¸£à¸°à¸à¸¸à¸§à¸±à¸à¸à¸µà¹","à¸à¹à¸§à¸à¸§à¸±à¸à¸à¸µà¹"])
    with fc2:
        topts = ["à¸à¸¸à¸à¸à¸µà¸¡"] + [t['name'] for t in DB['teams']]
        f_team = st.selectbox("à¸à¸µà¸¡", topts)
    with fc3: sort_dir = st.selectbox("à¹à¸£à¸µà¸¢à¸", ["à¸§à¸±à¸à¸à¸µà¹à¸¥à¹à¸²à¸ªà¸¸à¸","à¸§à¸±à¸à¸à¸µà¹à¹à¸à¹à¸²à¸ªà¸¸à¸"])

    f_date = f_start = f_end = None
    if ftype == "à¸£à¸°à¸à¸¸à¸§à¸±à¸à¸à¸µà¹": f_date  = st.date_input("à¸§à¸±à¸à¸à¸µà¹", value=date.today())
    elif ftype == "à¸à¹à¸§à¸à¸§à¸±à¸à¸à¸µà¹":
        dc1,dc2 = st.columns(2)
        with dc1: f_start = st.date_input("à¸à¸²à¸à¸§à¸±à¸à¸à¸µà¹")
        with dc2: f_end   = st.date_input("à¸à¸¶à¸à¸§à¸±à¸à¸à¸µà¹")

    rpts = list(DB['reports'])
    if f_team != "à¸à¸¸à¸à¸à¸µà¸¡":
        tid2 = next((t['id'] for t in DB['teams'] if t['name']==f_team), None)
        if tid2: rpts = [r for r in rpts if r['teamId']==tid2]
    if ftype=="à¸£à¸°à¸à¸¸à¸§à¸±à¸à¸à¸µà¹" and f_date:
        rpts = [r for r in rpts if r['date']==f_date.isoformat()]
    elif ftype=="à¸à¹à¸§à¸à¸§à¸±à¸à¸à¸µà¹":
        if f_start: rpts = [r for r in rpts if r['date']>=f_start.isoformat()]
        if f_end:   rpts = [r for r in rpts if r['date']<=f_end.isoformat()]
    rpts.sort(key=lambda r: r['date'], reverse=(sort_dir=="à¸§à¸±à¸à¸à¸µà¹à¸¥à¹à¸²à¸ªà¸¸à¸"))

    total_sum = sum(_f(r['total']) for r in rpts)
    info_txt  = f"à¸à¸ **{len(rpts)}** à¸£à¸²à¸¢à¸à¸²à¸£"
    if can_see_money: info_txt += f" &nbsp;|&nbsp; à¸£à¸§à¸¡ **à¸¿ {N(total_sum)}**"
    st.markdown(info_txt, unsafe_allow_html=True)
    st.markdown("---")

    if not rpts:
        st.info("à¹à¸¡à¹à¸à¸à¸à¹à¸­à¸¡à¸¹à¸¥")
    else:
        for r in rpts:
            tname2 = get_team(r['teamId'])['name']
            hdr = f"ð {thd(r['date'])}  â  {tname2}  â  ð· {r['workers']} à¸à¸"
            if can_see_money: hdr += f"  â  à¸¿ {N(r['total'])}"
            with st.expander(hdr):
                dc1,dc2 = st.columns([3,1])
                with dc1:
                    irows = []
                    for it in r['items']:
                        p2 = get_proj(it['pid'])
                        row2 = {"à¸à¸²à¸": p2['name'], "à¸«à¸à¹à¸§à¸¢": it['unit'], "à¸à¸£à¸´à¸¡à¸²à¸": it['qty']}
                        if can_see_money:
                            row2["Rate(à¸¿)"] = N(it['rate'])
                            row2["à¹à¸à¸´à¸(à¸¿)"] = N(it['amt'])
                        irows.append(row2)
                    st.dataframe(pd.DataFrame(irows), hide_index=True, use_container_width=True)
                    if r.get('note'): st.caption(f"ð {r['note']}")
                with dc2:
                    st.metric("à¸à¸à¸à¸²à¸", r['workers'])
                    if can_see_money: st.metric("à¸£à¸§à¸¡ (à¸¿)", N(r['total']))
                    if can_edit:
                        eb1,eb2 = st.columns(2)
                        with eb1:
                            if st.button("âï¸ à¹à¸à¹à¹à¸", key=f"ed_{r['id']}"):
                                st.session_state.edit_id = r['id']
                                st.session_state.wi = []
                                st.session_state.page_key = "â à¸à¸±à¸à¸à¸¶à¸à¸à¸²à¸à¸à¸£à¸°à¸à¸³à¸§à¸±à¸"
                                st.rerun()
                        with eb2:
                            if st.button("ðï¸ à¸¥à¸", key=f"dl_{r['id']}"):
                                DB['reports'] = [x for x in DB['reports'] if x['id']!=r['id']]
                                with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("reports")
                                st.rerun()

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE: PERIOD REPORT
CPAGE: PERIOD REPORT
CPAGE: PERIOD REPORT
CPAGE: PERIOD REPORT
CPAGE: PERIOD SUMWARY (Admin only)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
elif PAGE == "summary" and can_summary:
    st.markdown("### ð à¸ªà¸£à¸¸à¸à¸£à¸²à¸¢à¸à¸§à¸")
    sc1,sc2 = st.columns(2)
    with sc1: sel_year  = st.number_input("à¸à¸µ (à¸.à¸¨.)", min_value=2020, max_value=2035, value=date.today().year)
    with sc2: sel_month = st.selectbox("à¹à¸à¸·à¸­à¸", list(range(1,13)),
                                        index=date.today().month-1,
                                        format_func=lambda m: TH_MO[m])
    yr2, mo2 = int(sel_year), int(sel_month)

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
            f"<div class='period-hdr'>à¸à¸§à¸à¸à¸µà¹ {period}: {sday}â{eday} {TH_MO[mo2]} {yr2+543} "
            f"&nbsp;|&nbsp; à¸£à¸§à¸¡ à¸¿ {N(ptot)} &nbsp;|&nbsp; "
            f"<span style='color:#a8d8a8'>à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§ à¸¿ {N(paid)}</span> &nbsp;"
            f"<span style='color:#f8a9a9'>à¸à¹à¸²à¸ à¸¿ {N(ptot-paid)}</span></div>",
            unsafe_allow_html=True)

        if not DB['teams']:
            st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸µà¸¡"); return

        for t,tot,rpts,pay,ip in rows_d:
            days   = len(rpts)
            manday = sum(_i(r['workers']) for r in rpts)
            rc1,rc2,rc3 = st.columns([3,1.5,1.5])
            with rc1:
                st.markdown(f"**{t['name']}**")
                st.caption(f"{days} à¸§à¸±à¸à¸à¸³à¸à¸²à¸ | {manday} à¸à¸-à¸§à¸±à¸")
                if ip: st.caption(f"â à¸à¹à¸²à¸¢à¸§à¸±à¸à¸à¸µà¹ {thd(pay.get('paidDate'))} {pay.get('note','')}")
            with rc2:
                st.metric("", f"à¸¿ {N(tot)}")
            with rc3:
                sk = f"mark_{t['id']}_{period}"
                if ip:
                    st.markdown("<div class='b-paid'>â à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§</div>", unsafe_allow_html=True)
                    if tot>0 and st.button("à¸¢à¸à¹à¸¥à¸´à¸", key=f"un_{t['id']}_{period}", use_container_width=True):
                        for px in DB['payments']:
                            if px['tid']==t['id'] and _i(px['y'])==yr2 and _i(px['mo'])==mo2 and _i(px['p'])==period:
                                px['paid']=False; px['paidDate']=''
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("payments")
                        st.rerun()
                else:
                    if tot>0:
                        st.markdown("<div class='b-unpaid'>à¸¢à¸±à¸à¹à¸¡à¹à¹à¸à¹à¸à¹à¸²à¸¢</div>", unsafe_allow_html=True)
                        if st.button("ð° à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§", key=f"pk_{t['id']}_{period}", use_container_width=True):
                            st.session_state[sk] = True; st.rerun()
                    else:
                        st.caption("à¹à¸¡à¹à¸¡à¸µà¸à¸²à¸")

            if st.session_state.get(f"mark_{t['id']}_{period}"):
                with st.form(key=f"pf_{t['id']}_{period}"):
                    pd_inp = st.date_input("à¸§à¸±à¸à¸à¸µà¹à¸à¹à¸²à¸¢", value=date.today())
                    pn_inp = st.text_input("à¸«à¸¡à¸²à¸¢à¹à¸«à¸à¸¸")
                    if st.form_submit_button("â à¸¢à¸·à¸à¸¢à¸±à¸"):
                        prec = {'id':uid(),'tid':t['id'],'y':yr2,'mo':mo2,'p':period,
                                'paid':True,'paidDate':pd_inp.isoformat(),'note':pn_inp}
                        idx3 = next((i for i,px in enumerate(DB['payments'])
                                     if px['tid']==t['id'] and _i(px['y'])==yr2 and
                                        _i(px['mo'])==mo2 and _i(px['p'])==period), None)
                        if idx3 is not None: DB['payments'][idx3] = prec
                        else: DB['payments'].append(prec)
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("payments")
                        st.session_state[f"mark_{t['id']}_{period}"] = False
                        st.rerun()
            st.markdown("<hr style='margin:6px 0;border-color:#f0f2f5'>", unsafe_allow_html=True)

    render_period(1)
    st.markdown("---")
    render_period(2)

    st.markdown("---")
    st.markdown(f"#### ð à¸ªà¸£à¸¸à¸à¸£à¸§à¸¡ {TH_MO[mo2]} {yr2+543}")
    m_str = str(mo2).zfill(2)
    cum_rows = []
    for t in DB['teams']:
        trpts = [r for r in DB['reports'] if r['teamId']==t['id']
                 and r['date'].startswith(f"{yr2}-{m_str}")]
        tot    = sum(_f(r['total']) for r in trpts)
        manday = sum(_i(r['workers']) for r in trpts)
        pd_tot = 0.0
        for pp in [1,2]:
            pay = get_payment(t['id'], yr2, mo2, pp)
            if pay and pay.get('paid'):
                s2,e2 = pdates(yr2, mo2, pp)
                pd_tot += sum(_f(r['total']) for r in DB['reports']
                              if r['teamId']==t['id'] and s2<=r['date']<=e2)
        cum_rows.append({"à¸à¸µà¸¡":t['name'],"à¸à¸-à¸§à¸±à¸":manday,
                         "à¸¢à¸­à¸à¸£à¸§à¸¡(à¸¿)":N(tot),"à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§(à¸¿)":N(pd_tot),"à¸à¹à¸²à¸(à¸¿)":N(tot-pd_tot)})
    if cum_rows:
        gt  = sum(_f(r["à¸¢à¸­à¸à¸£à¸§à¸¡(à¸¿)"].replace(',',''))  for r in cum_rows)
        gp  = sum(_f(r["à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§(à¸¿)"].replace(',','')) for r in cum_rows)
        gmd = sum(r["à¸à¸-à¸§à¸±à¸"] for r in cum_rows)
        cum_rows.append({"à¸à¸µà¸¡":"à¸£à¸§à¸¡à¸à¸±à¹à¸à¸«à¸¡à¸","à¸à¸-à¸§à¸±à¸":gmd,
                         "à¸¢à¸­à¸à¸£à¸§à¸¡(à¸¿)":N(gt),"à¸à¹à¸²à¸¢à¹à¸¥à¹à¸§(à¸¿)":N(gp),"à¸à¹à¸²à¸(à¸¿)":N(gt-gp)})
        st.dataframe(pd.DataFrame(cum_rows), hide_index=True, use_container_width=True)
    else:
        st.info("à¹à¸¡à¹à¸¡à¸µà¸à¹à¸­à¸¡à¸¹à¸¥à¹à¸à¸·à¸­à¸à¸à¸µà¹")

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE: SETTINGS (Admin only)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
elif PAGE == "settings" and can_settings:
    st.markdown("### âï¸ à¸à¸±à¹à¸à¸à¹à¸²à¸£à¸°à¸à¸")
    tab_t, tab_ct, tab_p = st.tabs(["ð¥ à¸à¸µà¸¡à¸à¸¹à¹à¸£à¸±à¸à¹à¸«à¸¡à¸²", "ð à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸", "ð§ à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸ / Unit Rate"])

    # ââ helpers for contract type dropdown ââ
    ct_list   = DB.get('contractTypes', [])
    ct_names  = [c['name'] for c in ct_list]
    ct_ids    = [c['id']   for c in ct_list]
    ct_opts   = ["â à¹à¸¡à¹à¸£à¸°à¸à¸¸ â"] + ct_names   # index 0 = none

    def ct_idx(ctid):
        """Return dropdown index for a given contractTypeId (0 = none)."""
        try: return ct_ids.index(ctid) + 1
        except: return 0

    with tab_t:
        with st.expander("â à¹à¸à¸´à¹à¸¡à¸à¸µà¸¡à¹à¸«à¸¡à¹", expanded=(not DB['teams'])):
            with st.form("add_team"):
                t1,t2 = st.columns(2)
                with t1: tn = st.text_input("à¸à¸·à¹à¸­à¸à¸µà¸¡ *")
                with t2: tnote = st.text_input("à¸«à¸¡à¸²à¸¢à¹à¸«à¸à¸¸")
                t3,_ = st.columns([1,1])
                with t3:
                    if ct_opts:
                        t_ct_sel = st.selectbox("à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸", ct_opts)
                    else:
                        st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸ â à¹à¸à¸´à¹à¸¡à¹à¸à¹à¸à¸µà¹ Tab 'à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸'")
                        t_ct_sel = "â à¹à¸¡à¹à¸£à¸°à¸à¸¸ â"
                if st.form_submit_button("ð¾ à¸à¸±à¸à¸à¸¶à¸", type="primary"):
                    if not tn.strip(): st.error("à¸à¸£à¸¸à¸à¸²à¸£à¸°à¸à¸¸à¸à¸·à¹à¸­à¸à¸µà¸¡")
                    else:
                        new_ctid = ct_ids[ct_names.index(t_ct_sel)] if t_ct_sel != "â à¹à¸¡à¹à¸£à¸°à¸à¸¸ â" else ''
                        DB['teams'].append({'id':uid(),'name':tn.strip(),
                                            'contractTypeId':new_ctid,'note':tnote.strip()})
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("teams")
                        st.success("â à¸à¸±à¸à¸à¸¶à¸à¸à¸µà¸¡à¸ªà¸³à¹à¸£à¹à¸"); st.rerun()
        st.markdown("---")
        if not DB['teams']: st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸µà¸¡")
        for t in DB['teams']:
            ct_name_disp = get_contract_type(t.get('contractTypeId','')).get('name','-') if t.get('contractTypeId') else '-'
            with st.expander(f"**{t['name']}** â {ct_name_disp} â {t.get('note','-')}"):
                e1,e2 = st.columns(2)
                with e1: nn = st.text_input("à¸à¸·à¹à¸­à¸à¸µà¸¡", value=t['name'], key=f"tn_{t['id']}")
                with e2: nnt = st.text_input("à¸«à¸¡à¸²à¸¢à¹à¸«à¸à¸¸", value=t.get('note',''), key=f"tnote_{t['id']}")
                e3,_ = st.columns([1,1])
                with e3:
                    nct_sel = st.selectbox("à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸", ct_opts,
                                           index=ct_idx(t.get('contractTypeId','')),
                                           key=f"tct_{t['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("ð¾ à¸à¸±à¸à¸à¸¶à¸", key=f"ts_{t['id']}", use_container_width=True):
                        t['name'] = nn; t['note'] = nnt
                        t['contractTypeId'] = ct_ids[ct_names.index(nct_sel)] if nct_sel != "â à¹à¸¡à¹à¸£à¸°à¸à¸¸ â" else ''
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("teams")
                        st.success("à¸à¸±à¸à¸à¸¶à¸à¹à¸¥à¹à¸§"); st.rerun()
                with b2:
                    if st.button("ðï¸ à¸¥à¸", key=f"td_{t['id']}", use_container_width=True):
                        DB['teams'] = [x for x in DB['teams'] if x['id']!=t['id']]
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("teams")
                        st.rerun()

    # ââââââââââââââââââââââââââââââââââââââââ
    # TAB: à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸
    # ââââââââââââââââââââââââââââââââââââââââ
    with tab_ct:
        with st.expander("â à¹à¸à¸´à¹à¸¡à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸à¹à¸«à¸¡à¹", expanded=(not ct_list)):
            with st.form("add_ct"):
                ct1, ct2 = st.columns(2)
                with ct1: ctn = st.text_input("à¸à¸·à¹à¸­à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸ * (à¹à¸à¹à¸ à¸à¸£à¸´à¸©à¸±à¸, à¸à¸£à¸¡)")
                with ct2:
                    cm_opts  = list(CALC_MODES.values())
                    cm_keys  = list(CALC_MODES.keys())
                    ctm_sel  = st.selectbox("à¸§à¸´à¸à¸µà¸à¸³à¸à¸§à¸ *", cm_opts)
                if st.form_submit_button("ð¾ à¸à¸±à¸à¸à¸¶à¸", type="primary"):
                    if not ctn.strip(): st.error("à¸à¸£à¸¸à¸à¸²à¸£à¸°à¸à¸¸à¸à¸·à¹à¸­à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸")
                    else:
                        new_cm = cm_keys[cm_opts.index(ctm_sel)]
                        DB.setdefault('contractTypes', []).append(
                            {'id':uid(),'name':ctn.strip(),'calcMode':new_cm})
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("contractTypes")
                        st.success("â à¸à¸±à¸à¸à¸¶à¸à¸ªà¸³à¹à¸£à¹à¸"); st.rerun()
        st.markdown("---")
        if not ct_list:
            st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸ â à¸à¸ â à¹à¸à¸´à¹à¸¡à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸£à¸à¹à¸²à¸à¹à¸«à¸¡à¹")
        for ct in ct_list:
            cm_label = CALC_MODES.get(ct.get('calcMode','unit_rate'), '-')
            with st.expander(f"**{ct['name']}** â {cm_label}"):
                ec1, ec2 = st.columns(2)
                with ec1: nctn = st.text_input("à¸à¸·à¹à¸­", value=ct['name'], key=f"ctn_{ct['id']}")
                with ec2:
                    cur_cm_idx = cm_keys.index(ct.get('calcMode','unit_rate')) if ct.get('calcMode') in cm_keys else 0
                    nctm_sel   = st.selectbox("à¸§à¸´à¸à¸µà¸à¸³à¸à¸§à¸", cm_opts, index=cur_cm_idx, key=f"ctm_{ct['id']}")
                eb1, eb2 = st.columns(2)
                with eb1:
                    if st.button("ð¾ à¸à¸±à¸à¸à¸¶à¸", key=f"cts_{ct['id']}", use_container_width=True):
                        ct['name']     = nctn
                        ct['calcMode'] = cm_keys[cm_opts.index(nctm_sel)]
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("contractTypes")
                        st.success("à¸à¸±à¸à¸à¸¶à¸à¹à¸¥à¹à¸§"); st.rerun()
                with eb2:
                    if st.button("ðï¸ à¸¥à¸", key=f"ctd_{ct['id']}", use_container_width=True):
                        DB['contractTypes'] = [x for x in DB['contractTypes'] if x['id']!=ct['id']]
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("contractTypes")
                        st.rerun()

    with tab_p:
        with st.expander("â à¹à¸à¸´à¹à¸¡à¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸à¹à¸«à¸¡à¹", expanded=(not DB['projects'])):
            with st.form("add_proj"):
                p1,p2 = st.columns(2)
                with p1: pn = st.text_input("à¸à¸·à¹à¸­à¸à¸²à¸ *")
                with p2: pd2 = st.text_input("à¸à¸³à¸­à¸à¸´à¸à¸²à¸¢")
                p3,p4 = st.columns(2)
                with p3: pu = st.text_input("à¸«à¸à¹à¸§à¸¢ * (à¹à¸à¹à¸ à¸¡., kg)")
                with p4: pr = st.number_input("Unit Rate (à¸¿/à¸«à¸à¹à¸§à¸¢)", min_value=0.0, step=0.01)
                if st.form_submit_button("ð¾ à¸à¸±à¸à¸à¸¶à¸", type="primary"):
                    if not pn.strip() or not pu.strip():
                        st.error("à¸à¸£à¸¸à¸à¸²à¸à¸£à¸­à¸à¸à¹à¸­à¸¡à¸¹à¸¥à¹à¸«à¹à¸à¸£à¸")
                    else:
                        DB['projects'].append({'id':uid(),'name':pn.strip(),'unit':pu.strip(),
                                               'unitRate':pr,'description':pd2.strip()})
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("projects")
                        st.success("â à¸à¸±à¸à¸à¸¶à¸à¸ªà¸³à¹à¸£à¹à¸"); st.rerun()
        st.markdown("---")
        if not DB['projects']: st.info("à¸¢à¸±à¸à¹à¸¡à¹à¸¡à¸µà¸à¸£à¸°à¹à¸ à¸à¸à¸²à¸")
        for p in DB['projects']:
            with st.expander(f"**{p['name']}** â {p['unit']} â à¸¿{N(p['unitRate'])}/à¸«à¸à¹à¸§à¸¢"):
                e1,e2,e3 = st.columns([2,1,1])
                with e1:
                    npn = st.text_input("à¸à¸·à¹à¸­à¸à¸²à¸", value=p['name'], key=f"pn_{p['id']}")
                    npd = st.text_input("à¸à¸³à¸­à¸à¸´à¸à¸²à¸¢", value=p.get('description',''), key=f"pd_{p['id']}")
                with e2: npu = st.text_input("à¸«à¸à¹à¸§à¸¢", value=p['unit'], key=f"pu_{p['id']}")
                with e3: npr = st.number_input("Unit Rate", value=_f(p['unitRate']),
                                               min_value=0.0, step=0.01, key=f"pr_{p['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("ð¾ à¸à¸±à¸à¸à¸¶à¸", key=f"ps_{p['id']}", use_container_width=True):
                        p['name']=npn; p['unit']=npu; p['unitRate']=npr; p['description']=npd
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("projects")
                        st.success("à¸à¸±à¸à¸à¸¶à¸à¹à¸¥à¹à¸§"); st.rerun()
                with b2:
                    if st.button("ðï¸ à¸¥à¸", key=f"pd_{p['id']}", use_container_width=True):
                        DB['projects'] = [x for x in DB['projects'] if x['id']!=p['id']]
                        with st.spinner("à¸à¸³à¸¥à¸±à¸à¸à¸±à¸à¸à¸¶à¸..."): save_db("projects")
                        st.rerun()
