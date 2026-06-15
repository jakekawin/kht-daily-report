import streamlit as st
import json, calendar
from datetime import date, datetime
import uuid
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ─── PAGE CONFIG ─────────────────────────────────────
st.set_page_config(
    page_title="KHT Daily Report",
    page_icon="⛑️",
    layout="wide",
    initial_sidebar_state="expanded",
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
    "teams":         ["id", "name", "contractTypeId", "note"],
    "contractTypes": ["id", "name", "calcMode"],
    "projects":      ["id", "name", "unit", "unitRate", "description"],
    "reports":       ["id", "date", "teamId", "workers", "note", "items", "total"],
    "payments":      ["id", "tid", "y", "mo", "p", "paid", "paidDate", "note"],
}
CALC_MODES = {"unit_rate": "คิดตาม Unit Rate (ปริมาณ × ราคา)",
              "by_workers": "คิดตามจำนวนคน (คน × วัน × ราคา)"}

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
        st.error(f"❌ โหลดข้อมูลไม่ได้: {e}")
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
        st.error(f"❌ บันทึกไม่สำเร็จ: {e}")

# ─── DB ACCESSORS ─────────────────────────────────────
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

# ─── AUTH ─────────────────────────────────────────────
def check_login(role_key, pw):
    try: return pw == st.secrets["passwords"][role_key]
    except: return False

def login_page():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:40px 0 20px 0">
          <div style="font-size:3.5rem">⛑️</div>
          <h2 style="color:#1e3a5f;margin:8px 0 4px 0">KHT Daily Report</h2>
          <p style="color:#888;font-size:0.9rem">ระบบบันทึกผลงานผู้รับเหมา</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            role_display = st.selectbox(
                "ระดับผู้ใช้งาน",
                ["👑 ผู้บริหาร (Admin)", "🔧 หัวหน้างาน", "👁️ ดูข้อมูล"]
            )
            pw = st.text_input("🔑 รหัสผ่าน", type="password")
            sub = st.form_submit_button("เข้าสู่ระบบ", type="primary", use_container_width=True)

        if sub:
            rmap = {
                "👑 ผู้บริหาร (Admin)": ROLE_ADMIN,
                "🔧 หัวหน้างาน":       ROLE_SUPER,
                "👁️ ดูข้อมูล":         ROLE_VIEW,
            }
            rk = rmap[role_display]
            if check_login(rk, pw):
                st.session_state.logged_in = True
                st.session_state.role = rk
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
              ('edit_id', None), ('page_key', None)]:
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
if can_settings:pages_map["⚙️ ตั้งค่าระบบ"]      = "settings"

# Validate stored page_key
if st.session_state.page_key not in pages_map:
    st.session_state.page_key = list(pages_map.keys())[0]

with st.sidebar:
    st.markdown(f"""
    <div style="padding:4px 0 14px 0">
      <div style="font-size:1.25rem;font-weight:700">⛑️ KHT Daily Report</div>
      <div style="font-size:0.78rem;color:#e07b2b">ระบบบันทึกผลงานผู้รับเหมา</div>
      <div style="font-size:0.75rem;color:rgba(255,255,255,0.55);margin-top:5px">
        {ROLE_LABEL[role]}</div>
    </div>
    """, unsafe_allow_html=True)

    cur_idx = list(pages_map.keys()).index(st.session_state.page_key)
    chosen  = st.radio("เมนู", list(pages_map.keys()),
                        index=cur_idx, label_visibility="collapsed")
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
        for k in ['logged_in','role','db','wi','edit_id','page_key']:
            st.session_state.pop(k, None)
        st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════
if PAGE == "dashboard":
    now  = date.today()
    yr, mo, dy = now.year, now.month, now.day
    p_cur = 1 if dy <= 15 else 2
    ps, pe = pdates(yr, mo, p_cur)
    ms = f"{yr}-{str(mo).zfill(2)}-01"
    me = f"{yr}-{str(mo).zfill(2)}-31"
    today = today_str()

    period_lbl = f"งวดที่ {p_cur}: {'1–15' if p_cur==1 else '16–สิ้นเดือน'} {TH_MO[mo]} {yr+543}"
    st.markdown(f"### 📊 Dashboard &nbsp;<span style='font-size:0.85rem;color:#777'>{period_lbl}</span>",
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
        with c1: st.metric("📅 ยอดวันนี้",   f"฿ {N(today_tot)}")
        with c2: st.metric("📆 ยอดงวดนี้",   f"฿ {N(period_tot)}")
        with c3: st.metric("🗓️ ยอดเดือนนี้", f"฿ {N(month_tot)}")
        with c4: st.metric("⚠️ ค้างชำระ",    f"฿ {N(unpaid)}")
    else:
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("📅 รายงานวันนี้",    f"{len(today_rpts)} รายการ")
        with c2: st.metric("📆 รายงานงวดนี้",    f"{len(period_rpts)} รายการ")
        with c3: st.metric("🗓️ รายงานเดือนนี้",  f"{len(month_rpts)} รายการ")

    st.markdown("---")
    ca, cb = st.columns(2)
    with ca: st.metric("👥 จำนวนทีม",   len(DB['teams']))
    with cb: st.metric("🔧 ประเภทงาน", len(DB['projects']))

    st.markdown("---")
    st.markdown("#### 📋 ผลงานวันนี้")
    if not today_rpts:
        st.info("ยังไม่มีข้อมูลวันนี้")
    else:
        rows = []
        for r in today_rpts:
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
        if edit_rec:
            st.info(f"✏️ กำลังแก้ไข: {thd(edit_rec['date'])} — {get_team(edit_rec['teamId'])['name']}")

    col1, col2, col3 = st.columns([1.5,1.5,1])
    with col1:
        default_dt = datetime.strptime(edit_rec['date'],'%Y-%m-%d').date() if edit_rec else date.today()
        r_date = st.date_input("📅 วันที่ *", value=default_dt)
    with col2:
        tnames = [t['name'] for t in DB['teams']]
        tids   = [t['id']   for t in DB['teams']]
        if not tnames:
            st.warning("ยังไม่มีทีม — ขอให้ Admin เพิ่มทีมก่อน"); st.stop()
        def_ti = tids.index(edit_rec['teamId']) if edit_rec and edit_rec['teamId'] in tids else 0
        r_tname = st.selectbox("👥 ทีมผู้รับเหมา *", tnames, index=def_ti)
        r_tid   = tids[tnames.index(r_tname)]
    with col3:
        r_workers = st.number_input("🧑‍🔧 จำนวนคนงาน *", min_value=0,
                                    value=_i(edit_rec['workers']) if edit_rec else 0)
    r_note = st.text_input("📝 หมายเหตุ", value=edit_rec.get('note','') if edit_rec else '')

    st.markdown("---")
    st.markdown("**📋 รายการงาน**")

    if not DB['projects']:
        st.warning("ยังไม่มีประเภทงาน — ขอให้ Admin เพิ่มก่อน")
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
                sel = st.selectbox(f"งาน#{idx+1}", pnames, index=cur_pi,
                                   key=f"psel_{idx}", label_visibility="collapsed")
                sp = DB['projects'][pnames.index(sel)]
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
                st.session_state.wi = []; st.session_state.edit_id = None; st.rerun()

        if save_btn:
            if not st.session_state.wi:
                st.error("กรุณาเพิ่มรายการงานอย่างน้อย 1 รายการ")
            elif any(w['qty'] <= 0 for w in st.session_state.wi):
                st.error("กรุณาระบุปริมาณงานให้ครบทุกรายการ")
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
                with st.spinner("กำลังบันทึก..."):
                    if st.session_state.edit_id:
                        idx2 = next((i for i,r in enumerate(DB['reports']) if r['id']==rec['id']), None)
                        if idx2 is not None: DB['reports'][idx2] = rec
                        msg = "✅ แก้ไขสำเร็จ"
                    else:
                        DB['reports'].append(rec)
                        msg = "✅ บันทึกสำเร็จ"
                    save_db("reports")
                st.success(msg)
                st.session_state.wi = []; st.session_state.edit_id = None
                st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE: VIEW REPORTS
# ═══════════════════════════════════════════════════════
elif PAGE == "view":
    st.markdown("### 🔍 ดูข้อมูลรายวัน")

    fc1,fc2,fc3 = st.columns([1.5,1,1])
    with fc1: ftype = st.selectbox("การค้นหา", ["ทั้งหมด","ระบุวันที่","ช่วงวันที่"])
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
                with dc2:
                    st.metric("คนงาน", r['workers'])
                    if can_see_money: st.metric("รวม (฿)", N(r['total']))
                    if can_edit:
                        eb1,eb2 = st.columns(2)
                        with eb1:
                            if st.button("✏️ แก้ไข", key=f"ed_{r['id']}"):
                                st.session_state.edit_id = r['id']
                                st.session_state.wi = []
                                st.session_state.page_key = "➕ บันทึกงานประจำวัน"
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
    sc1,sc2 = st.columns(2)
    with sc1: sel_year  = st.number_input("ปี (ค.ศ.)", min_value=2020, max_value=2035, value=date.today().year)
    with sc2: sel_month = st.selectbox("เดือน", list(range(1,13)),
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
            f"<div class='period-hdr'>งวดที่ {period}: {sday}–{eday} {TH_MO[mo2]} {yr2+543} "
            f"&nbsp;|&nbsp; รวม ฿ {N(ptot)} &nbsp;|&nbsp; "
            f"<span style='color:#a8d8a8'>จ่ายแล้ว ฿ {N(paid)}</span> &nbsp;"
            f"<span style='color:#f8a9a9'>ค้าง ฿ {N(ptot-paid)}</span></div>",
            unsafe_allow_html=True)

        if not DB['teams']:
            st.info("ยังไม่มีทีม"); return

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
                        prec = {'id':uid(),'tid':t['id'],'y':yr2,'mo':mo2,'p':period,
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
    tab_t, tab_ct, tab_p = st.tabs(["👥 ทีมผู้รับเหมา", "📋 ประเภทการจ้าง", "🔧 ประเภทงาน / Unit Rate"])

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
                t3,_ = st.columns([1,1])
                with t3:
                    if ct_opts:
                        t_ct_sel = st.selectbox("ประเภทการจ้าง", ct_opts)
                    else:
                        st.info("ยังไม่มีประเภทการจ้าง — เพิ่มได้ที่ Tab 'ประเภทการจ้าง'")
                        t_ct_sel = "— ไม่ระบุ —"
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not tn.strip(): st.error("กรุณาระบุชื่อทีม")
                    else:
                        new_ctid = ct_ids[ct_names.index(t_ct_sel)] if t_ct_sel != "— ไม่ระบุ —" else ''
                        DB['teams'].append({'id':uid(),'name':tn.strip(),
                                            'contractTypeId':new_ctid,'note':tnote.strip()})
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.success("✅ บันทึกทีมสำเร็จ"); st.rerun()
        st.markdown("---")
        if not DB['teams']: st.info("ยังไม่มีทีม")
        for t in DB['teams']:
            ct_name_disp = get_contract_type(t.get('contractTypeId','')).get('name','-') if t.get('contractTypeId') else '-'
            with st.expander(f"**{t['name']}** — {ct_name_disp} — {t.get('note','-')}"):
                e1,e2 = st.columns(2)
                with e1: nn = st.text_input("ชื่อทีม", value=t['name'], key=f"tn_{t['id']}")
                with e2: nnt = st.text_input("หมายเหตุ", value=t.get('note',''), key=f"tnote_{t['id']}")
                e3,_ = st.columns([1,1])
                with e3:
                    nct_sel = st.selectbox("ประเภทการจ้าง", ct_opts,
                                           index=ct_idx(t.get('contractTypeId','')),
                                           key=f"tct_{t['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("💾 บันทึก", key=f"ts_{t['id']}", use_container_width=True):
                        t['name'] = nn; t['note'] = nnt
                        t['contractTypeId'] = ct_ids[ct_names.index(nct_sel)] if nct_sel != "— ไม่ระบุ —" else ''
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.success("บันทึกแล้ว"); st.rerun()
                with b2:
                    if st.button("🗑️ ลบ", key=f"td_{t['id']}", use_container_width=True):
                        DB['teams'] = [x for x in DB['teams'] if x['id']!=t['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("teams")
                        st.rerun()

    # ═══════════════════════════════════════
    # TAB: ประเภทการจ้าง
    # ═════════════════════════════════════════
    with tab_ct:
        with st.expander("➕ เพิ่มประเภทการจ้างใหม่", expanded=(not ct_list)):
            with st.form("add_ct"):
                ct1, ct2 = st.columns(2)
                with ct1: ctn = st.text_input("ชื่อประเภทการจ้าง * (เช่น บริษัท, ผรม)")
                with ct2:
                    cm_opts  = list(CALC_MODES.values())
                    cm_keys  = list(CALC_MODES.keys())
                    ctm_sel  = st.selectbox("วิธีคำนวณ *", cm_opts)
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not ctn.strip(): st.error("กรุณาระบุชื่อประเภทการจ้าง")
                    else:
                        new_cm = cm_keys[cm_opts.index(ctm_sel)]
                        DB.setdefault('contractTypes', []).append(
                            {'id':uid(),'name':ctn.strip(),'calcMode':new_cm})
                        with st.spinner("กำลังบันทึก..."): save_db("contractTypes")
                        st.success("✅ บันทึกสำเร็จ"); st.rerun()
        st.markdown("---")
        if not ct_list:
            st.info("ยังไม่มีประเภทการจ้าง — กด ➕ เพิ่มประเภทการจ้างใหม่")
        for ct in ct_list:
            cm_label = CALC_MODES.get(ct.get('calcMode','unit_rate'), '-')
            with st.expander(f"**{ct['name']}** — {cm_label}"):
                ec1, ec2 = st.columns(2)
                with ec1: nctn = st.text_input("ชื่อ", value=ct['name'], key=f"ctn_{ct['id']}")
                with ec2:
                    cur_cm_idx = cm_keys.index(ct.get('calcMode','unit_rate')) if ct.get('calcMode') in cm_keys else 0
                    nctm_sel   = st.selectbox("วิธีคำนวณ", cm_opts, index=cur_cm_idx, key=f"ctm_{ct['id']}")
                eb1, eb2 = st.columns(2)
                with eb1:
                    if st.button("💾 บันทึก", key=f"cts_{ct['id']}", use_container_width=True):
                        ct['name']     = nctn
                        ct['calcMode'] = cm_keys[cm_opts.index(nctm_sel)]
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
                p3,p4 = st.columns(2)
                with p3: pu = st.text_input("หน่วย * (เช่น ม., kg)")
                with p4: pr = st.number_input("Unit Rate (฿/หน่วย)", min_value=0.0, step=0.01)
                if st.form_submit_button("💾 บันทึก", type="primary"):
                    if not pn.strip() or not pu.strip():
                        st.error("กรุณากรอกข้อมูลให้ครบ")
                    else:
                        DB['projects'].append({'id':uid(),'name':pn.strip(),'unit':pu.strip(),
                                               'unitRate':pr,'description':pd2.strip()})
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.success("✅ บันทึกสำเร็จ"); st.rerun()
        st.markdown("---")
        if not DB['projects']: st.info("ยังไม่มีประเภทงาน")
        for p in DB['projects']:
            with st.expander(f"**{p['name']}** — {p['unit']} — ฿{N(p['unitRate'])}/หน่วย"):
                e1,e2,e3 = st.columns([2,1,1])
                with e1:
                    npn = st.text_input("ชื่องาน", value=p['name'], key=f"pn_{p['id']}")
                    npd = st.text_input("คำอธิบาย", value=p.get('description',''), key=f"pd_{p['id']}")
                with e2: npu = st.text_input("หน่วย", value=p['unit'], key=f"pu_{p['id']}")
                with e3: npr = st.number_input("Unit Rate", value=_f(p['unitRate']),
                                               min_value=0.0, step=0.01, key=f"pr_{p['id']}")
                b1,b2 = st.columns(2)
                with b1:
                    if st.button("💾 บันทึก", key=f"ps_{p['id']}", use_container_width=True):
                        p['name']=npn; p['unit']=npu; p['unitRate']=npr; p['description']=npd
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.success("บันทึกแล้ว"); st.rerun()
                with b2:
                    if st.button("🗑️ ลบ", key=f"pd_{p['id']}", use_container_width=True):
                        DB['projects'] = [x for x in DB['projects'] if x['id']!=p['id']]
                        with st.spinner("กำลังบันทึก..."): save_db("projects")
                        st.rerun()
