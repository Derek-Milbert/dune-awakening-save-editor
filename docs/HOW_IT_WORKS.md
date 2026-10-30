# How the save editor works

This document explains what is inside a Dune: Awakening single-player save, how the editor reads and changes it
safely, where the catalogue data comes from, and how the code is organised. It is written for curious players and
for anyone who wants to contribute. For day-to-day usage see the [User guide](USER_GUIDE.md).

Everything here was worked out by inspecting a real save and the game's own data files. Where something is an
assumption rather than a verified fact, it says so (see also [Tested vs assumed](../README.md#tested-vs-assumed)).

---

## 1. The big picture

```
 browser (web/app.js, app.css)              Python (dune_editor/)                         your PC
 ┌───────────────────────────┐   JSON    ┌───────────────────────────┐        ┌───────────────────────────┐
 │ tabs, forms, tiles, grids │ <───────> │ server.py  (127.0.0.1)    │        │ %LOCALAPPDATA%\DuneSandbox │
 └───────────────────────────┘  /api/*   │   │                       │ read   │  ...\<env>\<account>\      │
                                         │   ├ editors.py  (the edits)│ <───── │      game.db  (the save)   │
                                         │   ├ changes.py  (summary,  │        └───────────────────────────┘
                                         │   │              diff)     │ write        ▲
                                         │   ├ fmt.py      (codec)    │ ─────────────┘ (only on "Write to game")
                                         │   └ savefile.py (open,     │        ┌───────────────────────────┐
                                         │       backup, write)       │ ─────> │ backups/<time>_before_write│
                                         └───────────────────────────┘        └───────────────────────────┘
```

* The editor is a tiny **local web server** (Python standard library only) plus a **single-page web UI**. It binds to
  `127.0.0.1`, rejects requests whose `Host` header isn't `127.0.0.1`/`localhost`, and requires a custom
  `X-Dune-Editor: 1` header on every change, so a random web page you visit can't make it modify your save.
* All edits happen on a **temporary working copy** of the database. The real `game.db` is only touched by
  **Write to game**, which makes a backup first.
* One global lock serialises requests, so two browser tabs can't interleave edits.

---

## 2. The save file

### Container

`game.db` is **not** a plain SQLite file. It is:

| bytes | meaning |
|---|---|
| 0-3 | `u32` little-endian, always `1` (a format flag) |
| 4-7 | `u32` little-endian, size of the data once decompressed |
| 8-end | a **zlib** stream whose content is an ordinary **SQLite 3 database** |

`savefile.py` (`read_db` / `pack_db`) unwraps and re-wraps this. The editor always checks the magic string
`SQLite format 3` after decompressing and decodes the file again before replacing the original.

### Where each editable thing lives

The database has about 95 tables. These are the ones the editor uses:

| Edit | Where it is stored |
|---|---|
| Character identity | `player_state` (name, controller id, pawn id) and `accounts` |
| Solari, House Script | table `player_virtual_currency_balances` (currency 0 = Solari, 1 = House Script) |
| Specialization levels and XP | table `specialization_tracks` (`track_type` 1-5) |
| Specialization traits ("keystones") | tables `purchased_specialization_keystones` + `specialization_keystones_map` |
| Building sets learned | table `building_progression_learned_building_sets` (and `building_progression_new_buildable_pieces` for the "new" markers) |
| Inventory | tables `inventories` (one per container, owned by the player pawn `actor_id`) and `items` (one row per stack); new item ids come from `items_id_sequencer` |
| Skills, skill points, XP, tech points, known recipes, unlocked skins and swatches | **inside binary blobs** on the character: `actors.properties` for the player pawn, described next |

So some edits are simple SQL on ordinary tables, and the rest need the blob codec.

### The property container (`dune_editor/fmt.py`)

Character state is stored in a compact tagged format: a tree of strings, numbers, booleans, **structs** (key/value
lists) and **arrays**. Every value starts with a tag byte whose low nibble gives the type and whose high nibble
(or following bytes) gives the payload length. Numbers and floats are stored as **decimal text**. Structs and arrays
carry their own byte size, so changing the size of anything inside requires recomputing every enclosing size.

`fmt.decode()` turns a blob into `Node` objects (`s` string, `i` int, `f` float, `b` bool, `S` struct, `A` array);
`fmt.encode()` writes them back, recomputing all sizes. Two properties make this safe:

* **Lossless.** Numbers keep their original text, so decode → encode returns the *identical* bytes.
  `python tools/roundtrip_fmt.py <game.db>` proves it on every blob of a real save (all 315 blobs matched
  byte-for-byte when this was written).
* **No-op edits change nothing.** The self-test applies an "edit" that doesn't actually change anything and checks the
  bytes are identical, so merely opening and writing never alters data you didn't touch.

An edit is then: decode the pawn blob → find the struct/array → change it → encode → store.
For example, unlocked skins live at
`CustomizationLibraryActorComponent → m_UnlockedCustomizationSerializableList → m_UnlockedCustomizationIds`
(an array of structs holding a `m_CustomizationId` string), and known recipes at
`CraftingRecipesLibraryActorComponent → m_KnownItemRecipes`.

### Items

An item stack is a row in `items`: `template_id` (e.g. `Ammo`, `Stillsuit_Unique_Armored_06_Top`), `stack_size`,
`position_index` (the slot), `acquisition_time`, `is_new`, `quality_level` and a JSON text column `stats`:

```json
{"FItemStackAndDurabilityStats":[[],{"CurrentDurability":94.17}], "FCustomizationStats":[[],{"SwatchId":"..."}]}
```

In `stats` a **missing field means its default**: full durability is simply `{}`, which is why repairing an item
*removes* `CurrentDurability`. Different item kinds carry extra stat structs (weapon, clothing, fillable...). When the
editor creates an item it copies the *set* of stat structs from an item of the same kind already in your save
and resets all values, because the game expects those structs to exist. Items added this way were accepted by the game in
testing.

---

## 3. What happens when you press "Write to game"

`Save.write()` in `savefile.py`:

1. refuse if a `DuneSandbox*` process is running (checked with `tasklist`);
2. refuse if `game.db`'s modification time differs from when it was opened;
3. commit and run `PRAGMA integrity_check` on the working copy;
4. copy the **entire save folder** to `backups/<timestamp>_before_write/` and verify the file counts match;
5. pack the database (`pack_db`), write it to `game.db.editor_tmp`, **decode that file again**, and only then
   `os.replace` it over the real `game.db` (an atomic swap);
6. re-open the new file so the UI shows what is actually on disk.

If any step fails, the original file is untouched.

---

## 4. Reading the UI's data: the API

All endpoints live under `/api/` on the local server (`server.py`). `GET` reads, `POST` stages a change.

| Endpoint | Purpose |
|---|---|
| `GET /api/state` | saves found, which is open, dirty flag, is the game running, character overview |
| `POST /api/open` | open one of the detected saves (must be one that was found; arbitrary paths are refused) |
| `GET /api/summary` | collection progress for the Overview tiles |
| `GET /api/changes` | the **Pending changes** list: a snapshot of the original save (kept as an untouched copy) compared with the working copy (`changes.py`) |
| `GET/POST /api/skills`, `/api/spec`, `/api/recipes`, `/api/building`, `/api/customization`, `/api/inventory` | read the current state + catalogue / stage an edit |
| `POST /api/currency`, `/api/tech` | wallet and tech points |
| `POST /api/write`, `/api/discard` | write to the game / drop staged edits |
| `GET /api/backups`, `POST /api/backup`, `/api/restore` | backups |

Every `POST` validates its input (value ranges, known ids, name patterns) and raises a readable error that the UI
shows as a message; inventory changes are applied **all or nothing** (SQLite savepoint).

---

## 5. How a few edits work

* **Level.** The in-game level is `total skill points + 1`. The editor stores the total and the unspent counter
  separately because that's how the save keeps them; it does **not** recompute unspent points from ranks.
* **Specialization level → XP.** XP is derived from the game's own curve (`data/xp_curve.json`, identical for all
  five tracks and matching a real save exactly), so the level you set shows correctly in-game.
* **Recipes.** Each known recipe is a struct with the recipe id, a grade (`m_QualityLevel`) and a use counter
  (`m_NumberOfRecipeUses`). The editor writes entries byte-identical to ones the game wrote.
* **Skins and swatches.** Both share one list of ids; unlocking adds an id, locking removes it. Ids that aren't in
  the catalogue are kept untouched.
* **Building sets.** Learning a set adds its name to the learned-sets table. The game then grants its pieces
  (confirmed in-game; the save's existing pieces are all covered by its learned sets).
* **Inventory.** Quantities are capped at the item's stack size; adding splits into stacks and uses the first free
  slots (or the slot you clicked); new ids are taken from `items_id_sequencer` and the counter is advanced.

---

## 6. The data catalogues

The editor needs to know *what exists* in the game (names, stack sizes, which pieces a set contains...). That
information is **not in the save**; it is in the game's data files. The JSON files in `data/` were generated from one
game install with scripts in `tools/`:

| File | Content | Built by |
|---|---|---|
| `data/skills.json` | class skill nodes and shared abilities / perks | `tools/build_skills_data.py` (needs a save + `_work/loc_skills.json`) |
| `data/recipes.json` | Tier 6 recipes with names and where they drop | built from the crafting-recipe table, loot tables and item text |
| `data/building.json` | 276 building sets and their 1,034 pieces | `tools/build_building_data.py` |
| `data/customization.json` | 804 skins and swatches | `tools/build_customization_data.py` |
| `data/items.json` | ~2,400 items (name, category, stack size, tier...) | `tools/build_item_data.py` |
| `data/xp_curve.json` | specialization XP per level | measured from the game |

The game ships its assets as Unreal Engine IoStore containers (`*.utoc` / `*.ucas`). They were converted to
ordinary `.uasset` files with the open-source tool [retoc](https://github.com/trumank/retoc)
(`retoc to-legacy -f <filter> <Paks folder> <out>`), and the `tools/build_*.py` scripts read the resulting data
tables directly (their docstrings say exactly which files and filters to use).

**You do not need any of this to use the editor**; the generated JSON is included. You only need it to refresh the
catalogues after a game patch. The text in these files belongs to the game's publisher.

---

## 7. Code map

```
run.py                  entry point (argument parsing, starts the server)
start_editor.bat        Windows launcher (finds Python, checks the version)
dune_editor/
  savefile.py           find saves, open/pack game.db, backups, the safe write
  fmt.py                codec for the property container (decode/encode, Node tree)
  editors.py            every read/edit: currency, skills, specializations, recipes,
                        customisation, building, tech points, inventory
  changes.py            snapshot + diff for the Overview dashboard and Pending changes
  server.py             HTTP server, routing, request validation, global lock
web/
  index.html, app.css   page shell and the neumorphic (soft UI) CHOAM theme
  app.js                the UI: one render function per tab, no framework, no build step
data/                   catalogues (see section 6)
tools/                  catalogue builders, selftest.py, roundtrip_fmt.py, inspect_save.py
_work/                  small inputs used by tools/build_skills_data.py
docs/                   this documentation
```

There is **no build step and no third-party dependency**: edit a file, reload the page (or restart for Python
changes).

### Testing

* `python tools/selftest.py "<path to game.db>"` copies your save to a temp folder, performs edits in every area,
  writes, re-opens and checks everything read back correctly. It never touches your real save and prints only
  counts.
* `python tools/roundtrip_fmt.py "<path to game.db>"` decodes and re-encodes every blob and checks byte equality.
* `python tools/inspect_save.py "<path to game.db>"` is a read-only summary.
* To try the UI without risking anything: copy a `game.db` into a throw-away folder shaped like
  `<root>\<env>\<account>\game.db` and start `python run.py --save-root "<root>"`.

### Contributing

Bug reports and pull requests are welcome. Please test against a copy of a save, keep the UI's neumorphic style
(shadow variables in `app.css`), never commit a save or `backups/`, and say honestly what you did and didn't verify
in the game.

---

## 8. Known limits

* The editing features were tested in-game by the author on one save and one game version. A game update can change
  the save layout or add content the catalogues don't list yet.
* Specialization tracks 2-5 are labelled from the in-game row order and aren't confirmed from a save.
* Maximum ranks for skill nodes are a reading of the game's screens (the game's own data tables use an unversioned
  format that needs its type schema to decode).
* Base storage chests and vehicle inventories are not shown.
* Windows-only conveniences: default save path and the "game running" check.
