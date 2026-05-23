# Tests

Automated tests for the Godot client. Uses **GUT** (Godot Unit Test) — the de-facto Godot 4 testing framework.

> [!important] GUT is **not** included in this repo yet.
> Install it once via the Asset Library before running any tests. See "Install" below.

## Why we have this folder before any real tests exist

The procedural [[Levels & Environments|level generator]] (Phase 4a) MUST be deterministic — server-generated `LevelData` has to be byte-identical to every client's `LevelData` for the same `(env_id, difficulty, seed)`. That property is exactly the kind of thing a one-line test catches and a manual playthrough doesn't.

Locking in test infrastructure now means Phase 4a writes the test alongside the generator instead of "we'll add tests later."

## Install

### Editor (one-click)

1. Open the Godot editor
2. **AssetLib** tab (top of editor)
3. Search: `Gut`
4. Pick **Gut** by Butch Wesley
5. Download → Install — Godot puts it in `addons/gut/`
6. **Project → Project Settings → Plugins** → enable **Gut**
7. Restart the editor

A new **Gut** panel appears at the bottom. Use it to run tests.

### CLI / headless

After install, run from PowerShell:

```powershell
& "C:\Program Files (x86)\Godot\Godot_v4.6.2-stable_win64_console.exe" `
    --headless `
    --path godot `
    -s addons/gut/gut_cmdln.gd `
    -gdir=res://tests `
    -gexit
```

Add this as a `scripts/test.ps1` once we have real tests.

## File conventions (once GUT is in)

- Test files live in this `tests/` folder
- Filename pattern: `test_*.gd`
- Test class: `extends "res://addons/gut/test.gd"` (or `extends GutTest` once registered)
- Test methods: `func test_*() -> void`
- One file per unit under test (e.g., `test_level_generator.gd`, `test_environment_registry.gd`)

Example for the future generator:

```gdscript
extends GutTest

func test_generator_is_deterministic() -> void:
    var env := preload("res://resources/environments/sky.tres")
    var a := LevelGenerator.generate(env, 5, 12345)
    var b := LevelGenerator.generate(env, 5, 12345)
    assert_eq(a.slots.size(), b.slots.size())
    for i in a.slots.size():
        assert_eq(a.slots[i].position, b.slots[i].position)
        assert_eq(a.slots[i].chosen_element_id, b.slots[i].chosen_element_id)
```

## Vault link

Full reasoning lives in the [[Roadmap]] (Phase 4a setup) and the [[Levels & Environments]] note's "Determinism rules" section.
