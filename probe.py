import csv,io,json,sys,urllib.parse,urllib.request
from datetime import date
DAY=date.fromisoformat(sys.argv[1] if len(sys.argv)>1 else '2026-11-09')
url='https://www.tpex.org.tw/www/zh-tw/afterTrading/turnover?'+urllib.parse.urlencode({'type':'Daily','date':DAY.strftime('%Y/%m/%d'),'response':'csv'})
print('REQUEST',url,flush=True)
req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'*/*'})
try:
 with urllib.request.urlopen(req,timeout=35) as r:
  body=r.read(); print('HTTP',r.status,'BYTES',len(body),'TYPE',r.headers.get('Content-Type'),flush=True)
 text=body.decode('cp950'); rows=list(csv.reader(io.StringIO(text)))
 assert len(rows)>3 and '週轉率' in rows[0][0], 'report title mismatch'
 roc=f'{DAY.year-1911}/{DAY.month:02d}/{DAY.day:02d}'
 assert roc in ''.join(rows[1]), 'date mismatch'
 assert '股票代號' in rows[2][1] and '發行股數' in rows[2][4], 'header mismatch'
 stocks=[r for r in rows[3:] if len(r)==6 and r[0].strip().isdigit() and r[1].strip()]
 assert len(stocks)>100, 'too few stocks'
 for r in stocks:
  assert r[3].replace(',','').strip().isdigit() and r[4].replace(',','').strip().isdigit()
  float(r[5])
 print('PASS',json.dumps({'date':DAY.isoformat(),'count':len(stocks),'first_symbol':stocks[0][1],'last_symbol':stocks[-1][1]},ensure_ascii=False),flush=True)
except Exception as e:
 print('FAIL',type(e).__name__,str(e),flush=True)
 sys.exit(1)
