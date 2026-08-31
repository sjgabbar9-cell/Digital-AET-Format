import base64, calendar, io
from datetime import date, datetime
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="AET QPDC Board",page_icon="📊",layout="wide")
AETS=["Slip House and Spray Dryer","Press","Glazeline and Glaze Preparation","Kiln","Polishing"]
CATS=["Q","P","D","C"]; NAMES={"Q":"Quality","P":"Productivity","D":"Delivery","C":"Cost"}

def headers(): return {"Authorization":f"Bearer {st.secrets['GITHUB_TOKEN']}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
def url(path): return f"https://api.github.com/repos/{st.secrets['GITHUB_OWNER']}/{st.secrets['GITHUB_REPO']}/contents/{path}"
def read_csv(path):
 r=requests.get(url(path),headers=headers(),params={"ref":st.secrets.get("GITHUB_BRANCH","main")},timeout=30); r.raise_for_status(); j=r.json()
 return pd.read_csv(io.BytesIO(base64.b64decode(j["content"]))),j["sha"]
def write_csv(path,df,sha,message):
 content=base64.b64encode(df.to_csv(index=False).encode()).decode(); payload={"message":message,"content":content,"sha":sha,"branch":st.secrets.get("GITHUB_BRANCH","main")}
 r=requests.put(url(path),headers=headers(),json=payload,timeout=30); r.raise_for_status()
def admin(): return st.session_state.get("admin",False)
def met(v,t,d): return float(v)>=float(t) if d=="Higher is better" else float(v)<=float(t)
def dot(day,status):
 c="#9ca3af" if status is None else ("#16a34a" if status else "#dc2626")
 return f'<div style="width:42px;height:42px;border-radius:50%;background:{c};color:white;display:flex;align-items:center;justify-content:center;font-weight:700;margin:auto">{day}</div>'
def upsert(df,keys,row):
 mask=pd.Series(True,index=df.index)
 for k in keys: mask &= df[k].astype(str).eq(str(row[k]))
 if mask.any():
  for k,v in row.items(): df.loc[mask,k]=v
 else: df=pd.concat([df,pd.DataFrame([row])],ignore_index=True)
 return df

st.title("AET QPDC Daily Performance Board"); st.caption("Project: PARIVARTAN | Green = target met | Red = target missed | Grey = no data")
with st.sidebar:
 with st.expander("Administrator login"):
  pwd=st.text_input("Password",type="password")
  if st.button("Login"):
   if pwd==st.secrets["ADMIN_PASSWORD"]: st.session_state.admin=True; st.rerun()
   else: st.error("Incorrect password")
  if admin() and st.button("Logout"): st.session_state.admin=False; st.rerun()
 aet=st.selectbox("AET",AETS); now=date.today(); year=int(st.number_input("Year",2024,2100,now.year)); month=st.selectbox("Month",range(1,13),index=now.month-1,format_func=lambda x:calendar.month_name[x])
try: targets,tsha=read_csv("data/targets.csv"); daily,dsha=read_csv("data/daily_entries.csv")
except Exception as e: st.error(f"GitHub data error: {e}"); st.stop()
t=targets[(targets.AET==aet)&(pd.to_numeric(targets.Year)==year)&(pd.to_numeric(targets.Month)==month)]
daily["Date"]=pd.to_datetime(daily["Date"],errors="coerce"); d=daily[(daily.AET==aet)&(daily.Date.dt.year==year)&(daily.Date.dt.month==month)]
board,entry,target,report=st.tabs(["QPDC Board","Daily Entry","Target Setup","Download Data"])
with board:
 tm={r.Category:r for _,r in t.iterrows()}; dm={(r.Date.day,r.Category):r["Actual Value"] for _,r in d.iterrows()}
 for cat in CATS:
  x=tm.get(cat); label=NAMES[cat] if x is None else f"{x['KPI Name']} | Target {x.Target} {x.UOM} | {x.Direction}"
  st.markdown(f"### {cat} - {label}"); cols=st.columns(8)
  for day in range(1,calendar.monthrange(year,month)[1]+1):
   v=dm.get((day,cat)); status=None if x is None or v is None else met(v,x.Target,x.Direction)
   with cols[(day-1)%8]: st.markdown(dot(day,status),unsafe_allow_html=True); st.caption("" if v is None else str(v))
with entry:
 if not admin(): st.info("Administrator login required.")
 elif t.empty: st.warning("Set targets first.")
 else:
  dt=st.date_input("Performance date",value=date(year,month,min(now.day,calendar.monthrange(year,month)[1]))); user=st.text_input("Updated by")
  tm={r.Category:r for _,r in t.iterrows()}
  with st.form("entry"):
   vals={c:st.number_input(f"{c} - {tm[c]['KPI Name']} ({tm[c].UOM})",value=0.0) for c in CATS}
   if st.form_submit_button("Save daily data"):
    latest,sha=read_csv("data/daily_entries.csv"); ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for c,v in vals.items(): latest=upsert(latest,["AET","Date","Category"],{"AET":aet,"Date":str(dt),"Category":c,"Actual Value":v,"Updated By":user,"Updated At":ts})
    write_csv("data/daily_entries.csv",latest,sha,f"Update {aet} QPDC for {dt}"); st.success("Saved to GitHub."); st.rerun()
with target:
 if not admin(): st.info("Administrator login required.")
 else:
  old={r.Category:r for _,r in t.iterrows()}; user=st.text_input("Updated by",key="tu")
  with st.form("targets"):
   rows=[]
   for c in CATS:
    x=old.get(c,{}); st.markdown(f"**{c} - {NAMES[c]}**"); a,b,k,e=st.columns(4)
    name=a.text_input("KPI Name",x.get("KPI Name",NAMES[c]),key="n"+c); uom=b.text_input("UOM",x.get("UOM","%"),key="u"+c); val=k.number_input("Target",value=float(x.get("Target",0)),key="v"+c); direction=e.selectbox("Direction",["Higher is better","Lower is better"],index=0 if x.get("Direction","Lower is better")=="Higher is better" else 1,key="d"+c)
    rows.append({"AET":aet,"Year":year,"Month":month,"Category":c,"KPI Name":name,"UOM":uom,"Target":val,"Direction":direction})
   if st.form_submit_button("Save targets"):
    latest,sha=read_csv("data/targets.csv"); ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in rows: r.update({"Updated By":user,"Updated At":ts}); latest=upsert(latest,["AET","Year","Month","Category"],r)
    write_csv("data/targets.csv",latest,sha,f"Update {aet} targets {year}-{month:02d}"); st.success("Saved to GitHub."); st.rerun()
with report:
 st.dataframe(d,use_container_width=True,hide_index=True); st.download_button("Download CSV",d.to_csv(index=False).encode(),f"{aet}_{year}_{month}.csv","text/csv")
