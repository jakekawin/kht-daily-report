import streamlit as st
import json, os, calendar
from datetime import date, datetime
import uuid
import pandas as pd

# ────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="KHT Daily Report",
    page_icon="⛑️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────────────────────
# CSS
# ────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] > div:first-child { background-color: #1e3a5f !important; }
  [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,[data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label, [data-testid="stSidebar"] span
  { color: white !important; }
  [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.2) !important; }
  [data-testid="stSidebar"] .stButton button { background:rgba(255,255,255,0.15); color:white; border:1px solid rgba(255,255,255,0.3); }
  [data-testid="stSidebar"] .stDownloadButton button { background:rgba(255,255,255,0.12); color:white; border:1px solid rgba(255,255,255,0.3); width:100%; }

  .m-card { background:white; border-radius:10px; padding:18px 16px;
    box-shadow:0 2px 10px rgba(0,0,0,0.07); border-top:3px solid #e07b2b;
    text-align:center; margin-bottom:8px; }
  .m-val  { font-size:1.6rem; font-weight:700; color:#1e3a5f; line-height:1.1; }
  .m-lbl  { font-size:0.78rem; color:#777; margin-top:4px; }

  .period-hdr { background:#1e3a5f; color:white; padding:12px 18px;
    border-radius:8px 8px 0 0; font-weight:700; }
  .period-body { background:white; border-radius:0 0 8px 8px;
    border:1px solid #dde2ea; border-top:none; }
  .team-row { padding:12px 18px; border-bottom:1px solid #f0f2f5; }
  .team-row:last-child { border-bottom:none; }

  .b-paid   { background:#d4edda; color:#155724; padding:3px 10px;
    border-radius:12px; font-size:0.78rem; font-weight:600; }
  .b-unpaid { background:#f8d7da; color:#721c24; padding:3px 10px;
    border-radius:12px; font-size:0.78rem; font-weight:600; }

  div[data-testid="stMetric"] { background:white; border-radius:10px;
    padding:14px; box-shadow:0 2px 8px rgba(0,0,0,0.07); }
  div[data-testid="stMetric"] label { font-size:0.82rem !important; color:#777 !important; }
  div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size:1.6rem !important; color:#1e3a5f !important; }
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
# DATA LAYER
# ────────────────────────────────────────────────
DATA_FILE = "daily_report_data.json"
TH_MO = ['','มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
          'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
TH_MO_S = ['','ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.',
            'ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            d = json.loads(open(DATA_FILE, 'r', encoding='utf-8').read())
            d.setdefault('payments', [])
            return d
        except:
            pass
    return {"teams": [], "projects": [], "reports": [], "payments": []}

def save_db():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.db, f, ensure_ascii=False, indent=2)

# ─ init session state
if 'db' not in st.session_state:
    st.session_state.db = load_db()
if 'wi' not in st.session_state:   # work items for current form
    st.session_state.wi = []
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None

DB = st.session_state.db

# ────────────────────────────────────────────────
# UTILITIES
# ────────────────────────────────────────────────
def uid():
    return str(uuid.uuid4())[:8]

def N(n):
    return f"{float(n or 0):,.2f}"

def thd(s):
    """Convert YYYY-MM-DD → Thai date string"""
    if not s:
        return '-'
    try:
        y, m, d = s.split('-')
        return f"{int(d)} {TH_MO_S[int(m)]} {int(y)+543}"
    except:
        return s

def pdates(yr, mo, p):
    """Return (start_str, end_str) for the given period."""
    m = str(mo).zfill(2)
    if p == 1:
        return f"{yr}-{m}-01", f"{yr}-{m}-15"
    last = calendar.monthrange(yr, mo)[1]
    return f"{yr}-{m}-16", f"{yr}-{m}-{str(last).zfill(2)}"

def get_team(tid):
    return next((x for x in DB['teams'] if x['id'] == tid), {'name': '?', 'note': ''})

def get_proj(pid):
    return next((x for x in DB['projects'] if x['id'] == pid),
                {'name': '?', 'unit': '', 'unitRate': 0})

def period_total(tid, yr, mo, p):
    s, e = pdates(yr, mo, p)
    return sum(r['total'] for r in DB['reports']
               if r['teamId'] == tid and s <= r['date'] <= e)

def get_payment(tid, yr, mo, p):
    return next((x for x in DB['payments']
                 if x['tid'] == tid and x['y'] == yr and x['mo'] == mo and x['p'] == p), None)

def today_str():
    return date.today().isoformat()

# ────────────────────────────────────────────────
# SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:4px 0 14px 0">
      <div style="font-size:1.25rem;font-weight:700">⛑️ KHT Daily Report</div>
      <div style="font-size:0.78rem;color:#e07b2b">ระบบบันทึกผลงานผู้รับเหมา</div>
    </div>
    """, unsafe_allow_html=True)

    PAGES = {
        "📊 Dashboard": "dashboard",
        "➕ บันทึกงานประจำวัน": "add",
        "🔍 ดูข้อมูลรายวัน": "view",
        "📈 สรุปรายงวด": "summary",
        "⚙️ ตั้งค่าระบบ": "settings",
    }
    page_label = st.radio("เมนู", list(PAGES.keys()), label_visibility="collapsed")
    PAGE = PAGES[page_label]

    st.markdown("---")

    # Export
    export_bytes = json.dumps(DB, ensure_ascii=False, indent=2).encode('utf-8')
    st.download_button(
        "📥 Export ข้อมูล (JSON)",
        data=export_bytes,
        file_name=f"kht-report-{today_str()}.json",
        mime="application/json",
        use_container_width=True,
    )

    # Import
    uploaded = st.file_uploader("📤 Import JSON", type=["json"], label_visibility="collapsed")
    if uploaded:
        try:
            imp = json.load(uploaded)
            if 'teams' in imp and 'reports' in imp:
                if st.button("✅ ยืนยัน Import", use_container_width=True):
                    imp.setdefault('payments', [])
                    st.session_state.db = imp
                    save_db()
                    st.rerun()
            else:
                st.error("ไฟล์ไม่ถูกต้อง")
        except:
            st.error("ไม่สามารถอ่านไฟล์ได้")

# ════════════════════════════════════════════════
# PAGE: DASHBOARD
# ════════════════════════════════════════════════
if PAGE == "dashboard":
    now = date.today()
    yr, mo, dy = now.year, now.month, now.day
    p_cur = 1 if dy <= 15 else 2
    ps, pe = pdates(yr, mo, p_cur)
    ms = f"{yr}-{str(mo).zfill(2)}-01"
    me = f"{yr}-{str(mo).zfill(2)}-31"
    today = today_str()

    period_lbl = f"งวดที่ {p_cur}: {'1-15' if p_cur==1 else '16-สิ้นเดือน'} {TH_MO[mo]} {yr+543}"
    st.markdown(f"### 📊 Dashboard &nbsp; <span style='font-size:0.85rem;color:#777'>{period_lbl}</span>",
                unsafe_allow_html=True)

    today_rpts = [r for r in DB['reports'] if r['date'] == today]
    period_rpts = [r for r in DB['reports'] if ps <= r['date'] <= pe]
    month_rpts = [r for r in DB['reports'] if ms <= r['date'] <= me]
    today_tot = sum(r['total'] for r in today_rpts)
    period_tot = sum(r['total'] for r in period_rpts)
    month_tot = sum(r['total'] for r in month_rpts)

    # Unpaid amount
    unpaid = 0
    for t in DB['teams']:
        for p in [1, 2]:
            tot = period_total(t['id'], yr, mo, p)
            pay = get_payment(t['id'], yr, mo, p)
            if tot > 0 and (not pay or not pay.get('paid')):
                unpaid += tot

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📅 ยอดวันนี้", f"฿ {N(today_tot)}")
    with c2:
        st.metric("📆 ยอดงวดนี้", f"฿ {N(period_tot)}")
    with c3:
        st.metric("🗓️ ยอดเดือนนี้", f"฿ {N(month_tot)}")
    with c4:
        st.metric("⚠️ ค้างชำระ", f"฿ {N(unpaid)}")

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("👥 จำนวนทีม", len(DB['teams']))
    with col_b:
        st.metric("🔧 ประเภทงาน", len(DB['projects']))

    st.markdown("---")
    st.markdown("#### 📋 ผลงานวันนี้")
    if not today_rpts:
        st.info("ยังไม่มีข้อมูลวันนี้")
    else:
        rows = []
        for r in today_rpts:
            items_str = " | ".join(
                f"{get_proj(it['pid'])['name']}: {it['qty']} {it['unit']} = {N(it['amt'])} ฿"
                for it in r['items']
            )
            rows.append({
                "ทีม": get_team(r['teamId'])['name'],
                "คนงาน": r['workers'],
                "รายการงาน": items_str,
                "รวม (฿)": N(r['total']),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════
# PAGE: ADD / EDIT REPORT
# ════════════════════════════════════════════════
elif PAGE == "add":
    st.markdown("### ➕ บันทึกงานประจำวัน")

    edit_rec = None
    if st.session_state.edit_id:
        edit_rec = next((r for r in DB['reports'] if r['id'] == st.session_state.edit_id), None)
        if edit_rec and st.session_state.wi == []:
            st.session_state.wi = [dict(i) for i in edit_rec['items']]

    col1, col2, col3 = st.columns([1.5, 1.5, 1])
    with col1:
        default_date = datetime.strptime(edit_rec['date'], '%Y-%m-%d').date() if edit_rec else date.today()
        r_date = st.date_input("📅 วันที่ *", value=default_date)
    with col2:
        team_names = [t['name'] for t in DB['teams']]
        team_ids   = [t['id']   for t in DB['teams']]
        if not team_names:
            st.warning("ยังไม่มีทีม — ไปที่ตั้งค่าระบบเพื่อเพิ่มทีมก่อน")
            st.stop()
        default_ti = team_ids.index(edit_rec['teamId']) if edit_rec and edit_rec['teamId'] in team_ids else 0
        r_team_name = st.selectbox("👥 ทีมผู้รับเหมา *", team_names, index=default_ti)
        r_team_id = team_ids[team_names.index(r_team_name)]
    with col3:
        r_workers = st.number_input("🧑‍🔧 จำนวนคนงาน *", min_value=0,
                                    value=int(edit_rec['workers']) if edit_rec else 0)

    r_note = st.text_input("📝 หมายเหตุ", value=edit_rec.get('note','') if edit_rec else '')

    st.markdown("---")
    st.markdown("**📋 รายการงาน**")

    if not DB['projects']:
        st.warning("ยังไม่มีประเภทงาน — ไปที่ตั้งค่าระบบเพื่อเพิ่มประเภทงานก่อน")
    else:
        proj_names = [p['name'] for p in DB['projects']]
        proj_ids   = [p['id']   for p in DB['projects']]

        # Dynamic work items
        to_remove = None
        for idx, item in enumerate(st.session_state.wi):
            ic1, ic2, ic3, ic4, ic5 = st.columns([2.5, 1, 1, 1.2, 0.5])
            with ic1:
                cur_pi = proj_ids.index(item['pid']) if item.get('pid') in proj_ids else 0
                sel_name = st.selectbox(f"งาน#{idx+1}", proj_names, index=cur_pi,
                                        key=f"psel_{idx}", label_visibility="collapsed")
                sel_proj = DB['projects'][proj_names.index(sel_name)]
                item['pid']  = sel_proj['id']
                item['unit'] = sel_proj['unit']
                item['rate'] = sel_proj['unitRate']
            with ic2:
                st.text_input("หน่วย", value=item['unit'], disabled=True,
                              key=f"unit_{idx}", label_visibility="collapsed")
            with ic3:
                st.text_input("Rate", value=N(item['rate']), disabled=True,
                              key=f"rate_{idx}", label_visibility="collapsed")
            with ic4:
                item['qty'] = st.number_input("ปริมาณ", min_value=0.0,
                                              value=float(item.get('qty', 0)),
                                              step=0.01, key=f"qty_{idx}",
                                              label_visibility="collapsed")
                item['amt'] = item['qty'] * item['rate']
            with ic5:
                if st.button("🗑️", key=f"del_{idx}"):
                    to_remove = idx

        if to_remove is not None:
            st.session_state.wi.pop(to_remove)
            st.rerun()

        ca, cb = st.columns([1, 5])
        with ca:
            if st.button("➕ เพิ่มรายการงาน"):
                first_proj = DB['projects'][0]
                st.session_state.wi.append({
                    'id': uid(), 'pid': first_proj['id'],
                    'unit': first_proj['unit'], 'rate': first_proj['unitRate'],
                    'qty': 0, 'amt': 0
                })
                st.rerun()

        if st.session_state.wi:
            grand = sum(w['amt'] for w in st.session_state.wi)
            st.markdown(f"**รวมทั้งหมด: <span style='color:#e07b2b;font-size:1.1rem'>฿ {N(grand)}</span>**",
                        unsafe_allow_html=True)

        st.markdown("---")
        s1, s2, s3 = st.columns([1.2, 1, 5])
        with s1:
            save_btn = st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True)
        with s2:
            if st.button("🗑️ ล้างข้อมูล", use_container_width=True):
                st.session_state.wi = []
                st.session_state.edit_id = None
                st.rerun()

        if save_btn:
            if not st.session_state.wi:
                st.error("กรุณาเพิ่มรายการงานอย่างน้อย 1 รายการ")
            elif any(w['qty'] <= 0 for w in st.session_state.wi):
                st.error("กรุณาระบุปริมาณงานให้ครบทุกรายการ")
            else:
                total = sum(w['amt'] for w in st.session_state.wi)
                rec = {
                    'id': st.session_state.edit_id or uid(),
                    'date': r_date.isoformat(),
                    'teamId': r_team_id,
                    'workers': int(r_workers),
                    'note': r_note,
                    'items': [dict(w) for w in st.session_state.wi],
                    'total': total,
                }
                if st.session_state.edit_id:
                    idx = next((i for i,r in enumerate(DB['reports']) if r['id']==rec['id']), None)
                    if idx is not None:
                        DB['reports'][idx] = rec
                    st.success("✅ แก้ไขข้อมูลสำเร็จ")
                else:
                    DB['reports'].append(rec)
                    st.success("✅ บันทึกข้อมูลสำเร็จ")
                save_db()
                st.session_state.wi = []
                st.session_state.edit_id = None
                st.rerun()

# ════════════════════════════════════════════════
# PAGE: VIEW REPORTS
# ════════════════════════════════════════════════
elif PAGE == "view":
    st.markdown("### 🔍 ดูข้อมูลรายวัน")

    fc1, fc2, fc3 = st.columns([1.5, 1, 1])
    with fc1:
        filter_type = st.selectbox("ประเภทการค้นหา",
                                   ["ทั้งหมด", "ระบุวันที่", "ช่วงวันที่"])
    with fc2:
        team_opts = ["ทุกทีม"] + [t['name'] for t in DB['teams']]
        f_team = st.selectbox("ทีม", team_opts)
    with fc3:
        sort_dir = st.selectbox("เรียงตาม", ["วันที่ล่าสุด", "วันที่เก่าสุด"])

    f_date, f_start, f_end = None, None, None
    if filter_type == "ระบุวันที่":
        f_date = st.date_input("วันที่", value=date.today())
    elif filter_type == "ช่วงวันที่":
        dc1, dc2 = st.columns(2)
        with dc1: f_start = st.date_input("จากวันที่")
        with dc2: f_end   = st.date_input("ถึงวันที่")

    rpts = list(DB['reports'])
    if f_team != "ทุกทีม":
        tid = next(t['id'] for t in DB['teams'] if t['name'] == f_team)
        rpts = [r for r in rpts if r['teamId'] == tid]
    if filter_type == "ระบุวันที่" and f_date:
        rpts = [r for r in rpts if r['date'] == f_date.isoformat()]
    elif filter_type == "ช่วงวันที่":
        if f_start: rpts = [r for r in rpts if r['date'] >= f_start.isoformat()]
        if f_end:   rpts = [r for r in rpts if r['date'] <= f_end.isoformat()]

    rpts.sort(key=lambda r: r['date'], reverse=(sort_dir == "วันที่ล่าสุด"))

    total = sum(r['total'] for r in rpts)
    st.markdown(f"พบ **{len(rpts)}** รายการ &nbsp;|&nbsp; รวม **฿ {N(total)}**",
                unsafe_allow_html=True)
    st.markdown("---")

    if not rpts:
        st.info("ไม่พบข้อมูล")
    else:
        for r in rpts:
            team_name = get_team(r['teamId'])['name']
            with st.expander(f"📅 {thd(r['date'])}  —  {team_name}  —  ฿ {N(r['total'])}"):
                dc1, dc2 = st.columns([3, 1])
                with dc1:
                    item_rows = []
                    for it in r['items']:
                        p = get_proj(it['pid'])
                        item_rows.append({
                            "งาน": p['name'],
                            "หน่วย": it['unit'],
                            "Rate (฿)": N(it['rate']),
                            "ปริมาณ": it['qty'],
                            "จำนวนเงิน (฿)": N(it['amt']),
                        })
                    st.dataframe(pd.DataFrame(item_rows), hide_index=True, use_container_width=True)
                    if r.get('note'):
                        st.caption(f"📝 {r['note']}")
                with dc2:
                    st.metric("คนงาน", r['workers'])
                    st.metric("รวม (฿)", N(r['total']))
                    eb1, eb2 = st.columns(2)
                    with eb1:
                        if st.button("✏️ แก้ไข", key=f"ed_{r['id']}"):
                            st.session_state.edit_id = r['id']
                            st.session_state.wi = []
                            st.rerun()
                    with eb2:
                        if st.button("🗑️ ลบ", key=f"dl_{r['id']}"):
                            DB['reports'] = [x for x in DB['reports'] if x['id'] != r['id']]
                            save_db()
                            st.rerun()

# ════════════════════════════════════════════════
# PAGE: PERIOD SUMMARY
# ════════════════════════════════════════════════
elif PAGE == "summary":
    st.markdown("### 📈 สรุปรายงวด")

    sc1, sc2 = st.columns([1, 1])
    with sc1:
        sel_year  = st.number_input("ปี (ค.ศ.)", min_value=2020, max_value=2035,
                                    value=date.today().year)
    with sc2:
        sel_month = st.selectbox("เดือน", list(range(1, 13)),
                                 index=date.today().month - 1,
                                 format_func=lambda m: TH_MO[m])

    yr, mo = int(sel_year), int(sel_month)

    def render_period(period: int):
        s, e = pdates(yr, mo, period)
        end_day = 15 if period == 1 else calendar.monthrange(yr, mo)[1]
        start_day = 1 if period == 1 else 16

        period_tot, paid_tot = 0, 0
        rows_data = []
        for t in DB['teams']:
            tot  = period_total(t['id'], yr, mo, period)
            rpts = [r for r in DB['reports'] if r['teamId']==t['id'] and s<=r['date']<=e]
            pay  = get_payment(t['id'], yr, mo, period)
            is_paid = pay and pay.get('paid')
            period_tot += tot
            if is_paid:
                paid_tot += tot
            rows_data.append((t, tot, rpts, pay, is_paid))

        unpaid_tot = period_tot - paid_tot
        st.markdown(
            f"<div class='period-hdr'>งวดที่ {period}: {start_day}–{end_day} {TH_MO[mo]} {yr+543} &nbsp;|&nbsp; "
            f"รวม ฿ {N(period_tot)} &nbsp;|&nbsp; "
            f"<span style='color:#a8d8a8'>จ่ายแล้ว ฿ {N(paid_tot)}</span> &nbsp; "
            f"<span style='color:#f8a9a9'>ค้าง ฿ {N(unpaid_tot)}</span></div>",
            unsafe_allow_html=True,
        )

        if not DB['teams']:
            st.info("ยังไม่มีทีม")
            return

        for t, tot, rpts, pay, is_paid in rows_data:
            days = len(rpts)
            mandays = sum(r['workers'] for r in rpts)

            rc1, rc2, rc3 = st.columns([3, 1.5, 1.5])
            with rc1:
                st.markdown(f"**{t['name']}**")
                st.caption(f"{days} วันทำงาน | {mandays} คน-วัน")
                if is_paid:
                    st.caption(f"✅ จ่ายวันที่ {thd(pay.get('paidDate'))} {pay.get('note','')}")
            with rc2:
                st.metric("", f"฿ {N(tot)}")
            with rc3:
                if is_paid:
                    st.markdown(f"<div class='b-paid'>✓ จ่ายแล้ว</div>", unsafe_allow_html=True)
                    if tot > 0 and st.button("ยกเลิก", key=f"un_{t['id']}_{period}", use_container_width=True):
                        idx = next((i for i,px in enumerate(DB['payments'])
                                    if px['tid']==t['id'] and px['y']==yr and px['mo']==mo and px['p']==period), None)
                        if idx is not None:
                            DB['payments'][idx]['paid'] = False
                            DB['payments'][idx]['paidDate'] = None
                        save_db()
                        st.rerun()
                else:
                    if tot > 0:
                        st.markdown(f"<div class='b-unpaid'>ยังไม่ได้จ่าย</div>", unsafe_allow_html=True)
                        if st.button("💰 จ่ายแล้ว", key=f"pk_{t['id']}_{period}", use_container_width=True):
                            st.session_state[f"mark_{t['id']}_{period}"] = True
                            st.rerun()
                    else:
                        st.caption("ไม่มีงาน")

            # Payment date input popup
            state_key = f"mark_{t['id']}_{period}"
            if st.session_state.get(state_key):
                with st.form(key=f"pf_{t['id']}_{period}"):
                    paid_date = st.date_input("วันที่จ่ายเงิน", value=date.today(),
                                              key=f"pd_{t['id']}_{period}")
                    paid_note = st.text_input("หมายเหตุ", key=f"pn_{t['id']}_{period}")
                    if st.form_submit_button("✅ ยืนยัน"):
                        rec = {'id': uid(), 'tid': t['id'], 'y': yr, 'mo': mo, 'p': period,
                               'paid': True, 'paidDate': paid_date.isoformat(), 'note': paid_note}
                        idx = next((i for i,px in enumerate(DB['payments'])
                                    if px['tid']==t['id'] and px['y']==yr and px['mo']==mo and px['p']==period), None)
                        if idx is not None: DB['payments'][idx] = rec
                        else: DB['payments'].append(rec)
                        save_db()
                        st.session_state[state_key] = False
                        st.rerun()

            st.markdown("<hr style='margin:6px 0;border-color:#f0f2f5'>", unsafe_allow_html=True)

    render_period(1)
    st.markdown("---")
    render_period(2)

    # Cumulative table
    st.markdown("---")
    st.markdown(f"#### 📊 สรุปรวม {TH_MO[mo]} {yr+543}")
    cum_rows = []
    m_str = str(mo).zfill(2)
    for t in DB['teams']:
        rpts = [r for r in DB['reports'] if r['teamId']==t['id']
                and r['date'].startswith(f"{yr}-{m_str}")]
        tot = sum(r['total'] for r in rpts)
        pd_tot = 0
        for p in [1, 2]:
            pay = get_payment(t['id'], yr, mo, p)
            if pay and pay.get('paid'):
                s, e = pdates(yr, mo, p)
                pd_tot += sum(r['total'] for r in DB['reports']
                              if r['teamId']==t['id'] and s<=r['date']<=e)
        cum_rows.append({
            "ทีม": t['name'],
            "ยอดรวม (฿)": N(tot),
            "จ่ายแล้ว (฿)": N(pd_tot),
            "ค้างชำระ (฿)": N(tot - pd_tot),
        })
    if cum_rows:
        grand_tot = sum(float(r["ยอดรวม (฿)"].replace(',','')) for r in cum_rows)
        grand_paid = sum(float(r["จ่ายแล้ว (฿)"].replace(',','')) for r in cum_rows)
        cum_rows.append({
            "ทีม": "รวมทั้งหมด",
            "ยอดรวม (฿)": N(grand_tot),
            "จ่ายแล้ว (฿)": N(grand_paid),
            "ค้างชำระ (฿)": N(grand_tot - grand_paid),
        })
        st.dataframe(pd.DataFrame(cum_rows), hide_index=True, use_container_width=True)
    else:
        st.info("ไม่มีข้อมูลเดือนนี้")

# ════════════════════════════════════════════════
# PAGE: SETTINGS
# ════════════════════════════════════════════════
elif PAGE == "settings":
    st.markdown("### ⚙️ ตั้งค่าระบบ")

    tab_teams, tab_projs = st.tabs(["👥 ทีมผู้รับเหมา", "🔧 ประเภทงาน / Unit Rate"])

    # ─── TEAMS ───────────────────────────────────
    with tab_teams:
        with st.expander("➕ เพิ่มทีมใหม่", expanded=(not DB['teams'])):
            with st.form("add_team_form"):
                tn1, tn2 = st.columns(2)
                with tn1: new_team_name = st.text_input("ชื่อทีม *")
                with tn2: new_team_note = st.text_input("หมายเหตุ / ชื่อผู้รับเหมา")
                if st.form_submit_button("💾 บันทึกทีม", type="primary"):
                    if not new_team_name.strip():
                        st.error("กรุณาระบุชื่อทีม")
                    else:
                        DB['teams'].append({'id': uid(), 'name': new_team_name.strip(),
                                            'note': new_team_note.strip()})
                        save_db()
                        st.success("✅ บันทึกทีมสำเร็จ")
                        st.rerun()

        st.markdown("---")
        if not DB['teams']:
            st.info("ยังไม่มีทีม")
        for t in DB['teams']:
            with st.expander(f"**{t['name']}** — {t.get('note','-')}"):
                ef1, ef2 = st.columns(2)
                with ef1:
                    new_name = st.text_input("ชื่อทีม", value=t['name'], key=f"tn_{t['id']}")
                with ef2:
                    new_note = st.text_input("หมายเหตุ", value=t.get('note',''), key=f"tnote_{t['id']}")
                ea, eb = st.columns(2)
                with ea:
                    if st.button("💾 บันทึก", key=f"tsave_{t['id']}", use_container_width=True):
                        t['name'] = new_name; t['note'] = new_note
                        save_db()
                        st.success("บันทึกแล้ว")
                        st.rerun()
                with eb:
                    if st.button("🗑️ ลบทีม", key=f"tdel_{t['id']}", use_container_width=True):
                        DB['teams'] = [x for x in DB['teams'] if x['id'] != t['id']]
                        save_db()
                        st.rerun()

    # ─── PROJECTS ────────────────────────────────
    with tab_projs:
        with st.expander("➕ เพิ่มประเภทงานใหม่", expanded=(not DB['projects'])):
            with st.form("add_proj_form"):
                pa, pb = st.columns(2)
                with pa: new_pname = st.text_input("ชื่องาน / โปรเจค *")
                with pb: new_pdesc = st.text_input("คำอธิบาย")
                pc, pd_ = st.columns(2)
                with pc: new_punit = st.text_input("หน่วย *  (เช่น ม., kg, ม.2)")
                with pd_: new_prate = st.number_input("Unit Rate (฿/หน่วย) *", min_value=0.0, step=0.01)
                if st.form_submit_button("💾 บันทึกงาน", type="primary"):
                    if not new_pname.strip() or not new_punit.strip() or not new_prate:
                        st.error("กรุณากรอกข้อมูลให้ครบ")
                    else:
                        DB['projects'].append({
                            'id': uid(), 'name': new_pname.strip(),
                            'unit': new_punit.strip(), 'unitRate': new_prate,
                            'description': new_pdesc.strip()
                        })
                        save_db()
                        st.success("✅ บันทึกงานสำเร็จ")
                        st.rerun()

        st.markdown("---")
        if not DB['projects']:
            st.info("ยังไม่มีประเภทงาน")
        for p in DB['projects']:
            with st.expander(f"**{p['name']}** — {p['unit']} — ฿ {N(p['unitRate'])}/หน่วย"):
                pea, peb, pec = st.columns([2, 1, 1])
                with pea:
                    new_pn = st.text_input("ชื่องาน", value=p['name'], key=f"pn_{p['id']}")
                    new_pd = st.text_input("คำอธิบาย", value=p.get('description',''), key=f"pd_{p['id']}")
                with peb:
                    new_pu = st.text_input("หน่วย", value=p['unit'], key=f"pu_{p['id']}")
                with pec:
                    new_pr = st.number_input("Unit Rate", value=float(p['unitRate']),
                                            min_value=0.0, step=0.01, key=f"pr_{p['id']}")
                pb1, pb2 = st.columns(2)
                with pb1:
                    if st.button("💾 บันทึก", key=f"psave_{p['id']}", use_container_width=True):
                        p['name'] = new_pn; p['unit'] = new_pu
                        p['unitRate'] = new_pr; p['description'] = new_pd
                        save_db()
                        st.success("บันทึกแล้ว")
                        st.rerun()
                with pb2:
                    if st.button("🗑️ ลบ", key=f"pdel_{p['id']}", use_container_width=True):
                        DB['projects'] = [x for x in DB['projects'] if x['id'] != p['id']]
                        save_db()
                        st.rerun()
