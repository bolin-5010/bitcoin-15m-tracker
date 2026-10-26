#!/usr/bin/env python3
"""Authenticated Kalshi -> CF Benchmarks BRTI, prior-minute mean for each 15m boundary.

No fallback to other venues. Values are BRTI index observations, not trade prices.
"""
import base64
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data.json'
BASE = 'https://external-api.kalshi.com'
PATH = '/trade-api/v2/cfbenchmarks/values'
INTERVAL = 900


def stamp(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def fetch_brti():
    key_id = os.environ.get('KALSHI_API_KEY_ID', '').strip()
    pem = os.environ.get('KALSHI_PRIVATE_KEY', '').replace('\\n', '\n').strip()
    if not key_id or not pem:
        raise RuntimeError('Please configure KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY GitHub Actions secrets.')
    millis = str(int(time.time() * 1000))
    signing = (millis + 'GET' + PATH).encode()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    sig = base64.b64encode(key.sign(signing, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())).decode()
    url = BASE + PATH + '?' + urlencode({'id': 'BRTI'})
    req = Request(url, headers={'KALSHI-ACCESS-KEY': key_id, 'KALSHI-ACCESS-SIGNATURE': sig,
        'KALSHI-ACCESS-TIMESTAMP': millis, 'Accept': 'application/json', 'User-Agent': 'BRTIQuarterTracker/3.0'})
    with urlopen(req, timeout=40) as response:
        result = json.load(response)
    if not isinstance(result, dict) or 'data' not in result:
        raise ValueError('Unexpected Kalshi response; no data envelope')
    return result['data']


def observations(tree):
    """Extract index observations, fail closed on an unknown response shape."""
    results = []
    def walk(x):
        if isinstance(x, list):
            for entry in x: walk(entry)
        elif isinstance(x, dict):
            # The usual CF BRTI row fields are time (milliseconds) and value.
            if 'value' in x and ('time' in x or 'timestamp' in x):
                try:
                    t = x.get('time', x.get('timestamp'))
                    if isinstance(t, str) and not t.isdigit():
                        sec = datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp()
                    else:
                        sec = float(t)
                        if sec > 1e11: sec /= 1000
                    val = Decimal(str(x['value']))
                    if val.is_finite() and val > 0: results.append((sec, val))
                except (ValueError, TypeError, ArithmeticError): pass
            else:
                for name, child in x.items():
                    if name in ('payload','values','BRTI','data','indexValues','results','value') or isinstance(child, list):
                        walk(child)
    walk(tree)
    return sorted(set(results))


def collect():
    now = time.time()
    points = observations(fetch_brti())
    if not points:
        raise RuntimeError('CF Benchmarks response contains no readable BRTI ticks. No Coinbase fallback; inspect response schema / entitlement.')
    payload = json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {}
    old = payload.get('samples', [])
    # Avoid mixing data sources or old Coinbase samples.
    by_time = {s['time']: s for s in old if s.get('source') == 'CF Benchmarks BRTI via Kalshi' and s.get('price_type') == 'prior_60s_mean'}
    newest_complete = int((min(now - 30, max(t for t, _ in points)) // INTERVAL) * INTERVAL)
    for boundary in range(newest_complete - 3600, newest_complete + 1, INTERVAL):
        if boundary < 0: continue
        label = stamp(boundary)
        if label in by_time: continue
        window = [v for t,v in points if boundary-60 <= t < boundary]
        # 55 distinct seconds minimum makes partial data less likely to be misrepresented.
        covered = len({int(t) for t,v in points if boundary-60 <= t < boundary})
        if covered < 55: continue
        avg = sum(window, Decimal(0))/Decimal(len(window))
        by_time[label] = {'time':label,'price':round(float(avg), 4),
            'price_type':'prior_60s_mean','source':'CF Benchmarks BRTI via Kalshi',
            'observations':len(window),'seconds_covered':covered}
    records = sorted(by_time.values(), key=lambda p: p['time'])[-35040:]
    if not records and not old:
        print('No complete 60-second window yet. Not writing an incorrect value.')
    payload = {'symbol':'BTC-USD','source':'CF Benchmarks BRTI via Kalshi (authenticated)',
        'interval_minutes':15,'price_definition':'mean BRTI index observations over 60 seconds before boundary',
        'updated_at':stamp(now),'samples': records}
    DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'CF BRTI index points retrieved: {len(points)}. Quarter-hour observations stored: {len(records)}.')

if __name__=='__main__':
    collect()
