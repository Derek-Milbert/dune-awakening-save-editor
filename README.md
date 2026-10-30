# Dune: Awakening Save Editor

A free, local save editor for your **offline / self-hosted single-player** Dune: Awakening save. It finds your save,
shows it in a browser UI (soft-UI "neumorphic" design in CHOAM cream and copper), and lets you change your wallet,
level and skill points, skills, specializations, recipes, building sets, skins and swatches, and your inventory.

> **Unofficial fan tool.** Not affiliated with or endorsed by Funcom or Dune: Awakening. Use it only on your own
> offline / self-hosted single-player saves; never on an online character. **Always keep a backup** (the editor
> makes one before every write). Every editing feature has been tested in-game by the author, but only on one
> save and one game version; see [Tested vs assumed](#tested-vs-assumed).
> `data/*.json` are catalogues of names and stats extracted from the game's own files for use with this tool;
> all game content belongs to its owners.

## Quick start (Windows)

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/> (tick *Add python.exe to PATH*).
   Nothing else needs installing.
2. **Close Dune: Awakening completely**, including the solo server process.
3. Download this repository (green **Code** button → *Download ZIP*, then unzip) and double-click
   **`start_editor.bat`**. (Or run `python run.py`.)
4. Your browser opens at `http://127.0.0.1:8765`. Make edits in any tab (they are **staged**, nothing touches the game
   yet), check the **Pending changes** list on the Overview, then press **Write to game** (bottom right).

The editor runs on your PC only and listens on `127.0.0.1`; nothing is uploaded anywhere.

## Documentation

* **[User guide](docs/USER_GUIDE.md)**: step-by-step instructions for every tab, how writing and undoing works,
  troubleshooting and FAQ.
* **[How it works](docs/HOW_IT_WORKS.md)**: the save format, how edits and the safety checks work, where the
  catalogue data comes from, and a map of the code.

## What you can edit

| Tab | Edits |
|---|---|
| Overview | Dashboard: Solari, House Script, tech knowledge points, total / unspent skill points (**level = total skill points + 1**), total XP; clickable progress tiles for every collection; and a **Pending changes** list comparing your staged edits with the save as it was opened |
| Skills | Class skills for Trooper, Mentat, Planetologist, Bene Gesserit, Swordmaster: tier unlocks, capstones, tree nodes, and the shared abilities / perks / spice techniques (rank per node) |
| Specializations | Crafting / Gathering / Exploration / Combat / Sabotage: track level (0-100, XP set from the game's own curve) and which traits (keystones) you own |
| Recipes | Known crafting recipes (Tier 6 weapons, armor, stillsuits and augmentations): **grade** (1-5) and **how many times you can craft** each |
| Building | Full catalogue of all 276 building sets ("patents") with their pieces, searchable and filterable; tick to learn / untick to forget |
| Skins & Swatches | All 804 skins (mesh / material variants) and swatches (dye packs) for armor, stillsuits, weapons, vehicles and placeables; unlock or lock each, searchable and filterable |
| Inventory | Slot grid of your backpack, worn gear, hand-held tools and other containers (select an item to edit it; click an empty backpack slot to add): change quantities (capped at the game's stack size), set durability, remove items, and add any of ~2,400 catalogued items to the backpack (big amounts are split into stacks) |
| Backups | List, create and restore backups |

## Safety

* Edits are made on a temporary copy; `game.db` is only replaced when you press **Write to game**.
* Before every write the **whole save folder is copied** to `backups/<timestamp>_before_write/`.
* The new `game.db` is decoded again before it replaces the old one, SQLite's integrity check must pass, and
  the write is refused if the game is running or if `game.db` changed on disk since you opened it.
* To undo: **Backups → Restore** (game closed), or copy a backup folder's contents back over the save folder.
* `backups/` holds copies of your real save (including your account id). It is listed in `.gitignore`; never share it.

## Tested vs assumed

**Tested in the game by the author** (single-player save, one game version): every editing feature in the
table above works: wallet and tech points, level and skill points, skills, specializations, recipes, building sets,
skins and swatches, and inventory edits (change amounts and durability, remove, add new items). Game updates can
change the save layout or add content, so keep your backups and treat a new game version as untested.

Also verified against a real save and the in-game screens:
* Solari = currency 0, House Script = currency 1; LVL = total skill points + 1; tech points; the Crafting track is track 1.
* Specialization XP curve (identical for all five tracks) matches the save exactly.
* Writing, re-reading and the integrity check (`python tools/selftest.py <game.db>`, runs on a copy), covering every area.
* The container codec re-encodes **all 315 blobs of a real save byte-for-byte** (`python tools/roundtrip_fmt.py <game.db>`).
* Recipe grade = the recipe's "Grade Level" (`m_QualityLevel`); the craft count = `m_NumberOfRecipeUses`.
  A first version of this recipe edit (byte-level) was accepted by the game; the editor now produces
  byte-identical entries through the container codec.

**Limits and open points:**
* Inventory: new items copy the stat structs of a similar item already in your save (defaults otherwise). Items are only added to the backpack (not worn gear), the label of the "Quick-use gear" container is a guess, and base storage chests and vehicle inventories are not shown.
* Maximum ranks for skill nodes (keys and perks 1; attributes and abilities 3) are a reading of the in-game screens.
  The game's data tables are in an unversioned format that cannot be decoded without its type schema.
* Specialization tracks 2-5 are labelled Gathering / Exploration / Combat / Sabotage from the in-game row order.
  Only track 1 (Crafting) could be confirmed from the save.
* Unspent skill points are a separate counter in the save; the editor does not recompute them from ranks.
* Skill-node display names: abilities use the game's names where they could be matched; attribute nodes are
  labelled by tree and number because the game names them by effect, not by node.

## Data files

`data/` was generated from one game install with the helper scripts in `tools/` (see
[How it works](docs/HOW_IT_WORKS.md#6-the-data-catalogues)); the game's assets were converted with the
[retoc](https://github.com/trumank/retoc) extractor. It contains text from the game. After a big game patch the
catalogues may be missing new entries; the save itself is always read live, and entries already in your save that
the catalogue doesn't know are preserved.

## Development

* `python tools/selftest.py <game.db>`: full edit, write and re-read cycle on a **copy** of your save.
* `python tools/inspect_save.py <game.db>`: read-only summary of a save.
* `python run.py --save-root <folder>` (or the `DUNE_EDITOR_SAVE_ROOT` environment variable) points the editor at a
  test copy of `PlayerClientStorage`; `--port`, `--no-browser` are also available.
* No build step, no dependencies. See [How it works](docs/HOW_IT_WORKS.md#7-code-map) for the code map.

## License

MIT, see [LICENSE](LICENSE).
