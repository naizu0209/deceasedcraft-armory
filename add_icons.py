"""Adds an `icons` map {item id: PNG data URI} to tacz.json.

Run after extract_tacz.py:  python add_icons.py tacz.json
Icon source: the `slot` texture named in each item's display JSON, found under
overrides/tacz/<pack>/assets/<ns>/textures/. Large textures are downscaled to MAX px.
"""
import base64, glob, io, json, os, re, sys
from PIL import Image

ROOT = "C:/Users/pronh/Documents/DeceasedCraftInfo"
TACZ = ROOT + "/DeceasedCraft_CB-5.11.19 (1)/overrides/tacz"
MAX = 64
path = sys.argv[1]


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
PACK = ROOT + "/DeceasedCraft_CB-5.11.19 (1)/overrides"
JAR = PACK + "/mods/DCTweaks_5.11.19.jar"
GUIDE_ICONS = ROOT + "/DeceasedC_City_Item_Guide-main/icons.js"

s = open(GUIDE_ICONS, encoding='utf-8').read()
guide = json.loads(s[s.index('{'):s.rindex('}') + 1])

# item id -> texture ref, from the pack's KubeJS item definitions
tex_ref = {}
for f in glob.glob(PACK + "/kubejs/startup_scripts/items/*.js"):
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r"event\.create\('([^']+)'\)(.*?)(?=event\.create\(|\Z)", src, re.S):
        tm = re.search(r"\.texture\('([^']+)'\)", m.group(2))
        if tm:
            tex_ref[m.group(1)] = tm.group(1)

jar = zipfile.ZipFile(JAR)
jar_names = set(jar.namelist())


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
    if not uri:   # textures downloaded from GitHub (see extra_icons/README.txt)
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extra_icons', item.replace(':', '__') + '.png')
        if os.path.exists(f):
            uri = 'data:image/png;base64,' + base64.b64encode(open(f, 'rb').read()).decode()
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
