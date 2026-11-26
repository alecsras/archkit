---
name: architectural-build
description: Design buildings (floor plans, 3D walkthroughs, game levels) that are architecturally sound and verified - no wall gaps, floating objects or blocked paths, code-checked.
---

# Architectural build (verified)

Use this whenever someone asks for a floor plan, building layout, interior layout, 3D walkthrough, or a game level that is a building. Any building type (house, apartment, motel/hotel, office, retail, mixed-use). Default code basis: IBC 2021 + 2010 ADA (US) unless the person names another.

The promise this skill keeps: **nothing is delivered until the validator reports 0 errors**, and every 2D/3D output is generated from the same validated model, so the pictures cannot drift from what was checked.

## Non-negotiable rules
1. **One model, everything derived.** The building is a single `archkit` model (walls, openings, spaces, objects, devices, stairs, elevators). Plans and the 3D walkthrough are rendered from it by `archkit.render`. Never hand-place geometry in a renderer, never edit an SVG/HTML output to fix something - fix the model and re-render.
2. **Rooms are traced, not typed.** Create spaces with `b.space(level, seed_point, ...)`; the polygon is traced from the walls. A gap in the walls shows up as a leak error. Only balconies/porches/walkways use `open_space(rect)`.
3. **No typed heights.** Ceiling devices take the room's ceiling height; wall devices must sit on a wall face; furniture sits on the floor or `on=` a host. Never write a z value.
4. **Walls join exactly.** Draw centerlines on a grid; every wall end must land on another wall's centerline (corner or T). Split a wall where another crosses it.
5. **Place furniture with `against=` + `along=`** so it is flush to a wall, and respect each object's clearance zones (catalog `OBJ`). Chairs are movable; everything else blocks.
6. **Validate -> fix -> repeat** until 0 errors. Every remaining warning gets a one-line justification in the delivery notes (e.g. a plumbing stack offset over a lobby).
7. **Visual QA after validation.** Render, screenshot the plans and 3D from standard viewpoints, and look. If you see a defect the validator missed, first add a check for it to `validate.py` (so it can never recur), then fix the model.

## Workflow
1. **Brief -> program.** List spaces with type, target size and count, number of levels, floor-to-floor height, occupancy (R-1 lodging, R-2 apartments, R-3 house, B office, M retail, A assembly), sprinklered yes/no, accessible yes/no. For a house, set `residential_interior=True` (relaxes commercial door/route rules inside the dwelling). Confirm with the person only if the request is ambiguous or expensive.
2. **Set up the library** (first use in a session): `git clone --depth 1 https://github.com/alecsras/archkit.git` then `pip install shapely --break-system-packages` and work inside `archkit/` (so `python -m archkit.validate` resolves). If GitHub is unreachable, ask the person to attach `archkit.zip`. Do not rewrite the library from memory - it is the tested version.
3. **Grid & structure first.** Pick a structural grid and bearing strategy (e.g. floor joists span to exterior + corridor walls). Bearing walls, shafts (stairs, elevators, plumbing chases) and wet walls must stack level to level - the validator checks this.
4. **Model** in a script `build_<name>.py` (copy `examples/inn.py`, a 2-story 9-key inn that passes with 0 errors; `examples/defects.py` injects 13 defects that must all be caught). Order: levels -> walls -> openings -> `space()` seeds -> `b.trace()` -> objects -> devices -> stairs/elevators -> `b.save()`.
5. **Validate:** `python -m archkit.validate model.json --json report.json`. Read every error; fix the model; repeat. Typical fixes: move a door hinge or swing, shift furniture with `along=`, split a crossing wall, widen a bath, put a stair flush to its enclosure walls.
6. **Render:** `python -m archkit.render model.json out/ --report report.json` -> `plan_<level>.svg` per level (issues circled if any remain) and `walkthrough.html` (first-person, WASD/mouse/touch, doors with E, elevator buttons, day/night).
7. **QA the renders:** rasterize plans (`rsvg-convert`) and screenshot the walkthrough headless (three.js r128 from cdnjs; for offline testing `npm pack three@0.128.0` and point the script src at the local `build/three.min.js`). Check: entrance, each room type, stairs top and bottom, corridor, exterior. `window.__walk.step(dt, mx, my)` lets you simulate walking at a fixed timestep (headless frame rates are too low for real-time tests); confirm you can enter, climb every stair to every level, reach every room, and that guards stop falls.
8. **Deliver:** the validation summary (PASS line + count of checks + justified warnings), the plans, and the walkthrough (publish as an artifact with its HTML; it is self-contained apart from three.js on cdnjs). Mention what the model does not cover (see Limits).

## What the validator checks (codes)
- **Geometry G-**: rooms enclosed (leak detection), wall ends joined, no overlapping/crossing walls, openings fit their wall with jambs, heads below ceiling, openings don't overlap, spaces don't overlap, upper floors supported by the floor below, bearing walls stack, elevator shafts stack.
- **Placement P-**: every object inside its room (nothing through walls), wall-mounted items on a wall face, `on=` items on their host, no two objects in the same volume, every device inside its room / on a wall face at a mount height below the ceiling, every object's required clearances free of walls and other objects.
- **Circulation C-**: doors connect two places (no door to a drop), door clear width (32"), swing arcs hit nothing, ADA maneuvering clearances at public/accessible doors and a clear approach at every other door, exterior landing clear, furniture never splits a room or blocks a door or a fixture on a 36" route, corridor widths (36"/44"), every room reachable from the street, stairs (riser/tread/width/landing, risers add up, enclosure, headroom opening above, floor to step onto at top and bottom, no open edges), elevator car size (ADA / stretcher at 4+ stories).
- **Accessibility A-**: accessible rooms reachable without stairs, 60" turning circle, water-closet centerline 16-18", 60x56 WC clearance, no protruding objects in routes, accessible guest-room count (ADA 224).
- **Code K-**: habitable room size, ceiling heights (and room left for structure), emergency escape windows when unsprinklered, exits required by occupant load, exit separation (1/2 or 1/3 diagonal), travel distance (grid search through real walkable space).
- **MEP M-**: required devices per room type (light, smoke alarm, exhaust fan, GFCI, receptacles), plumbing fixtures near a wet wall, wet walls stacking.

## Modeling cheat sheet
- Units feet; +x east, +y south (screen down). Wall `t`: exterior 0.67, interior 0.5. Door `into=` is any point on the side the leaf swings toward; `hinge='start'|'end'` along the wall's a->b direction; `kind` swing|double|pocket|slide|cased.
- Accessible bath: >= 8' x 8.5' interior; `toilet_ada` against a side wall with centerline 17" off it (`along = wall_face -/+ 1.42`); `lavatory_ada` outside the 60x56 zone; pocket door.
- Standard bath: 5' x 7.5' interior with a 5' tub across one end, toilet and lav on the back wall.
- U-stair: `b.stair_u(id, from, to, x, y, width, up='N')` where (x, y) is the bottom-left corner of the footprint with 'up' pointing to the top of the page; make the two flights + 4" gap span the enclosure wall-to-wall and put the landing against the far wall, leaving an approach area >= flight width at the start.
- Elevator: shaft walls + an `elevator` space on every served level with the same inner rectangle, a `slide` door, and `b.elevator(id, levels, rect)`.
- Every room type needs its devices (see `SPACE[...]["need"]`). Wall devices go exactly on the face: e.g. x = the room polygon's min-x for the west wall.

## Limits (say so when delivering)
Schematic accuracy, not construction documents: no structural calculations, no duct/pipe sizing, no energy code, no local amendments. Curved walls are approximated with straight segments. A licensed architect/engineer must review anything that will be built.

## Library
Lives at https://github.com/alecsras/archkit: `archkit/model.py` (model + catalogs), `validate.py` (all checks; exit 1 on errors), `scene.py` (derived 3D scene), `render.py` (plans + walkthrough), `walk_template.html` (three.js player), `examples/`. After changing a check, re-run `python examples/defects.py` and `python examples/inn.py` to confirm nothing regressed.
