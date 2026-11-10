#!/usr/bin/env python3
"""Download and validate official TPEx turnover CSV, without touching D1."""
import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

API = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/turnover'
HEADER = ['日期', '股票代號', '股票名稱', '總成交股數', '發行股數', '周轉率(%)']


def fetch(day):
    url = API + '?' + urllib.parse.urlencode({'type': 'Daily', 'date': day.strftime('%Y/%m/%d'), 'response': 'csv'})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}')
        raw = response.read()
    text = raw.decode('cp950')
    if '<html' in text.lower() or '<!doctype' in text.lower():
        raise ValueError('HTML instead of CSV')
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3 or not rows[0] or '週轉率' not in rows[0][0]:
        raise ValueError('Invalid report title')
    roc = f'{day.year - 1911}/{day.month:02d}/{day.day:02d}'
    if roc not in ''.join(rows[1]):
        raise ValueError('Report date mismatch')
    if len(rows[2]) < 6 or '股票代號' not in rows[2][1] or '發行股數' not in rows[2][4]:
        raise ValueError('Invalid report columns')
    stocks = []
    for row in rows[3:]:
        if len(row) == 6 and row[0].strip().isdigit() and row[1].strip():
            code = row[1].strip()
            vol, issued = row[3].replace(',', '').strip(), row[4].replace(',', '').strip()
            if not vol.isdigit() or not issued.isdigit():
                raise ValueError(f'Invalid shares: {code}')
            turnover = row[5].strip()
            value = float(turnover)
            if not (0 <= value <= 100):
                raise ValueError(f'Invalid turnover: {code}')
            stocks.append([day.isoformat(), code, row[2].strip(), vol, issued, turnover])
    if not stocks:
        return None
    if len(stocks) < 100:
        raise ValueError(f'Too few stocks: {len(stocks)}')
    if len({r[1] for r in stocks}) != len(stocks):
        raise ValueError('Duplicate stock codes')
    return stocks


def save(day, stocks, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{day:%Y%m%d}.txt'
    tmp = target.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as out:
        writer = csv.writer(out, delimiter='\t', lineterminator='\n')
        writer.writerow(HEADER)
        writer.writerows(stocks)
    tmp.replace(target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='One YYYY-MM-DD date, for a probe')
    parser.add_argument('--days', type=int, default=10, help='Calendar-day lookback')
    parser.add_argument('--out', default='tpex-turnover')
    args = parser.parse_args(argv)
    if not 1 <= args.days <= 31:
        parser.error('--days must be 1..31')
    today = datetime.now(ZoneInfo('Asia/Taipei')).date()
    dates = [date.fromisoformat(args.date)] if args.date else [today - timedelta(days=n) for n in range(args.days, 0, -1)]
    folder = Path(args.out)
    success, empty, failed, skipped = [], [], [], []
    for day in dates:
        if day.weekday() >= 5:
            skipped.append(day.isoformat())
            continue
        for attempt in range(3):
            try:
                stocks = fetch(day)
                if stocks is None:
                    empty.append(day.isoformat())
                    print(f'NO_DATA {day} (verify holiday / publication)', flush=True)
                else:
                    save(day, stocks, folder)
                    success.append({'date': day.isoformat(), 'count': len(stocks)})
                    print(f'PASS {day} {len(stocks)} stocks', flush=True)
                break
            except (OSError, ValueError, UnicodeError, urllib.error.URLError) as exc:
                if attempt == 2:
                    failed.append({'date': day.isoformat(), 'error': f'{type(exc).__name__}: {exc}'})
                    print(f'FAIL {day}: {exc}', flush=True)
                else:
                    time.sleep(attempt + 1)
    folder.mkdir(parents=True, exist_ok=True)
    summary = {'success': success, 'no_data': empty, 'weekend': skipped, 'failed': failed}
    (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if failed or (args.date and not success) else 0


if __name__ == '__main__':
    sys.exit(main())
