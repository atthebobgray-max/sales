"""Vinted Trend Radar — small standard-library HTTP server.
Configure optional eBay Browse credentials; enter verified social signals in the UI.
"""
import base64, datetime as dt, json, os, pathlib, re, secrets, threading, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'signals.json'
PORT = int(os.environ.get('PORT', '8765'))
HOST = os.environ.get('HOST', '0.0.0.0')
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '').strip()
LOCK = threading.Lock()
TOKEN = {'value': None, 'expires': 0}
CACHE = {'data': None, 'expires': 0}
CLIENT_ID = os.environ.get('EBAY_CLIENT_ID', '').strip()
CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '').strip()
# Short list is a *classification vocabulary*, never a claim these products are trending.
CATEGORIES = {
 'outerwear': ['jacket','coat','puffer','fleece','gilet','parka','windbreaker'],
 'footwear': ['trainers','sneakers','boots','loafers','shoes','slippers'],
 'knitwear': ['knit','cardigan','jumper','sweater'],
 'fashion': ['jeans','dress','handbag','bag','hoodie','denim','trousers','skirt','sunglasses','scarf'],
 'beauty accessories': ['makeup bag','beauty case','hair clip'],
 'fitness': ['running shoes','gym bag','running vest'],
}
REJECT = {'movie','football match','election','earthquake','weather','lottery','recipe','celebrity death','stock price'}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
def get_json():
    try:
        x=json.loads(DATA.read_text(encoding='utf-8'))
        return x if isinstance(x,list) else []
    except (FileNotFoundError, ValueError): return []
def save_json(rows):
    tmp=DATA.with_suffix('.tmp'); tmp.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8'); tmp.replace(DATA)
def request(url, headers=None, data=None):
    req=urllib.request.Request(url, headers={'User-Agent':'VintedTrendRadar/1.0 (+personal research)','Accept':'application/json, application/xml, text/xml, */*',**(headers or {})}, data=data)
    with urllib.request.urlopen(req,timeout=12) as r: return r.read()
def classify(title):
    s=title.lower()
    if any(w in s for w in REJECT): return None
    for cat, keywords in CATEGORIES.items():
        if any(re.search(r'\b'+re.escape(w)+r'\b',s) for w in keywords): return cat
    return None

def google_trends(country):
    # A limited feed of emerging Google searches: NOT TikTok/Instagram sales.
    try:
        xml=request('https://trends.google.com/trending/rss?geo='+country)
        root=ET.fromstring(xml)
        ns={'ht':'https://trends.google.com/trending/rss'}
        out=[]
        for it in root.findall('.//item'):
            title=(it.findtext('title') or '').strip()
            category=classify(title)
            if not category: continue
            traffic=it.findtext('ht:approx_traffic',default='',namespaces=ns)
            pub=it.findtext('pubDate') or ''
            out.append({'id':'google-'+country+'-'+re.sub('[^a-z0-9]+','-',title.lower()),'name':title,'category':category,'market':country,'source':'Google Trends','source_url':'https://trends.google.com/trending?geo='+country,'observed_at':now(),'published_at':pub,'traffic':traffic,'gender':'all','age':'25-44','status':'discovery','note':'Emerging Google search only; not verified purchases or age-specific demand.'})
        return out, None
    except Exception as e: return [], str(e)

def ebay_token():
    if not (CLIENT_ID and CLIENT_SECRET): return None
    if TOKEN['value'] and time.time()<TOKEN['expires']: return TOKEN['value']
    auth=base64.b64encode((CLIENT_ID+':'+CLIENT_SECRET).encode()).decode()
    body=b'grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope'
    obj=json.loads(request('https://api.ebay.com/identity/v1/oauth2/token',{'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded'},body))
    TOKEN.update(value=obj['access_token'],expires=time.time()+int(obj.get('expires_in',7200))-120)
    return TOKEN['value']

def get_ebay(q, country):
    token=ebay_token()
    if not token: return [], 'eBay API credentials not configured'
    try:
        params=urllib.parse.urlencode({'q':q[:100],'limit':'12','sort':'price','filter':'buyingOptions:{FIXED_PRICE}'})
        url='https://api.ebay.com/buy/browse/v1/item_summary/search?'+params
        site='EBAY_GB' if country=='GB' else 'EBAY_IE'
        obj=json.loads(request(url,{'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':site}))
        result=[]
        for item in obj.get('itemSummaries',[]):
            price=item.get('price',{})
            shipping=item.get('shippingOptions',[])
            ship=(shipping[0].get('shippingCost') or {}) if shipping else {}
            # Unknown shipping must remain unknown, not zero.
            p=float(price['value']) if 'value' in price else None
            s=float(ship['value']) if 'value' in ship else None
            if p is None: continue
            result.append({'title':item.get('title',''),'image':(item.get('image') or {}).get('imageUrl'), 'price':p,'shipping':s,'currency':price.get('currency','GBP'), 'url':item.get('itemWebUrl'), 'condition':item.get('condition',''), 'seller':(item.get('seller') or {}).get('username',''), 'marketplace':'eBay'})
        return result,None
    except Exception as e: return [],str(e)

def build(country):
    signals=get_json()
    manual=[s for s in signals if s.get('market') in (country,'BOTH')]
    google,ge=google_trends(country)
    items=manual+google
    # No arbitrary candidate products. Evidence is required to appear.
    for s in items:
        evidence=s.get('source','')
        s['verified_social']=evidence in ('TikTok','Instagram') and bool(s.get('source_url'))
        s['buyer_age_verified']=False
        s['purchases_verified']=False
        s['image']=s.get('image') or None
        s['buy_options']=[]
        s['price_status']='Not checked'
    return {'items':items,'errors':([f'Google Trends: {ge}'] if ge else []),'market':country,'updated_at':now(),'sources':{'google_trends':'ok' if ge is None else 'error','ebay':'configured' if CLIENT_ID and CLIENT_SECRET else 'needs keys','social':'user-supplied URLs and observations; no automatic TikTok/Instagram feed'}}

class Handler(BaseHTTPRequestHandler):
    def send(self,obj,status=200):
        payload=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        if u.path=='/':
            b=(ROOT/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        q=urllib.parse.parse_qs(u.query);market=q.get('market',['GB'])[0].upper()
        if market not in ('GB','IE'): return self.send({'error':'Invalid market'},400)
        if u.path=='/api/feed':
            key='feed-'+market
            with LOCK:
                if CACHE.get(key) and time.time()<CACHE[key]['expiry']: return self.send(CACHE[key]['data'])
            data=build(market)
            with LOCK: CACHE[key]={'data':data,'expiry':time.time()+300}
            return self.send(data)
        if u.path=='/api/price':
            search=q.get('q',[''])[0].strip()[:100]
            if not search or len(search)>100:return self.send({'error':'Missing product name'},400)
            rows,error=get_ebay(search,market)
            return self.send({'items':rows,'error':error,'source':'eBay active listings, not completed sales','updated_at':now()})
        self.send({'error':'Not found'},404)
    def do_POST(self):
        if self.path!='/api/signal':return self.send({'error':'Not found'},404)
        # Public deployments must configure ADMIN_TOKEN to permit writes.
        if not ADMIN_TOKEN and HOST != '127.0.0.1':return self.send({'error':'Adding signals is disabled until ADMIN_TOKEN is set'},403)
        if ADMIN_TOKEN and not secrets.compare_digest(self.headers.get('X-Admin-Token',''), ADMIN_TOKEN):return self.send({'error':'Incorrect or missing admin token'},401)
        try:
            length=int(self.headers.get('Content-Length',0))
            if length>16000: return self.send({'error':'Too large'},413)
            s=json.loads(self.rfile.read(length))
            for field in ('name','source','source_url','gender','market'):
                if not isinstance(s.get(field),str) or not s[field].strip():return self.send({'error':'Required: '+field},400)
            if s['source'] not in ('TikTok','Instagram','Other'):return self.send({'error':'Invalid source'},400)
            if s['gender'] not in ('men','women','all'):return self.send({'error':'Invalid gender'},400)
            if s['market'] not in ('GB','IE','BOTH'):return self.send({'error':'Invalid market'},400)
            url=urllib.parse.urlparse(s['source_url'])
            if url.scheme not in ('https','http') or not url.netloc:return self.send({'error':'Invalid evidence URL'},400)
            item={'id':secrets.token_hex(8),'name':s['name'].strip()[:110], 'source':s['source'],'source_url':s['source_url'].strip()[:1000], 'gender':s['gender'],'age':'25-44', 'market':s['market'],'category':classify(s['name']) or 'other','observed_at':now(),'note':str(s.get('note',''))[:500],'status':'social observation','views':str(s.get('views',''))[:40]}
            with LOCK:
                rows=get_json();rows.insert(0,item);save_json(rows)
                for k in list(CACHE):
                    if k.startswith('feed-'): CACHE.pop(k,None)
            return self.send({'ok':True,'item':item},201)
        except (ValueError,TypeError) as e:return self.send({'error':str(e)},400)

if __name__=='__main__':
    print(f'Open http://localhost:{PORT} — eBay credentials: {"configured" if CLIENT_ID and CLIENT_SECRET else "not configured"}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
