# User guide

A step-by-step guide to the Dune: Awakening Save Editor. If you just want to get going, read
[Getting started](#1-getting-started) and [Writing your changes safely](#3-writing-your-changes-safely); the rest is
a reference you can dip into.

> **Unofficial fan tool.** Not affiliated with Funcom. It is meant for your own **offline / self-hosted
> single-player** save. Don't use it on an online character. Always keep a backup (the editor makes one for you).

---

## 1. Getting started

### What you need

* **Windows** with Dune: Awakening installed. The save location and the "is the game running?" check are
  Windows-specific (see [Other setups](#other-setups)).
* **Python 3.10 or newer.** Get it from <https://www.python.org/downloads/> and, in the installer, tick
  **"Add python.exe to PATH"**. Nothing else needs installing: the editor uses only Python's standard library.
* A browser (any modern one). The editor is a small web page served from your own PC.
* A save. Play the single-player game at least once so that it creates one.

### Start it

1. **Close Dune: Awakening completely**, including the solo server process. The editor refuses to write while the
   game is running (it can *read* while the game runs, but the game would overwrite your edits when it saves).
2. Download or clone this repository and open its folder.
3. **Double-click `start_editor.bat`.** (Or run `python run.py` in a terminal.)
4. Your browser opens at `http://127.0.0.1:8765`. If you have exactly one save it opens automatically; with
   several you pick one on the first screen.

The black console window is the editor's server. Keep it open while you use the editor; close it (or press
`Ctrl+C`) to stop it. The editor only listens on `127.0.0.1`, so it is not reachable from other computers.

### Where the editor looks for your save

```
%LOCALAPPDATA%\DuneSandbox\Saved\Cloud\PlayerClientStorage\<environment>\<account id>\game.db
```

Paste that into the Windows Explorer address bar to see it. Command-line options:

```
python run.py --port 9000                    # use another port (default 8765, the next 19 are tried if busy)
python run.py --no-browser                   # don't open the browser automatically
python run.py --save-root "D:\copy-of-saves" # search a different folder (must contain <env>\<account>\game.db)
```

---

## 2. How editing works (the important idea)

Every edit is **staged**. When you press **Apply** (or click on things in tabs that apply immediately, such as
Inventory), the change is made to a *temporary working copy* of your save inside the editor. **Nothing in your real
save changes until you press "Write to game"** at the bottom right.

* **Pending changes** (Overview tab) lists everything that differs from the save as it was when you opened it
  (or last wrote it).
* **Discard changes** (bottom bar) throws away all staged edits.
* **Write to game** puts them into the game's save file (see the next section).

Closing the editor with unwritten edits simply loses them; your save is untouched.

---

## 3. Writing your changes safely

When you press **Write to game**, the editor:

1. checks that **Dune: Awakening is not running** (it refuses otherwise);
2. checks that `game.db` has **not changed on disk** since you opened it (if the game saved in the meantime it
   refuses, so you don't overwrite newer progress; re-open the save and redo your edits);
3. runs SQLite's **integrity check** on the edited database;
4. makes a **full backup of the whole save folder** to `backups/<date>_<time>_before_write/` next to the editor;
5. builds the new `game.db`, **decodes it again** to prove it is readable, and only then replaces the old file.

### Undoing a write

* **Backups tab → Restore** next to the backup you want (game closed). The editor first takes another backup
  called `before_restore`, so a restore can itself be undone.
* Or do it by hand: close the game and copy the contents of the backup's save folder back over your save folder.

You can also press **Back up now** on the Backups tab at any time, for example before a big session.

> Backups are full copies of your save folder, including your account/Steam ID. They live in the editor's
> `backups/` folder, which is **excluded from git** so you can't publish them by accident. Don't share that folder.

---

## 4. The tabs

The header shows your character name, your Solari and House Script, and your level. The bar at the bottom shows
which file is open, a warning if the game is running, and the **Discard changes / Write to game** buttons.

### Overview

* **Hero card:** edit **Solari**, **House Script** (each 0 to 2,000,000,000) and **tech knowledge points**, then press
  **Apply wallet**. **Max** fills in the limit.
* **Collection tiles:** how much of each collection you have: building sets learned, skins and swatches unlocked,
  recipes known, skill nodes ranked, specialization levels, backpack slots used. Click a tile to open that tab.
* **Pending changes:** the list of staged edits with *Discard all* and *Write to game* buttons.
* **Character level and skill points:** your **level is total skill points + 1**. *Unspent skill points* is a
  separate counter in the save: set it to however many points you want to be able to spend in-game. *Total XP* is
  the XP counter.

### Skills

Pick a class (Trooper, Mentat, Planetologist, Bene Gesserit, Swordmaster) with the diamond buttons.

* **Click a node** to raise its rank; after the maximum it wraps back to 0. Filled pips show the current rank.
* **Tier 1 / 2 / 3** buttons toggle the tier unlocks; the capstone node sits at the top of each tree.
* **Max \<class\>** and **Clear \<class\>** rank every node of that class up or down in one go.
* Below the trees are the shared lists (abilities, perks, spice techniques) you can rank the same way.
* Changes are held until you press **Apply skill changes**; **Revert** drops them.

Maximum ranks are the editor's best reading of the game (keys and perks 1, attributes and abilities 3).

### Specializations

Five tracks (Crafting, Gathering, Exploration, Combat, Sabotage). For each:

* The **slider** sets the track level (0 to 100); the XP is filled in from the game's own XP curve.
* Click a **trait card** to own or un-own it. **All**, **Up to level** and **None** act on the whole track.
* Press **Apply specialization changes**.

Only the Crafting track label could be confirmed from a save; the names of the other four tracks come from the
in-game row order (the UI marks tracks whose mapping is unverified).

### Recipes

The known crafting recipes for Tier 6 weapons, armor, stillsuits and augmentations.

* Search and filter (by group or type), tick the recipes you want, then give each a **Grade** (1 to 5, the recipe's
  in-game "Grade Level") and **Know ×** (how many times you can craft it at that grade).
* The toolbar can set Grade / Know × on *all selected* at once, select everything shown, or clear the selection.
* Press **Apply**. Recipes you already know are marked **"You know: Grade 5 ×10"**.

### Building

All 276 building sets ("patents") in the game with their pieces. Tick a set to **learn** it, untick to forget it.
Sets are grouped (structure sets, stations and utilities, furniture and decor, lighting, store and event bundles)
with a progress bar per group and **Learn all / Forget all** buttons. Use search, the learned / not-learned
filters, or the group chips to narrow the list; **Pieces** expands what a set contains. Press **Apply**.

The "new piece" markers (advanced, at the bottom) are the pieces the game still flags as newly unlocked; you
normally never need to touch them.

### Skins & Swatches

Every skin (a mesh or material variant) and swatch (a dye pack) for armor and stillsuits, weapons, vehicles and
placeables, each with its slot (for example *Light armor › Feet*). Tick to unlock, untick to lock. Filter by
category chips, skins vs swatches, and unlocked vs locked; use **Unlock all / Lock all** per group or
**Unlock all shown** for the current filter. Press **Apply**. Hover a tile to see its internal id.

Some entries are store or event cosmetics that the game normally sells or hands out as rewards.

### Inventory

Your containers (backpack, worn gear, hand-held weapons and tools, quick-use gear, contract items, emotes) as
grids of slots. Everything here is staged immediately when you act on it.

* **Click an item** to open its panel: change the **amount** (− / + / typed value / Min, Half, Double, Full stack;
  limited to the item's real stack size), set **durability** with the slider (or **Repair fully**), or **Remove** it.
* **Click an empty backpack slot** (or *Add item…*) to add something: search all ~2,400 catalogued items, pick one,
  set the quantity and press **Add to backpack**. Amounts bigger than a stack are split over several slots.
* New items go to the **backpack only**. Equip them in the game.

### Backups

Lists the backups, lets you make a new one (**Back up now**), and restore an old one (**Restore**, with the game closed). See
[Writing your changes safely](#3-writing-your-changes-safely).

---

## 5. Troubleshooting

| What you see | What it means / what to do |
|---|---|
| "Python 3.10 or newer is required" | Install Python from python.org and tick *Add python.exe to PATH*, then start again. |
| "No Dune: Awakening save was found…" | Start the game once in single-player so it creates a save, then reload the page. If your saves live elsewhere, start with `--save-root "<folder>"`. |
| Browser doesn't open | Open the address printed in the console window (usually `http://127.0.0.1:8765/`). If the port was busy it may be 8766 and up. |
| "Dune: Awakening is running… Close it completely" | Quit the game, including the solo server process (check Task Manager for `DuneSandbox`), then press **Write to game** again. |
| "game.db changed on disk since it was opened" | The game saved after you opened the save. Open it again (reload the page / press **Discard changes**) and redo your edits so you don't overwrite newer progress. |
| "save failed its integrity check" | The file you opened is damaged. Restore one of your own backups. |
| Edits don't show up in the game | Did you press **Write to game** (not just *Apply*)? Was the game closed while writing? If the game syncs saves to a cloud, it may have restored its own copy; check the in-game load screen. |
| The game crashes or refuses the save after an edit | Restore the `before_write` backup (Backups tab). Please open an issue and say which tab and edit it was; every feature has worked in the author's tests, so a game update or an unusual save is the likely cause. |
| "unlocked customisation list not found…" or similar | The save has a layout the editor doesn't know (for example after a big game update). Nothing was changed. Open an issue. |

---

## 6. FAQ

**Is this safe?** It is careful (backups, integrity check, re-decode, refuses while the game runs), but it edits a
file the game owns. Every editing feature has been **tested in-game by the author**, but only on one save and one
game version. After a game update, or if your save is unusual, make one small change first, load the game and
check before making large ones. See "Tested vs assumed" in the [README](../README.md).

**Will it get me banned?** Only use it on offline / self-hosted single-player saves. Don't use it with online play.

**Does it send my save anywhere?** No. It runs on your PC and listens on `127.0.0.1` only. Nothing is uploaded.

**The game got a patch and something looks off.** The catalogues in `data/` come from one game version
(see [HOW_IT_WORKS](HOW_IT_WORKS.md#6-the-data-catalogues)); a patch can add items the editor doesn't list yet.
Your save is always read live, and unknown entries already in your save are preserved when you write.

**Can I run it on Linux / macOS?** See below.

### Other setups

The editor is plain Python, but two things are Windows-specific: the default save folder
(`%LOCALAPPDATA%`) and the check that the game isn't running (it uses `tasklist`; on other systems that check is
skipped, so *you* must make sure the game is closed). If you run the game through Proton or on a copy of a save,
point the editor at it with `--save-root`. Use at your own risk.

---

## 7. Reporting a problem

Open an issue on the repository and include: what you clicked, the exact message shown, and your Python version
(`python --version`). **Don't attach your save or backups** (they contain your account id). If you want to
attach diagnostics, `python tools/selftest.py "<path to game.db>"` runs a full edit-write-read cycle on a *copy* and
prints only levels and counts.
