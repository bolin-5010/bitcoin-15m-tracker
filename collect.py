#!/usr/bin/env python3
"""Record quarter-hour BTC/USD prices using Coinbase 1-minute candle OPEN.

A label of 12:15:00 means the first trade in [12:15:00,12:16:00) UTC,
not a trade guaranteed to have happened at exactly 12:15:00.
"""
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'data.json'
API = 'https://api.exchange.coinbase.com/products/BTC-USD/candles'
QUARTER = 15 * 60
MINUTE = 60
MAX_BACKFILL_SECONDS = 24 * 3600


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def quarter_timestamp(s):
    timestamp = int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp())
    return timestamp if timestamp % QUARTER == 0 else None


def get_candles(start, end):
    params = urllib.parse.urlencode({'granularity': 60, 'start': iso(start), 'end': iso(end)})
    request = urllib.request.Request(f'{API}?{params}', headers={
        'User-Agent': 'BTCQuarterHourMonitor/2.0', 'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                rows = json.load(response)
            if not isinstance(rows, list):
                raise ValueError(f'Unexpected Coinbase API response: {str(rows)[:200]}')
            return rows
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def collect(now=None):
    now = int(time.time()) if now is None else int(now)
    # Wait until at least 70 seconds after a quarter to use a completed 1-min candle.
    latest = ((now - 70) // QUARTER) * QUARTER
    if latest < 0:
        return 0

    if DATA.exists():
        payload = json.loads(DATA.read_text(encoding='utf-8'))
    else:
        payload = {}
    old = payload.get('samples', [])
    # Remove legacy execution-time samples; only genuine quarter-hour labels are valid.
    by_time = {}
    for sample in old:
        try:
            stamp = quarter_timestamp(sample['time'])
            price = Decimal(str(sample['price']))
            if stamp is not None and stamp <= latest and price.is_finite() and price > 0:
                by_time[stamp] = sample
        except (KeyError, ValueError, TypeError, ArithmeticError):
            continue

    # On first deployment, start at the latest completed quarter; don't pretend we
    # were recording before activation. Later runs backfill missed quarters <=24h.
    start = max(by_time) + QUARTER if by_time else latest
    start = max(start, latest - MAX_BACKFILL_SECONDS)
    if start > latest:
        print('No new completed quarter-hour slot. Existing samples:', len(by_time))
    else:
        # 4h windows (<300 one-minute bars per request), including the final minute.
        for window_start in range(start, latest + 1, 4 * 3600):
            window_last = min(window_start + 4 * 3600 - QUARTER, latest)
            candles = get_candles(window_start, window_last + MINUTE)
            expected = set(range(window_start, window_last + 1, QUARTER))
            for candle in candles:
                if not isinstance(candle, list) or len(candle) < 6:
                    continue
                stamp = int(candle[0])
                if stamp not in expected or stamp in by_time:
                    continue
                price = Decimal(str(candle[3]))  # Coinbase [time,low,high,open,close,volume]
                if not price.is_finite() or price <= 0:
                    continue
                by_time[stamp] = {'time': iso(stamp), 'price': float(price),
                                  'price_type': '1m_candle_open', 'source_candle_time': iso(stamp)}
            time.sleep(0.2)

    records = [by_time[k] for k in sorted(by_time)][-35040:]
    payload.update({'symbol': 'BTC-USD',
                    'source': 'Coinbase Exchange BTC-USD historical 1-minute candle open',
                    'interval_minutes': 15, 'price_definition': 'first trade of minute starting at label',
                    'samples': records, 'updated_at': iso(now)})
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    added = len(records) - len([s for s in old if quarter_timestamp(s.get('time', '1970-01-01T00:00:00Z')) is not None])
    print(f'Finished. Last eligible: {iso(latest)}; stored: {len(records)}. Last records: {records[-3:]}')
    return max(0, added)


if __name__ == '__main__':
    collect()
