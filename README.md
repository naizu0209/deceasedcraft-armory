# DeceasedCraft Armory

A single-page guide to every gun, attachment and ammo type in the DeceasedCraft modpack's TaCZ gun packs.
Open `index.html` in a browser. No server and no install; the data is inlined in the page.

## What it does

- **Guns / Attachments / Ammo**: search, filter and sort by damage, DPS, armor penetration, recoil, spread and more. Each item has a sheet with its recipe and what it fits. Only craftable items show by default; **Show uncraftable** adds the rest.
- **Special ammo**: the *Ammo* select on the Guns tab applies FMJ, Hollow-Point, Incendiary, High Explosive or Slug to every gun that accepts it.
- **Gunsmith**: build a gun with attachments and TaCZ enchantments (Enchantments Overhaul). Stat bars follow the in-game gun refit screen; hovering an attachment shows its effects. Guns whose stats change by fire mode get a fire-mode switch (pack `fire_mode_adjust`); pistols and SMGs get a dual-wield switch (TaCZ Dual Wield: both guns fire, so 2x fire rate and magazine, recoil x3 from its config). An attachment's sheet shows what it does to the chosen gun.
- **Shooting range**: fire at a dummy with recoil and spread for each stance, set the target's health and armor, and see DPS and the recoil pattern.

## How the numbers work

- Stats are base values read from the gun packs in `overrides/tacz/`. Server multipliers in the pack config are all 1.0, except `GlobalBulletSpeedModifier = 2.0` in `tacz-common.toml`, which doubles every bullet speed (the page shows base and effective).
- Attachments combine as `(base + addends) * (1 + percents) * multipliers`, with formula modifiers evaluated first.
- DPS = damage per shot x RPM / 60, body shots, before falloff. A shot's damage is split evenly across its pellets. *DPS vs armor* lets the armor-pen share bypass armor and runs the rest through vanilla armor reduction for the armor points entered (toughness is not modeled).
- Recoil follows TaCZ's camera code: one curve per shot through the gun's recoil keyframes, scaled by scope zoom, prone and attachments. Kick that has not recovered stays as climb. **Controlled** assumes an average player cancels about 70% of the vertical and 50% of the sideways climb; that is an estimate, not a measurement.
- Each pellet lands inside the stance's spread cone and is tested against a 1.8 m player shape. Damage falls off by range step, then armor applies per pellet.
- Not modeled: bullet drop, moving targets, armor enchants, mob health scaling, real mob hitboxes, and mob resistances. Target presets use the City Item Guide's base health and armor.
- Recipes: BF1 recipes only show on the BF1 workbench and Suffuse recipes on the Suffuse workbench; everything else is on the standard Gunsmith table.

## Updating for a new modpack version

Extract the new `DeceasedCraft_CB-x.y.z` folder, then run the updater:

```
python update_armory.py
```

(or double-click `update_armory.bat`). Pick the extracted modpack folder, then press **Update**. It rewrites `tacz.json` and `index.html`, and lists the guns, attachments and ammo that were added or removed. From the command line:

```
python update_armory.py "C:\path\to\DeceasedCraft_CB-x.y.z"
```

Needs Python 3 with Pillow (`py -m pip install pillow`).

### Guide data

Mob presets and ingredient icons are kept in `data.json`: most come from the DeceasedCraft City Item Guide, and three (fire charge from PrismarineJS/minecraft-assets, jerrycan from Immersive Engineering, gunpowder pinch from Create Big Cannons, CC BY-NC-SA 4.0) were downloaded from GitHub. The updater does not read the guide itself.

## Files

| File | Purpose |
|---|---|
| `index.html` | The built page (served by GitHub Pages) |
| `template.html` | Page source with a `__DATA__` placeholder; edit this, never the built page |
| `tacz.json` | Extracted data (guns, attachments, ammo, targets, icons, pack version, enchantment config) |
| `update_armory.py`, `update_armory.bat` | The updater: reads the gun packs, adds icons, writes `tacz.json` and `index.html` |
| `data.json` | Kept copy of the City Item Guide data used here (mob presets, ingredient icons incl. three downloaded from GitHub) |

## Credits

Data and icons come from the DeceasedCraft modpack, its TaCZ gun packs and the DeceasedCraft City Item Guide. Made by naizu0209. This is an unofficial fan tool.
