import csv,json,os,time,urllib.request,urllib.parse,collections
shard=int(os.environ.get("SHARD","0")); total=int(os.environ.get("SHARDS","12"))
with open("winner_tpex_gap_candidates.csv",encoding="utf-8-sig") as f: rows=list(csv.DictReader(f))
bydate=collections.defaultdict(list)
for r in rows: bydate[r["trade_date"]].append(r)
dates=[d for i,d in enumerate(sorted(bydate)) if i%total==shard]
out=[]
for n,date in enumerate(dates,1):
    url="https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?"+urllib.parse.urlencode({"type":"EW","date":date.replace("-","/"),"response":"json"})
    symbols=None;error=""
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 WINNER-data-audit","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=35) as resp: p=json.load(resp)
            if not isinstance(p,dict) or str(p.get("stat","ok")).lower() not in ("ok",""): raise ValueError("unexpected status")
            tables=p.get("tables")
            if isinstance(tables,list):
                t=next((t for t in tables if isinstance(t,dict) and "代號" in t.get("fields",[]) and t.get("data")),None)
                if not t: raise ValueError("no valid official table")
                fields,values=t["fields"],t["data"]
            else: fields,values=p.get("fields",[]),p.get("data",[])
            if "代號" not in fields or not isinstance(values,list) or len(values)<200: raise ValueError("official schema or row count unexpected")
            ix=fields.index("代號")
            symbols={str(v[ix]).strip() for v in values if isinstance(v,list) and len(v)>ix}
            if len(symbols)<200: raise ValueError("official code count too small")
            break
        except Exception as e:
            error=str(e)[:220];time.sleep(2*(attempt+1))
    for r in bydate[date]:
        status=("OFFICIAL_HAS_ROW_D1_MISSING" if r["symbol"] in symbols else "OFFICIAL_NO_ROW_REASON_UNVERIFIED") if symbols is not None else "OFFICIAL_QUERY_FAILED"
        out.append({"symbol":r["symbol"],"trade_date":date,"status":status,"source":"TPEx afterTrading/otc EW","note":error if symbols is None else ""})
    print(f"shard={shard} {n}/{len(dates)} date={date} official_count={len(symbols) if symbols is not None else 'FAILED'}",flush=True)
    time.sleep(2.5)
os.makedirs("results",exist_ok=True)
with open(f"results/part-{shard:02d}.csv","w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["symbol","trade_date","status","source","note"]);w.writeheader();w.writerows(out)
print("FINISHED",len(out),collections.Counter(r["status"] for r in out))
