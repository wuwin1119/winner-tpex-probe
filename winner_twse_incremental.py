#!/usr/bin/env python3
"""TWSE shares cloud incremental: progress-only handoff, NOT historical restoration or D1 import."""
import argparse, csv, io, json, os, sys, time
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import requests

API = 'https://api.finmindtrade.com/api/v4/data'
BASE = Path('cloud_state')
MANIFEST = BASE / 'twse_manifest.json'
DELTA = BASE / 'twse_delta.tsv'
HEAD = ['date', 'stock_id', 'NumberOfSharesIssued', 'RecentlyDeclareDate']

def run(today, limit, session, delay=0):
    if not MANIFEST.exists():
        raise ValueError('Missing audited manifest; refusing historical redownload')
    state = json.loads(MANIFEST.read_text(encoding='utf-8'))
    stocks = state.get('stocks', [])
    if len(stocks) != 471 or len({s['symbol'] for s in stocks}) != 471:
        raise ValueError('Manifest must have 471 unique symbols')
    token = os.environ.get('FINMIND_TOKEN', '').strip()
    if not token:
        raise ValueError('FINMIND_TOKEN is required; do not commit token to repository')
    # Only store new/overlap API observations. This is NOT a complete historical database.
    existing = {}
    if DELTA.exists():
        with DELTA.open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f, delimiter='\t'):
                existing[(r['stock_id'],r['date'])] = r
    attempted = completed = 0
    errors = []
    for s in sorted(stocks, key=lambda item: (item['checked_through'], item['symbol'])):
        checked = date.fromisoformat(s['checked_through'])
        if checked >= today:
            continue
        if attempted >= limit:
            break
        attempted += 1
        symbol = s['symbol']
        start = max(date(2023,5,23), checked - timedelta(days=7))
        params = dict(dataset='TaiwanStockShareholding',data_id=symbol,start_date=start.isoformat(),end_date=today.isoformat(),token=token)
        try:
            response = session.get(API, params=params, timeout=40)
            if response.status_code in (402,403,429):
                errors.append(f'{symbol}: quota/status {response.status_code}'); break
            response.raise_for_status()
            payload = response.json()
            if payload.get('status') != 200 or not isinstance(payload.get('data'),list):
                raise ValueError(f'API payload rejected: {str(payload)[:120]}')
            incoming = {}
            for item in payload['data']:
                if str(item.get('stock_id')) != symbol:
                    raise ValueError('Unexpected stock code')
                day = date.fromisoformat(str(item['date']))
                if not start <= day <= today:
                    raise ValueError('Out-of-range API date')
                shares = str(item['NumberOfSharesIssued'])
                if not shares.isdigit() or int(shares) <= 0:
                    raise ValueError('Invalid issued shares')
                declared = str(item.get('RecentlyDeclareDate') or '0')
                if declared != '0': date.fromisoformat(declared)
                rec = dict(date=day.isoformat(),stock_id=symbol,NumberOfSharesIssued=shares,RecentlyDeclareDate=declared)
                if day.isoformat() in incoming and incoming[day.isoformat()] != rec:
                    raise ValueError('Conflicting same-day values')
                incoming[day.isoformat()] = rec
            # All validation must finish before changing this symbol's state.
            for d,rec in incoming.items():
                existing[(symbol,d)] = rec
            s['checked_through'] = today.isoformat()
            if incoming:
                s['last_record'] = max(s['last_record'], max(incoming))
            completed += 1
            print(f'PASS {symbol} {len(incoming)} API rows',flush=True)
        except (ValueError, KeyError, requests.RequestException) as exc:
            errors.append(f'{symbol}: {type(exc).__name__}: {exc}')
            print('FAIL',errors[-1],flush=True)
            break  # Stop on first failure to avoid exhausting quota
        if delay: time.sleep(delay)
    if completed:
        BASE.mkdir(exist_ok=True)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=HEAD, delimiter='\t',lineterminator='\n')
        writer.writeheader()
        writer.writerows(existing[k] for k in sorted(existing))
        DELTA.write_text(out.getvalue(),encoding='utf-8')
        MANIFEST.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'attempted':attempted,'completed':completed,'errors':errors,'remaining':sum(date.fromisoformat(s['checked_through'])<today for s in stocks),'delta_records':len(existing)},ensure_ascii=False))
    return 1 if errors else 0

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=10)
    p.add_argument('--delay',type=float,default=1)
    a=p.parse_args()
    if not 1<=a.limit<=471: p.error('--limit must be 1..471')
    sys.exit(run(datetime.now(ZoneInfo('Asia/Taipei')).date(),a.limit,requests.Session(),a.delay))
