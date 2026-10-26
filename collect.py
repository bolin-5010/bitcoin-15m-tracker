#!/usr/bin/env python3
"""Collect Coinbase Exchange BTC-USD last trade, append only valid timed samples."""
import json, os, pathlib, time, urllib.request
from datetime import datetime, timezone
from decimal import Decimal

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / 'data.json'
API = 'https://api.exchange.coinbase.com/products/BTC-USD/ticker'

def collect():
    request = urllib.request.Request(API, headers={'User-Agent': 'BTC15Monitor/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=25) as resp:
        result = json.load(resp)
    price = Decimal(str(result['price']))
    assert price > 0 and price.is_finite(), 'Invalid price'
    trade_time = datetime.fromisoformat(result['time'].replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    if abs((now-trade_time).total_seconds()) > 600:
        raise ValueError('Price trade is stale: '+str(trade_time))
    record = {'time':now.isoformat(timespec='seconds').replace('+00:00','Z'), 'price':float(price), 'trade_time':trade_time.isoformat(timespec='seconds').replace('+00:00','Z')}
    if DATA.exists():
        payload=json.loads(DATA.read_text('utf-8'))
    else:
        payload={'symbol':'BTC-USD','source':'Coinbase Exchange ticker price (last trade)','interval_minutes':15,'samples':[]}
    samples=payload.setdefault('samples',[])
    # A rerun within the same 15-minute UTC bin updates the existing point.
    key=int(now.timestamp())//900
    samples[:]=[s for s in samples if int(datetime.fromisoformat(s['time'].replace('Z','+00:00')).timestamp())//900 != key]
    samples.append(record)
    samples.sort(key=lambda s:s['time'])
    # 365 days maximum to prevent repository from growing forever
    payload['samples']=samples[-35040:]
    payload['updated_at']=record['time']
    DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(record)

if __name__=='__main__':
    for attempt in range(3):
        try:
            collect(); break
        except Exception as err:
            if attempt==2: raise
            print(f'Attempt {attempt+1} failed: {err}')
            time.sleep(4 * (attempt+1))
