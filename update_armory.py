#!/usr/bin/env python3
"""Rebuild the DeceasedCraft Armory page from a (new) extracted DeceasedCraft_CB modpack folder.

    python update_armory.py                      window: pick the folder, press Update
    python update_armory.py PACK [--out DIR]     same thing, no window

PACK is the extracted modpack folder (the one holding manifest.json and overrides/), or a folder that
contains one or more of those: the newest version found is used. It reads the TaCZ gun packs in
overrides/tacz (stats, recipes, recoil, attachment fit, icons), the pack version and the enchantment config,
adds the mob presets and ingredient icons kept in data.json, and writes tacz.json (the data) and
index.html (template.html with the data inlined) into the output folder. It then lists the guns,
attachments and ammo that were added or removed.
Needs Python 3 with Pillow (py -m pip install pillow).
"""
import argparse
import base64
import collections
import contextlib
import glob
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, 'update_armory.cfg.json')
GUIDE_COPY = os.path.join(HERE, 'data.json')


# ---------- finding the pack
def pack_version(overrides):
    """(sort key, label) from the manifest next to overrides/."""
    try:
        with open(os.path.join(os.path.dirname(overrides), 'manifest.json'), encoding='utf-8-sig') as f:
            m = json.load(f)
        v = str(m.get('version', ''))
        return tuple(int(x) for x in re.findall(r'\d+', v)), (m.get('name', '') + ' ' + v).strip()
    except Exception:
        return (), os.path.basename(os.path.dirname(overrides))


def is_overrides(d):
    return os.path.isdir(os.path.join(d, 'tacz'))


def resolve_pack(path):
    """Return the overrides folder for `path`: a pack folder, its overrides/ or tacz/ folder, or a folder holding packs (newest wins)."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return None
    if os.path.basename(path) == 'tacz' and is_overrides(os.path.dirname(path)):
        return os.path.dirname(path)
    for d in (path, os.path.join(path, 'overrides')):
        if is_overrides(d):
            return d
    found = []
    for name in sorted(os.listdir(path)):
        sub = os.path.join(path, name)
        for d in (os.path.join(sub, 'overrides'), os.path.join(sub, name, 'overrides')):   # an archive often extracts to X/X/
            if is_overrides(d):
                found.append((pack_version(d)[0], d))
                break
    return max(found, key=lambda x: x[0])[1] if found else None


def default_pack():
    return resolve_pack(os.path.dirname(HERE)) or ''


# ---------- the update
def ids(data):
    return {k: {x['id']: x['name'] for x in data.get(k, [])} for k in ('guns', 'attachments', 'ammo')}


class _LogOut:
    """Sends what the data steps print to the log, line by line."""

    def __init__(self, log):
        self.log, self.buf = log, ''

    def write(self, s):
        self.buf += s
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            if line.strip():
                self.log('  ' + line.rstrip()[:240])
        return len(s)

    def flush(self):
        pass


def build_data(PACK, CACHE, OUT):
    """Read the gun packs under PACK/tacz (stats, recipes, recoil, attachment fit, pack version, enchantment config)
    and the kept mob presets in CACHE; write the data to OUT as JSON."""
    TACZ = PACK + "/tacz"
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


    # Simulator target presets (mob health / armor) from the kept guide data
    targets_src = []
    try:
        targets_src = json.load(open(CACHE, encoding='utf-8')).get('targets', [])
    except Exception as e:
        print('data.json missing or unreadable, no mob presets:', e)


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
    TARGETS = sorted(targets_src, key=lambda x: (x['hp'], x['name']))

    # pack label for the page header, from the modpack's manifest.json (next to overrides/)
    META = dict(pack=os.path.basename(os.path.dirname(PACK)))
    try:
        mf = load(os.path.dirname(PACK) + '/manifest.json')
        META = dict(pack=(mf.get('name', '').replace('DeceasedCraft_', '') + ' ' + mf.get('version', '')).strip() or META['pack'])
    except Exception as e:
        print('no manifest', e)

    # TaCZ Enchantments Overhaul values (level caps, per-level effect, guns barred from Capacity)
    ENCH = {}
    try:
        t = open(PACK + '/config/tacz_enchantments_overhaul.json5', encoding='utf-8-sig').read()
        t = re.sub(r'(?m)^(\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', strip_json(t))
        cfg = json.loads(t)
        ENCH = dict(cfg={k: v for k, v in cfg.items() if isinstance(v, (int, float))}, noCap=(cfg.get('enchantments_blacklist') or {}).get('tacz_eo:capacity', []))
    except Exception as e:
        print('no enchantment config', e)

    json.dump(dict(meta=META, ench=ENCH, guns=G, attachments=A, ammo=AM, targets=TARGETS, names={**{g['id']: g['name'] for g in G}, **{a['id']: a['name'] for a in A}}),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('guns', len(G), 'atts', len(A), 'ammo', len(AM))
    print('guns no data', [g['id'] for g in G if g['damage'] is None])
    print('guns no recipe', [g['id'] for g in G if not g['recipe']])
    print('atts no recipe', len([a for a in A if not a['recipe']]))
    print('atts no gun', [a['id'] for a in A if not a['guns']])
    print('guns no allowed', [g['id'] for g in G if not g['allowed']])
    print(collections.Counter(g['pack'] for g in G), collections.Counter(a['pack'] for a in A))
    print(collections.Counter(g['type'] for g in G), collections.Counter(a['type'] for a in A))


def add_icons(PACK, CACHE, path):
    """Add `icons` (guns, attachments, ammo: the slot textures from the gun packs, scaled to 64 px) and `ingIcons`
    (recipe ingredients: kept icons, DCTweaks jar, KubeJS textures) to the data file at path."""
    from PIL import Image
    TACZ = PACK + "/tacz"
    MAX = 64
    def load(p):
        t = open(p, encoding='utf-8-sig').read()
        t = re.sub(r'(?m)^\s*//.*$', '', t)
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        return json.loads(re.sub(r',(\s*[}\]])', r'\1', t))


    def find(pattern):
        hits = glob.glob(pattern)
        return hits[0] if hits else None


    def to_uri(png_path):
        im = Image.open(png_path).convert('RGBA')
        if max(im.size) > MAX:
            im.thumbnail((MAX, MAX), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'PNG', optimize=True)
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


    data = json.load(open(path, encoding='utf-8'))
    want = {'guns': 'guns', 'attachments': 'attachments', 'ammo': 'ammo'}
    icons, missing = {}, []
    for kind, folder in want.items():
        for item in data[kind]:
            ns, name = item['id'].split(':')
            idx_file = find(f"{TACZ}/*/data/{ns}/index/{folder}/{name}.json")
            slot = None
            if idx_file:
                dref = load(idx_file).get('display', '')
                dn, dp = dref.split(':') if ':' in dref else (ns, dref)
                disp = find(f"{TACZ}/*/assets/{dn}/display/{folder}/{dp}.json")
                if disp:
                    slot = load(disp).get('slot')
            png = None
            if slot and ':' in slot:
                sn, sp = slot.split(':', 1)
                png = find(f"{TACZ}/*/assets/{sn}/textures/{sp}.png")
            if png:
                icons[item['id']] = to_uri(png)
            else:
                missing.append(item['id'])

    data['icons'] = icons

    # ---- ingredient icons (recipe materials) ----
    import zipfile
    jars = sorted(glob.glob(PACK + "/mods/DCTweaks*.jar"))
    JAR = jars[-1] if jars else None
    # ingredient icons kept from the City Item Guide
    try:
        guide = json.load(open(CACHE, encoding='utf-8')).get('icons', {})
    except Exception:
        guide = {}
        print('data.json missing, some ingredient icons will be missing')

    # item id -> texture ref, from the pack's KubeJS item definitions
    tex_ref = {}
    for f in glob.glob(PACK + "/kubejs/startup_scripts/items/*.js"):
        src = open(f, encoding='utf-8').read()
        for m in re.finditer(r"event\.create\('([^']+)'\)(.*?)(?=event\.create\(|\Z)", src, re.S):
            tm = re.search(r"\.texture\('([^']+)'\)", m.group(2))
            if tm:
                tex_ref[m.group(1)] = tm.group(1)

    jar = zipfile.ZipFile(JAR) if JAR else None
    jar_names = set(jar.namelist()) if jar else set()


    def jar_uri(ref):
        ns, path = ref.split(':', 1)
        name = f"assets/{ns}/textures/{path}.png"
        if name not in jar_names:
            return None
        im = Image.open(io.BytesIO(jar.read(name))).convert('RGBA')
        if im.height > im.width:          # animated strip: keep first frame
            im = im.crop((0, 0, im.width, im.width))
        buf = io.BytesIO()
        im.save(buf, 'PNG', optimize=True)
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


    # tag -> representative item (icons only; the real recipe accepts any item in the tag)
    TAG_ITEM = {
        'forge:leather': 'minecraft:leather', 'forge:plates/aluminum': 'immersiveengineering:plate_aluminum',
        'forge:rods/blaze': 'minecraft:blaze_rod', 'minecraft:planks': 'minecraft:oak_planks',
        'forge:dyes/blue': 'minecraft:blue_dye', 'minecraft:logs': 'minecraft:oak_log',
        'forge:ingots/iron': 'minecraft:iron_ingot', 'forge:dusts/redstone': 'minecraft:redstone',
        'forge:gems/amethyst': 'minecraft:amethyst_shard', 'forge:obsidian': 'minecraft:obsidian',
        'forge:glass': 'minecraft:glass', 'forge:dusts/glowstone': 'minecraft:glowstone_dust',
        'forge:ingots/gold': 'minecraft:gold_ingot', 'forge:ingots/steel': 'immersiveengineering:ingot_steel',
        'minecraft:wool': 'minecraft:white_wool', 'forge:storage_blocks/lead': 'immersiveengineering:storage_lead',
        'forge:gunpowder': 'minecraft:gunpowder', 'forge:nuggets/lead': 'immersiveengineering:nugget_lead',
        'forge:ingots/lead': 'immersiveengineering:ingot_lead',
        'forge:plates/plastic': 'immersiveengineering:plate_duroplast',
    }
    # display names that differ from what the tag id suggests (in-game name, from the guide data)
    ING_NAMES = {'#forge:plates/plastic': 'Duroplast Sheet (any)'}

    mats = sorted({m['id'] for k in ('guns', 'attachments', 'ammo') for x in data[k]
                   for m in ((x.get('recipe') or {}).get('mats') or [])})
    ing, ing_missing = {}, []
    for mid in mats:
        base = mid.lstrip('#')
        item = TAG_ITEM.get(base, base) if mid.startswith('#') else base
        uri = guide.get(item)
        if not uri and item in tex_ref:
            uri = jar_uri(tex_ref[item])
        if not uri:
            ns, n = item.split(':', 1)
            uri = jar_uri(f"{ns}:item/{n}")
        if uri:
            ing[mid] = uri
        else:
            ing_missing.append(mid)
    data['ingIcons'] = ing
    data['ingNames'] = ING_NAMES
    print('ingredient icons', len(ing), 'of', len(mats), 'missing', ing_missing)
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('icons', len(icons), 'missing', len(missing), missing)
    print('icon bytes', sum(len(v) for v in icons.values()), 'file bytes', os.path.getsize(path))


def run_update(pack, out_dir, log):
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise RuntimeError('Pillow is missing. Install it with:  py -m pip install pillow')
    ov = resolve_pack(pack) if pack else None
    if not ov:
        raise RuntimeError('No modpack found in "%s". Pick the extracted DeceasedCraft_CB folder (it holds manifest.json and overrides/).' % pack)
    label = pack_version(ov)[1]
    log('Modpack: %s\n  %s' % (label, ov))
    packs = [d for d in os.listdir(os.path.join(ov, 'tacz')) if os.path.isdir(os.path.join(ov, 'tacz', d))]
    log('Gun packs: ' + ', '.join(sorted(packs)))
    if not os.path.exists(GUIDE_COPY):
        log('WARNING: data.json is missing, mob presets and some ingredient icons will be missing')
    template = os.path.join(HERE, 'template.html')
    with open(template, encoding='utf-8') as f:
        tmpl = f.read()
    if '__DATA__' not in tmpl:
        raise RuntimeError('template.html has no __DATA__ placeholder')

    os.makedirs(out_dir, exist_ok=True)
    cur, new = os.path.join(out_dir, 'tacz.json'), os.path.join(out_dir, 'tacz.new.json')
    before = {}
    if os.path.exists(cur):
        try:
            with open(cur, encoding='utf-8') as f:
                before = ids(json.load(f))
        except Exception:
            pass

    root = ov.replace(chr(92), '/').rstrip('/')
    log('\nReading the gun packs...')
    with contextlib.redirect_stdout(_LogOut(log)):
        build_data(root, GUIDE_COPY, new)
    log('\nCollecting icons...')
    with contextlib.redirect_stdout(_LogOut(log)):
        add_icons(root, GUIDE_COPY, new)

    with open(new, encoding='utf-8') as f:
        raw = f.read()
    data = json.loads(raw)
    if not data.get('guns'):
        raise RuntimeError('No guns found. Is this a TaCZ modpack?')
    after = ids(data)
    if before and len(after['guns']) < 0.8 * len(before['guns']):
        log('WARNING: guns dropped from %d to %d, check the pack folder before publishing' % (len(before['guns']), len(after['guns'])))

    os.replace(new, cur)
    html = tmpl.replace('__DATA__', raw.replace('</', '<\\/'), 1)
    outs = ['index.html']
    for name in outs:
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(html)

    log('\nDone: %d guns, %d attachments, %d ammo, %d targets (%s)' % (len(data['guns']), len(data['attachments']), len(data['ammo']), len(data.get('targets', [])), label))
    if before:
        for k, title in (('guns', 'Guns'), ('attachments', 'Attachments'), ('ammo', 'Ammo')):
            add = sorted(after[k][i] for i in after[k].keys() - before[k].keys())
            rem = sorted(before[k][i] for i in before[k].keys() - after[k].keys())
            log('%s: +%d new, -%d removed' % (title, len(add), len(rem)))
            if add:
                log('   new: ' + ', '.join(add[:40]) + (' ...' if len(add) > 40 else ''))
            if rem:
                log('   removed: ' + ', '.join(rem[:40]) + (' ...' if len(rem) > 40 else ''))
    else:
        log('(no earlier tacz.json to compare with)')
    log('Wrote %s in %s' % (', '.join(['tacz.json'] + outs), out_dir))
    log('Next: publish index.html (as the Artifact, or commit and push it for GitHub Pages).')


# ---------- window
def gui():
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, ttk

    cfg = {}
    try:
        with open(CFG, encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception:
        pass
    root = tk.Tk()
    root.title('DeceasedCraft Armory updater')
    root.geometry('820x560')
    pack = tk.StringVar(value=cfg.get('pack') or default_pack())
    out = tk.StringVar(value=cfg.get('out') or HERE)
    q = queue.Queue()

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill='both', expand=True)
    frm.columnconfigure(1, weight=1)
    frm.rowconfigure(3, weight=1)

    def row(r, label, var, hint):
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky='w', pady=3)
        ttk.Entry(frm, textvariable=var).grid(row=r, column=1, sticky='ew', padx=6)
        ttk.Button(frm, text='Browse', command=lambda: (lambda d: d and var.set(d))(filedialog.askdirectory(title=hint, initialdir=var.get() or HERE))).grid(row=r, column=2)

    row(0, 'Modpack folder', pack, 'Extracted DeceasedCraft_CB folder (or a folder holding them)')
    row(1, 'Output folder', out, 'Where tacz.json and index.html are written')
    btns = ttk.Frame(frm)
    btns.grid(row=2, column=0, columnspan=3, sticky='ew', pady=8)
    go = ttk.Button(btns, text='Update')
    go.pack(side='left')
    ttk.Button(btns, text='Open output folder', command=lambda: os.startfile(out.get()) if os.path.isdir(out.get()) else None).pack(side='left', padx=8)
    box = tk.Text(frm, wrap='word', state='disabled', font=('Consolas', 9))
    box.grid(row=3, column=0, columnspan=3, sticky='nsew')
    sb = ttk.Scrollbar(frm, command=box.yview)
    sb.grid(row=3, column=3, sticky='ns')
    box['yscrollcommand'] = sb.set

    def put(msg):
        box.configure(state='normal')
        box.insert('end', msg + '\n')
        box.see('end')
        box.configure(state='disabled')

    def pump():
        try:
            while True:
                item = q.get_nowait()
                if item is None:
                    go.configure(state='normal')
                else:
                    put(item)
        except queue.Empty:
            pass
        root.after(100, pump)

    def work():
        try:
            run_update(pack.get().strip(), out.get().strip() or HERE, q.put)
        except Exception as e:
            q.put('\nERROR: %s' % e)
        q.put(None)

    def start():
        try:
            with open(CFG, 'w', encoding='utf-8') as f:
                json.dump(dict(pack=pack.get(), out=out.get()), f)
        except Exception:
            pass
        box.configure(state='normal')
        box.delete('1.0', 'end')
        box.configure(state='disabled')
        go.configure(state='disabled')
        threading.Thread(target=work, daemon=True).start()

    go.configure(command=start)
    put('Pick the extracted DeceasedCraft_CB folder and press Update.')
    pump()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description='Rebuild the DeceasedCraft Armory page from a modpack folder.')
    ap.add_argument('pack', nargs='?', help='extracted modpack folder (omit to open the window)')
    ap.add_argument('--out', default=HERE, help='output folder (default: next to this script)')
    a = ap.parse_args()
    if not a.pack:
        return gui()
    try:
        run_update(a.pack, a.out, lambda m: print(m, file=sys.__stdout__))   # not plain print: the data steps' prints are redirected into this log
    except Exception as e:
        print('ERROR:', e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
