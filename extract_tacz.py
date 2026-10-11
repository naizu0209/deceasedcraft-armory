import json, os, re, sys, glob, collections

ROOT = "C:/Users/pronh/Documents/DeceasedCraftInfo"
TACZ = ROOT + "/DeceasedCraft_CB-5.11.19 (1)/overrides/tacz"
GUIDE = ROOT + "/DeceasedC_City_Item_Guide-main/"
OUT = sys.argv[1]


def strip_json(s):
    out, i, n, ins = [], 0, len(s), False
    while i < n:
        c = s[i]
        if ins:
            out.append(c)
            if c == '\\':
                out.append(s[i + 1]); i += 2; continue
            if c == '"':
                ins = False
            i += 1; continue
        if c == '"':
            ins = True; out.append(c); i += 1; continue
        if s.startswith('//', i):
            j = s.find('\n', i); i = n if j < 0 else j; continue
        if s.startswith('/*', i):
            j = s.find('*/', i + 2); i = n if j < 0 else j + 2; continue
        out.append(c); i += 1
    t = ''.join(out)
    return re.sub(r',(\s*[}\]])', r'\1', t)


def load(p):
    with open(p, encoding='utf-8-sig') as f:
        return json.loads(strip_json(f.read()))


packs = sorted(d for d in os.listdir(TACZ) if os.path.isdir(os.path.join(TACZ, d)) and d != 'immersive_ballistic')

lang = {}
for p in packs:
    for f in glob.glob(f"{TACZ}/{p}/assets/*/lang/en_us.json"):
        try:
            lang.update(load(f))
        except Exception as e:
            print('lang fail', f, e)


def tr(k):
    if not k or k not in lang:
        return ''
    return re.sub(r'§.', '', lang[k]).strip()


def pretty(i):
    if not i:
        return ''
    s = i.split(':')[-1].replace('_', ' ')
    return s.title()


guns, atts, ammo, tags, allow = {}, {}, {}, collections.defaultdict(list), collections.defaultdict(list)
recipes = {}
workbench = {}
for p in packs:
    for nsdir in glob.glob(f"{TACZ}/{p}/data/*"):
        ns = os.path.basename(nsdir)
        for f in glob.glob(f"{nsdir}/index/guns/*.json"):
            gid = f"{ns}:{os.path.basename(f)[:-5]}"
            idx = load(f)
            dref = idx.get('data', '')
            dn, dp = dref.split(':') if ':' in dref else (ns, dref)
            dfile = glob.glob(f"{TACZ}/*/data/{dn}/data/guns/{dp}.json")
            data = load(dfile[0]) if dfile else {}
            guns[gid] = dict(id=gid, pack=p, idx=idx, data=data)
        for f in glob.glob(f"{nsdir}/index/attachments/*.json"):
            aid = f"{ns}:{os.path.basename(f)[:-5]}"
            idx = load(f)
            dref = idx.get('data', '')
            dn, dp = dref.split(':') if ':' in dref else (ns, dref)
            dfile = glob.glob(f"{TACZ}/*/data/{dn}/data/attachments/{dp}.json")
            data = load(dfile[0]) if dfile else {}
            atts[aid] = dict(id=aid, pack=p, idx=idx, data=data)
        for f in glob.glob(f"{nsdir}/index/ammo/*.json"):
            aid = f"{ns}:{os.path.basename(f)[:-5]}"
            ammo[aid] = load(f)
        for f in glob.glob(f"{nsdir}/tacz_tags/attachments/*.json"):
            tags[f"{ns}:{os.path.basename(f)[:-5]}"] += load(f)
        for f in glob.glob(f"{nsdir}/tacz_tags/attachments/allow_attachments/*.json"):
            allow[f"{ns}:{os.path.basename(f)[:-5]}"] += load(f)
        for f in glob.glob(f"{nsdir}/recipes/**/*.json", recursive=True):
            try:
                r = load(f)
            except Exception as e:
                print('recipe fail', f, e); continue
            res = r.get('result', {})
            rid = res.get('id')
            if rid and res.get('type') in ('gun', 'attachment', 'ammo'):
                recipes[(res['type'], rid)] = dict(
                    recipe=f"{ns}:{os.path.relpath(f, nsdir + '/recipes')[:-5]}".replace('\\', '/'),
                    mats=[dict(id=(m['item'].get('item') or '#' + m['item'].get('tag', '')), n=m.get('count', 1)) for m in r.get('materials', [])],
                    count=res.get('count', 1), preset=res.get('attachments', {}))


def expand(entries, seen=None):
    seen = seen or set()
    out = set()
    for e in entries:
        if e.startswith('#'):
            t = e[1:]
            if t in seen:
                continue
            seen.add(t)
            out |= expand(tags.get(t, []), seen)
        else:
            out.add(e)
    return out


# Which gunsmith table crafts what (recipe filters)
def table_for(rid):
    ns = rid.split(':')[0]
    if ns == 'bf1':
        return 'BF1 workbench'
    if ns == 'suffuse':
        return 'Suffuse workbench'
    return 'Gunsmith table'


# Loot cross-reference from guide data
def loadjs(p):
    s = open(p, encoding='utf-8').read()
    return json.loads(s[s.index('{'):s.rindex('}') + 1])


loot = collections.defaultdict(lambda: dict(bld=set(), best=0.0, best_at=''))
mobdrop = collections.defaultdict(list)
try:
    db = loadjs(GUIDE + 'db.js')
    for b in db.values():
        for c in b['containers']:
            for it in c['items']:
                keys = {it['item'], it.get('vid', '')}
                if '@' in it.get('vid', ''):
                    keys.add(it['vid'].split('@', 1)[1])
                for k in keys:
                    if not k:
                        continue
                    L = loot[k]
                    L['bld'].add(b['name'])
                    if (it.get('chance') or 0) > L['best']:
                        L['best'] = it['chance']; L['best_at'] = f"{b['name']} ({c['name']})"
    mobs = loadjs(GUIDE + 'mobs.js')
    for m in mobs.values():
        for dr in m['drops']:
            for k in {dr['item'], (dr.get('vid') or '').split('@', 1)[-1]}:
                if k:
                    ch = dr.get('chances') or [None]
                    mobdrop[k].append(dict(mob=m['name'], chance=ch[0]))
except Exception as e:
    print('guide data fail', e)


def lootinfo(i):
    L = loot.get(i)
    md = mobdrop.get(i, [])
    return dict(buildings=sorted(L['bld']) if L else [], best=L['best'] if L else 0,
                bestAt=L['best_at'] if L else '', mobs=sorted({x['mob'] for x in md}))


def num(x, d=None):
    return x if isinstance(x, (int, float)) else d


G = []
for gid, g in sorted(guns.items()):
    idx, dat = g['idx'], g['data']
    b = dat.get('bullet', {})
    ex = b.get('extra_damage', {}) or {}
    rel = dat.get('reload', {})
    inacc = dat.get('inaccuracy', {})
    rec = dat.get('recoil', {})
    pitch = max([max(abs(v) for v in k['value']) for k in rec.get('pitch', [])] or [0])
    yaw = max([max(abs(v) for v in k['value']) for k in rec.get('yaw', [])] or [0])
    expl = b.get('explosion') or {}
    allowed = expand(allow.get(gid, []))
    # TaCZ also requires the attachment's type to be in the gun's allow_attachment_types
    # (e.g. FMJ ammo is type extended_mag, so a gun without that slot cannot take it even if tagged).
    slot_ok = set(dat.get('allow_attachment_types', []))
    allowed = {a for a in allowed if a in atts and atts[a]['idx'].get('type') in slot_ok}
    ammo_id = dat.get('ammo', '')
    ai = ammo.get(ammo_id, {})
    r = recipes.get(('gun', gid))
    G.append(dict(
        id=gid, pack=g['pack'].replace('_default_gun', ''), name=tr(idx.get('name')) or pretty(gid),
        desc=tr(idx.get('tooltip')), type=idx.get('type', ''), itemType=idx.get('item_type', ''),
        ammo=ammo_id, ammoName=tr(ai.get('name')) or pretty(ammo_id),
        mag=dat.get('ammo_amount'), xmag=dat.get('extended_mag_ammo_amount'),
        rpm=dat.get('rpm'), damage=b.get('damage', ((ex.get('damage_adjust') or [{}])[0]).get('damage')), pellets=b.get('bullet_amount', 1),
        armorIgnore=ex.get('armor_ignore', 0), headshot=ex.get('head_shot_multiplier', 1),
        falloff=[[a.get('distance'), a.get('damage')] for a in (ex.get('damage_adjust') or [])],
        speed=b.get('speed'), pierce=b.get('pierce', 1), knockback=b.get('knockback', 0),
        explode=bool(expl.get('explode')), explRadius=expl.get('radius'), explDamage=expl.get('damage'),
        ignite=b.get('ignite') if isinstance(b.get('ignite'), bool) else bool((b.get('ignite') or {}).get('entity')),
        bolt=dat.get('bolt', ''), modes=dat.get('fire_mode', []),
        burst=(dat.get('burst_data') or {}).get('count') if 'burst' in dat.get('fire_mode', []) else None,
        reloadType=rel.get('type', ''), reloadTac=(rel.get('feed') or {}).get('tactical'),
        reloadEmpty=(rel.get('feed') or {}).get('empty'),
        reloadTacTotal=(rel.get('cooldown') or {}).get('tactical'), reloadEmptyTotal=(rel.get('cooldown') or {}).get('empty'),
        aim=dat.get('aim_time'), draw=dat.get('draw_time'), sprint=dat.get('sprint_time'), weight=dat.get('weight'),
        move=dat.get('movement_speed'),
        hip=inacc.get('stand'), aimInacc=inacc.get('aim'), moveInacc=inacc.get('move'),
        inacc={k: inacc.get(k) for k in ('stand', 'move', 'sneak', 'lie', 'aim')},
        recoilV=pitch, recoilH=yaw, heat=bool(dat.get('heat')),
        recKeys={ax: [[k['time'], k['value'][0], k['value'][1]] for k in sorted(rec.get(ax) or [], key=lambda k: k['time'])] for ax in ('pitch', 'yaw')},
        crawlRec=dat.get('crawl_recoil_multiplier', 0.5),
        slotTypes=dat.get('allow_attachment_types', []),
        allowed=sorted(allowed),
        recipe=dict(table=table_for(gid), mats=r['mats'], preset=r['preset']) if r else None,
        loot=lootinfo(gid),
    ))

gun_by_att = collections.defaultdict(list)
for g in G:
    for a in g['allowed']:
        gun_by_att[a].append(g['id'])

def att_zoom(idx, ns):
    """Scope zoom levels (first = default, e.g. [4.25, 1.25]) live in the attachment's display JSON."""
    dref = idx.get('display', '')
    dn, dp = dref.split(':') if ':' in dref else (ns, dref)
    f = glob.glob(f"{TACZ}/*/assets/{dn}/display/attachments/{dp}.json")
    if not f:
        return None
    try:
        return load(f[0]).get('zoom')
    except Exception:
        return None


A = []
for aid, a in sorted(atts.items()):
    idx, dat = a['idx'], a['data']
    r = recipes.get(('attachment', aid))
    eff = {}
    for k, v in dat.items():
        if k in ('weight',):
            continue
        eff[k] = v
    A.append(dict(
        id=aid, pack=a['pack'].replace('_default_gun', ''), name=tr(idx.get('name')) or pretty(aid),
        desc=tr(idx.get('tooltip')), type=idx.get('type', ''), weight=dat.get('weight'),
        zoom=att_zoom(idx, aid.split(':')[0]), effects=eff, guns=sorted(gun_by_att.get(aid, [])),
        recipe=dict(table=table_for(aid), mats=r['mats']) if r else None,
        loot=lootinfo(aid),
    ))

AM = []
for aid, a in sorted(ammo.items()):
    r = recipes.get(('ammo', aid))
    AM.append(dict(id=aid, name=tr(a.get('name')) or pretty(aid), stack=a.get('stack_size'),
                   guns=sorted(g['id'] for g in G if g['ammo'] == aid),
                   recipe=dict(table=table_for(aid), mats=r['mats'], count=r['count']) if r else None))

matnames = {}
for coll in (G, A, AM):
    for x in coll:
        for m in ((x.get('recipe') or {}).get('mats') or []):
            matnames[m['id']] = m['id']

# damage-test targets for the simulator: base hp / armor from the guide's mob list
TARGETS = []
try:
    for m in mobs.values():
        st_ = m.get('stats') or {}
        if st_.get('hp'):
            TARGETS.append(dict(name=m['name'], hp=st_['hp'], armor=st_.get('armor') or 0))
    TARGETS.sort(key=lambda x: (x['hp'], x['name']))
except NameError:
    pass

json.dump(dict(guns=G, attachments=A, ammo=AM, targets=TARGETS, names={**{g['id']: g['name'] for g in G}, **{a['id']: a['name'] for a in A}}),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('guns', len(G), 'atts', len(A), 'ammo', len(AM))
print('guns no data', [g['id'] for g in G if g['damage'] is None])
print('guns no recipe', [g['id'] for g in G if not g['recipe']])
print('atts no recipe', len([a for a in A if not a['recipe']]))
print('atts no gun', [a['id'] for a in A if not a['guns']])
print('guns no allowed', [g['id'] for g in G if not g['allowed']])
print('guns in loot', sum(1 for g in G if g['loot']['buildings'] or g['loot']['mobs']))
print('atts in loot', sum(1 for a in A if a['loot']['buildings'] or a['loot']['mobs']))
print(collections.Counter(g['pack'] for g in G), collections.Counter(a['pack'] for a in A))
print(collections.Counter(g['type'] for g in G), collections.Counter(a['type'] for a in A))
