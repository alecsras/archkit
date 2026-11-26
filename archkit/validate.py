"""archkit.validate - every check a finished building must pass.
Usage:  python -m archkit.validate model.json [--json report.json]
Exit code 1 if any ERROR. Warnings must be reviewed and either fixed or justified in the delivery notes.
"""
import sys, json, math, heapq
from collections import defaultdict
from shapely.geometry import Polygon, Point, LineString, box as sbox
from shapely.ops import unary_union
from shapely.prepared import prep
from .model import load, OBJ, SPACE, OPP, TOL, flight_rect, under_stair

HEAD = 6.67        # 80" headroom
ROUTE = 1.5        # half of 36" accessible route
TURN = 2.5         # radius of 60" turning circle


class Report:
    def __init__(s): s.items, s.passed = [], defaultdict(int)
    def err(s, code, msg, at=None, level=None): s.items.append(dict(sev="ERROR", code=code, msg=msg, at=at, level=level))
    def warn(s, code, msg, at=None, level=None): s.items.append(dict(sev="WARN", code=code, msg=msg, at=at, level=level))
    def ok(s, code, n=1): s.passed[code] += n
    @property
    def errors(s): return [i for i in s.items if i["sev"] == "ERROR"]


def P2(p): return [round(p[0], 2), round(p[1], 2)]


def validate(b):
    R = Report(); d = b.d
    b.trace()
    lv = {L["id"]: L for L in d["levels"]}
    order = sorted(d["levels"], key=lambda L: L["elev"])
    sp = {s["id"]: s for s in d["spaces"]}
    W = {w["id"]: w for w in d["walls"]}

    # ===== G: GEOMETRY ===================================================
    for t in d.get("_trace", []):
        s = sp[t["space"]]; R.err("G-ROOM-ENCLOSED", f"{s['name']}: {t['problem']}", P2(s["seed"]), s["level"])
    for s in d["spaces"]:
        if s["poly"]: R.ok("G-ROOM-ENCLOSED")
    ends_by_level, unions = {}, {}
    for L in d["levels"]:
        ends = b.wall_ends(L["id"]); ends_by_level[L["id"]] = ends
        ws = [w for w in d["walls"] if w["level"] == L["id"]]
        unions[L["id"]] = unary_union([b.wall_body(w, ends)[0] for w in ws]) if ws else Polygon()
        for w in ws:
            if math.dist(w["a"], w["b"]) < 0.25: R.err("G-WALL-SHORT", f"wall {w['id']} shorter than 3\"", P2(w["a"]), L["id"]); continue
            for e in ("a", "b"):
                if not ends[(w["id"], e)] and not w.get("free_end"):
                    R.err("G-WALL-JOIN", f"wall {w['id']} end {e} is not joined to any wall (gap / dangling end)", P2(w[e]), L["id"])
                else: R.ok("G-WALL-JOIN")
        # overlapping collinear walls
        for i, w in enumerate(ws):
            li = LineString([w["a"], w["b"]])
            for v in ws[i + 1:]:
                lj = LineString([v["a"], v["b"]]); inter = li.intersection(lj)
                if inter.length > TOL: R.err("G-WALL-OVERLAP", f"walls {w['id']} and {v['id']} overlap along {inter.length:.2f}'", P2(inter.coords[0]), L["id"])
                elif li.crosses(lj): R.err("G-WALL-CROSS", f"walls {w['id']} and {v['id']} cross without a joint", P2(inter.coords[0]) if inter.geom_type == "Point" else None, L["id"])
                else: R.ok("G-WALL-OVERLAP")
    # openings
    by_wall = defaultdict(list)
    for o in d["openings"]:
        w = W.get(o["wall"])
        if not w: R.err("G-OPEN-HOST", f"opening {o['id']} has no host wall"); continue
        by_wall[w["id"]].append(o)
        L = math.dist(w["a"], w["b"]); lev = lv[w["level"]]
        wh = w["h"] or lev["height"]
        if o["offset"] < 0.33 - 1e-6 or o["offset"] + o["width"] > L - 0.33 + 1e-6:
            R.err("G-OPEN-FIT", f"{o['kind']} {o['id']} runs past its wall or leaves < 4\" jamb", P2(opening_center(b, o)), w["level"])
        else: R.ok("G-OPEN-FIT")
        clg_lim = lev["ceiling"]
        if o["sill"] + o["height"] > min(wh, clg_lim + 0.01) + 1e-6:
            R.err("G-OPEN-HEAD", f"{o['kind']} {o['id']} head at {o['sill'] + o['height']:.2f}' is above the ceiling ({clg_lim}')", P2(opening_center(b, o)), w["level"])
        else: R.ok("G-OPEN-HEAD")
    for wid, os_ in by_wall.items():
        os_ = sorted(os_, key=lambda o: o["offset"])
        for a, c in zip(os_, os_[1:]):
            if a["offset"] + a["width"] > c["offset"] - 0.33:
                R.err("G-OPEN-OVERLAP", f"openings {a['id']} and {c['id']} overlap or share < 4\" of wall", P2(opening_center(b, c)), W[wid]["level"])
            else: R.ok("G-OPEN-OVERLAP")
    # spaces must not overlap; open spaces must not overlap walls
    for L in d["levels"]:
        ss = [s for s in d["spaces"] if s["level"] == L["id"] and s["poly"]]
        for i, s in enumerate(ss):
            ps = b.spoly(s["id"])
            if s.get("open") and ps.intersection(unions[L["id"]]).area > 0.05:
                R.err("G-SPACE-IN-WALL", f"{s['name']} overlaps walls", P2(s["seed"]), L["id"])
            for t in ss[i + 1:]:
                if ps.intersection(b.spoly(t["id"])).area > 0.05:
                    R.err("G-SPACE-OVERLAP", f"{s['name']} overlaps {t['name']}", P2(s["seed"]), L["id"])
                else: R.ok("G-SPACE-OVERLAP")
    # stacking: every upper-level space must sit over floor area of the level below (or be open/exterior)
    for i in range(1, len(order)):
        below = unary_union([b.spoly(s["id"]) for s in d["spaces"] if s["level"] == order[i - 1]["id"] and s["poly"]] + [unions[order[i - 1]["id"]]])
        for s in d["spaces"]:
            if s["level"] != order[i]["id"] or not s["poly"]: continue
            un = b.spoly(s["id"]).difference(below.buffer(0.05)).area
            if un > 1.0 and SPACE[s["type"]].get("exterior") is None:
                R.err("G-UNSUPPORTED", f"{s['name']} hangs {un:.0f} SF beyond the floor below (no structure)", P2(s["seed"]), s["level"])
            else: R.ok("G-UNSUPPORTED")
    # bearing walls stack
    for i in range(1, len(order)):
        lo = [LineString([w["a"], w["b"]]) for w in d["walls"] if w["level"] == order[i - 1]["id"] and w["bearing"]]
        lou = unary_union(lo).buffer(0.3) if lo else Polygon()
        for w in d["walls"]:
            if w["level"] != order[i]["id"] or not w["bearing"]: continue
            ls = LineString([w["a"], w["b"]]); cov = ls.intersection(lou).length / ls.length
            if cov < 0.95: R.err("G-BEARING-STACK", f"bearing wall {w['id']} is {100 * (1 - cov):.0f}% unsupported below - add transfer beam or move it", P2(w["a"]), w["level"])
            else: R.ok("G-BEARING-STACK")
    # vertical shafts stack
    for e in d["elevators"]:
        r = sbox(*e["rect"])
        for lid in e["levels"]:
            hit = [s for s in d["spaces"] if s["level"] == lid and s["type"] == "elevator" and s["poly"] and b.spoly(s["id"]).symmetric_difference(r).area < 0.5]
            if not hit: R.err("G-SHAFT-STACK", f"elevator {e['id']}: no matching elevator space on {lid} (shaft must stack exactly)", P2(r.centroid.coords[0]), lid)
            else: R.ok("G-SHAFT-STACK")
        x0, y0, x1, y1 = e["rect"]; dims = sorted([x1 - x0, y1 - y0])
        need = (4.25, 5.67) if len(e["levels"]) < 4 else (4.42, 7.0)
        if dims[0] + 1e-6 < need[0] or dims[1] + 1e-6 < need[1]:
            R.err("C-ELEV-SIZE", f"elevator {e['id']} car {dims[0]:.2f}x{dims[1]:.2f}' < required {need[0]}x{need[1]}' ({'stretcher' if need[1] == 7 else 'ADA 407'})", P2(r.centroid.coords[0]))
        else: R.ok("C-ELEV-SIZE")

    # ===== P: PLACEMENT ===================================================
    objs_by_level = defaultdict(list)
    for o in d["objects"]:
        s = sp.get(o["space"])
        if not s or not s["poly"]: R.err("P-OBJ-SPACE", f"{o['label']} placed in an untraced space", [o["x"], o["y"]]); continue
        lid = s["level"]; o["_level"] = lid; objs_by_level[lid].append(o)
        fp = b.footprint(o); ps = b.spoly(s["id"])
        if o["mount"] == "wall":
            # must be flush to a wall face of its space and fully inside the space
            if not ps.buffer(0.02).contains(fp): R.err("P-OBJ-INSIDE", f"{o['label']} pokes outside {s['name']} (through a wall)", P2(fp.centroid.coords[0]), lid)
            elif fp.distance(ps.exterior) > 0.05: R.err("P-WALL-MOUNT", f"{o['label']} is wall-mounted but not on a wall face (floating)", P2(fp.centroid.coords[0]), lid)
            else: R.ok("P-OBJ-INSIDE")
            continue
        if not ps.buffer(0.02).contains(fp):
            R.err("P-OBJ-INSIDE", f"{o['label']} pokes outside {s['name']} (into a wall or another room)", P2(fp.centroid.coords[0]), lid)
        else: R.ok("P-OBJ-INSIDE")
        if o.get("on"):
            host = next((h for h in d["objects"] if h["id"] == o["on"]), None)
            if not host or not b.footprint(host).buffer(0.02).contains(fp): R.err("P-ON-HOST", f"{o['label']} is not fully on its host (floating)", P2(fp.centroid.coords[0]), lid)
            else: R.ok("P-ON-HOST")
    def zr(o):
        lev = lv[o["_level"]]
        if o.get("on"):
            host = next(h for h in d["objects"] if h["id"] == o["on"]); z0 = zr(host)[1]
        else: z0 = o["elev"]
        return (z0, z0 + o["h"])
    for lid, os_ in objs_by_level.items():
        for i, a in enumerate(os_):
            fa = b.footprint(a); za = zr(a)
            for c in os_[i + 1:]:
                if a.get("on") == c["id"] or c.get("on") == a["id"]: continue
                zc = zr(c)
                if za[1] <= zc[0] + 1e-6 or zc[1] <= za[0] + 1e-6: continue
                ov = fa.intersection(b.footprint(c)).area
                if ov > 0.02: R.err("P-OBJ-COLLIDE", f"{a['label']} and {c['label']} occupy the same space ({ov:.2f} SF)", P2(fa.centroid.coords[0]), lid)
                else: R.ok("P-OBJ-COLLIDE")
    # devices: derived heights; must sit on their mounting surface
    for dv in d["devices"]:
        s = sp.get(dv["space"])
        if not s or not s["poly"]: R.err("P-DEV-SPACE", f"{dv['type']} {dv['id']} is in an untraced space"); continue
        ps = b.spoly(s["id"]); pt = Point(dv["x"], dv["y"])
        if dv["mount"] in ("ceiling", "floor"):
            if not ps.contains(pt): R.err("P-DEV-INSIDE", f"{dv['type']} {dv['id']} is outside {s['name']}", P2((dv['x'], dv['y'])), s["level"])
            else: R.ok("P-DEV-INSIDE")
        else:
            dist = ps.exterior.distance(pt)
            if dist > 0.15: R.err("P-DEV-ONWALL", f"{dv['type']} {dv['id']} is {dist:.2f}' off the nearest wall face of {s['name']} (floating)", P2((dv['x'], dv['y'])), s["level"])
            else: R.ok("P-DEV-ONWALL")
            clg = s["ceiling"] or lv[s["level"]]["ceiling"]
            if dv["h"] is None or dv["h"] > clg - 0.1: R.err("P-DEV-HEIGHT", f"{dv['type']} {dv['id']} mount height {dv['h']} is above the ceiling", P2((dv['x'], dv['y'])), s["level"])

    # ===== C: CIRCULATION ================================================
    doors = [o for o in d["openings"] if o["kind"] == "door"]
    conn = {}
    for o in doors:
        w = W[o["wall"]]; c = opening_center(b, o); n = wall_normal(w)
        off = w["t"] / 2 + 0.35
        A = locate(b, w["level"], (c[0] + n[0] * off, c[1] + n[1] * off))
        Bs = locate(b, w["level"], (c[0] - n[0] * off, c[1] - n[1] * off))
        conn[o["id"]] = (A, Bs)
        lev = lv[w["level"]]
        if A is None and Bs is None: R.err("C-DOOR-NOWHERE", f"door {o['id']} connects nothing", P2(c), w["level"])
        elif (A is None or Bs is None) and lev["elev"] > 0.01:
            R.err("C-DOOR-NOWHERE", f"door {o['id']} on {w['level']} opens to a drop (no balcony/space outside)", P2(c), w["level"])
        else: R.ok("C-DOOR-CONNECTS")
        if A and Bs and A == Bs: R.err("C-DOOR-NOWHERE", f"door {o['id']} has the same room on both sides", P2(c), w["level"])
        # clear width
        nopass = any(s and SPACE[sp[s]["type"]].get("nopass") for s in (A, Bs))
        if o.get("route", True) and not nopass and d["accessible"] and not d["residential_interior"]:
            clear = o["width"] - (0.17 if o["door"] in ("swing", "double") else 0.08)
            if clear + 1e-6 < 2.667: R.err("C-DOOR-WIDTH", f"door {o['id']} clear width {clear * 12:.0f}\" < 32\"", P2(c), w["level"])
            else: R.ok("C-DOOR-WIDTH")
        elif o["width"] < 2.33 and not nopass:
            R.err("C-DOOR-WIDTH", f"door {o['id']} {o['width'] * 12:.0f}\" is too narrow for passage", P2(c), w["level"])
    # swing arcs
    arcs = {}
    for o in doors:
        if o["door"] in ("swing", "double"):
            if o["side"] == 0: R.err("C-DOOR-SWING", f"swing door {o['id']} has no swing direction (pass into=)", P2(opening_center(b, o)), W[o["wall"]]["level"]); continue
            arcs[o["id"]] = swing_polys(b, o)
    for oid, (arc, leafopen) in arcs.items():
        o = next(x for x in doors if x["id"] == oid); w = W[o["wall"]]; lid = w["level"]
        others = unary_union([b.wall_body(v, ends_by_level[lid])[0] for v in d["walls"] if v["level"] == lid and v["id"] != w["id"]])
        bad = []
        if arc.buffer(-0.05).intersects(others): bad.append("a wall")
        for f in objs_by_level[lid]:
            z = zr(f)
            if z[0] < HEAD and arc.buffer(-0.05).intersects(b.footprint(f)): bad.append(f["label"])
        for oid2, (arc2, _) in arcs.items():
            if oid2 != oid and W[next(x for x in doors if x["id"] == oid2)["wall"]]["level"] == lid and arc.buffer(-0.1).intersects(arc2.buffer(-0.1)):
                bad.append(f"door {oid2} swing")
        if bad: R.err("C-DOOR-SWING", f"door {oid} swing hits {', '.join(sorted(set(bad)))}", P2(opening_center(b, o)), lid)
        else: R.ok("C-DOOR-SWING")
    # maneuvering clearance (ADA 404.2.4) + entrance obstruction
    for o in doors:
        w = W[o["wall"]]; lid = w["level"]
        if not o.get("route", True): continue
        A, Bs = conn[o["id"]]
        if any(s and SPACE[sp[s]["type"]].get("nopass") for s in (A, Bs)): continue
        PRIVATE = ("bath", "closet", "guest_room", "bedroom", "living", "kitchen")
        private = all(s and sp[s]["type"] in PRIVATE and not sp[s].get("accessible") for s in (A, Bs)) or d["residential_interior"]
        for sgn, sid in ((1, A), (-1, Bs)):
            pull = (o["door"] in ("swing", "double") and o["side"] == sgn)
            depth = 5.0 if pull else 4.0
            if o["door"] not in ("swing", "double"): depth = 4.0
            latch = 1.5 if pull else 1.0
            if private: depth, latch = 2.0, 0.0      # non-accessible unit interior: just a clear approach
            zone = door_zone(b, o, sgn, depth, latch=latch)
            blockers = [f["label"] for f in objs_by_level[lid] if zr(f)[0] < 2.25 and not OBJ[f["type"]].get("movable") and zone.intersects(b.footprint(f).buffer(-0.02))]
            wallhit = zone.buffer(-0.05).intersects(unions[lid])
            if sid is None:   # exterior side: landing must be clear of building walls and site objects
                if blockers or wallhit: R.err("C-ENTRY-CLEAR", f"exterior side of door {o['id']} obstructed by {', '.join(blockers) or 'a wall'}", P2(zone.centroid.coords[0]), lid)
                else: R.ok("C-ENTRY-CLEAR")
                continue
            if blockers: R.err("C-DOOR-CLEAR", f"{'pull' if pull else 'push'}-side clear space at door {o['id']} blocked by {', '.join(sorted(set(blockers)))}", P2(zone.centroid.coords[0]), lid)
            elif d["accessible"] and not d["residential_interior"] and wallhit and SPACE[sp[sid]["type"]].get("corridor") is None:
                R.warn("C-DOOR-CLEAR", f"{'pull' if pull else 'push'}-side clear space at door {o['id']} is cut by a wall (check ADA 404.2.4 latch clearance)", P2(zone.centroid.coords[0]), lid)
            else: R.ok("C-DOOR-CLEAR")
    # walkable regions per space: furniture must not split a room, block doors or block fixtures
    walk_by_level = {}
    for L in d["levels"]:
        lid = L["id"]; pieces = []
        block = unary_union([b.footprint(f) for f in objs_by_level[lid] if zr(f)[0] < HEAD and OBJ[f["type"]].get("block", True) and not OBJ[f["type"]].get("movable") and f["mount"] == "floor"])
        for s in [s for s in d["spaces"] if s["level"] == lid and s["poly"]]:
            if SPACE[s["type"]].get("walk") is False: continue
            free = b.spoly(s["id"]).difference(block)
            if s["type"] == "stair":
                free = free.difference(stair_holes(b, s, lid))
                for st in d["stairs"]:
                    if st["level_from"] == lid: free = free.difference(under_stair(st))
            pieces.append(free)
            r = 1.0 if SPACE[s["type"]].get("nopass") else (1.25 if d["residential_interior"] else ROUTE)
            core = free.buffer(-r)
            probes = []
            for o in doors:
                if W[o["wall"]]["level"] != lid: continue
                A, Bs = conn[o["id"]]
                for sgn, sid in ((1, A), (-1, Bs)):
                    if sid == s["id"]:
                        c = opening_center(b, o); n = wall_normal(W[o["wall"]]); k = W[o["wall"]]["t"] / 2 + r + 0.1
                        probes.append((f"door {o['id']}", Point(c[0] + sgn * n[0] * k, c[1] + sgn * n[1] * k)))
            for f in objs_by_level[lid]:
                if f["space"] != s["id"]: continue
                for zn, z in b.clear_zones(f).items():
                    zi = z.intersection(b.spoly(s["id"]))
                    hit = [g["label"] for g in objs_by_level[lid] if g is not f and not OBJ[g["type"]].get("movable") and OBJ[g["type"]].get("block", True) and not (f.get("on") == g["id"] or g.get("on") == f["id"]) and zr(g)[0] < 2.5 and z.buffer(-0.03).intersects(b.footprint(g))]
                    if zi.area < z.area * 0.9: R.err("P-CLEARANCE", f"{f['label']} {zn} clearance runs into a wall ({(1 - zi.area / max(z.area, 1e-6)) * 100:.0f}% lost)", P2(z.centroid.coords[0]), lid)
                    elif hit: R.err("P-CLEARANCE", f"{f['label']} {zn} clearance blocked by {', '.join(sorted(set(hit)))}", P2(z.centroid.coords[0]), lid)
                    else: R.ok("P-CLEARANCE")
                    if zn in ("front", "ada_wc"): probes.append((f"{f['label']} {zn}", zi if not zi.is_empty else z))
            if not probes: continue
            comps = list(core.geoms) if core.geom_type == "MultiPolygon" else ([core] if not core.is_empty else [])
            def comp_of(pt):
                best, bd = None, 9e9
                for k, g in enumerate(comps):
                    dd = g.distance(pt)
                    if dd < bd: best, bd = k, dd
                return best, bd
            ids = {}
            for name, pt in probes:
                k, dist = comp_of(pt)
                if k is None or dist > r + 0.6: R.err("C-ROUTE", f"{s['name']}: {name} is not reachable on a {2 * r * 12:.0f}\" route (furniture or walls pinch it)", P2(pt.centroid.coords[0]), lid)
                else: ids[name] = k; R.ok("C-ROUTE")
            if len(set(ids.values())) > 1:
                R.err("C-ROUTE-SPLIT", f"{s['name']}: furniture splits the room - {', '.join(n for n in ids)} are not all connected by a {2 * r * 12:.0f}\" path", P2(s['seed']), lid)
            elif ids: R.ok("C-ROUTE-SPLIT")
            # corridor width
            if SPACE[s["type"]].get("corridor"):
                need = 1.83 if occupant_load(b, lid) > 49 else 1.5
                cw = free.buffer(-need + 0.01)
                if cw.is_empty or cw.geom_type == "MultiPolygon": R.err("C-CORRIDOR", f"{s['name']} is narrower than {need * 24:.0f}\" somewhere", P2(s['seed']), lid)
                else: R.ok("C-CORRIDOR")
            if s.get("accessible") or (d["accessible"] and s["type"] in ("restroom",)):
                if free.buffer(-TURN).is_empty: R.err("A-TURN", f"{s['name']}: no 60\" turning circle free of furniture", P2(s['seed']), lid)
                else: R.ok("A-TURN")
        walk_by_level[lid] = unary_union(pieces) if pieces else Polygon()
    # ADA water closet centerline 16-18" from side wall
    for f in d["objects"]:
        if OBJ[f["type"]].get("ada_wc") and f.get("_level"):
            fp = b.footprint(f); sb = b.spoly(f["space"]).bounds; cx, cy = fp.centroid.coords[0]
            dist = min(cx - sb[0], sb[2] - cx) if f["facing"] in "NS" else min(cy - sb[1], sb[3] - cy)
            if not 1.33 - 1e-3 <= dist <= 1.5 + 1e-3: R.err("A-WC-CL", f"{f['label']} centerline {dist * 12:.1f}\" from side wall (need 16-18\")", P2((cx, cy)), f["_level"])
            else: R.ok("A-WC-CL")
    # protruding objects (ADA 307)
    for lid, os_ in objs_by_level.items():
        for f in os_:
            if f["mount"] == "wall" and 2.25 < f["elev"] < 6.67 and f["d"] > 0.34 and sp[f["space"]]["type"] in ("corridor", "lobby"):
                R.err("A-PROTRUDE", f"{f['label']} protrudes {f['d'] * 12:.0f}\" into a route between 27\" and 80\" (max 4\")", [f["x"], f["y"]], lid)
    # building graph: every space reachable from an exit
    G = defaultdict(set)
    for o in doors:
        A, Bs = conn[o["id"]]
        A = A or "OUT"; Bs = Bs or "OUT"
        G[A].add(Bs); G[Bs].add(A)
    stairs_ok = check_stairs(b, R, lv, sp)
    for st in d["stairs"]:
        a = stair_space(b, st["level_from"], st); c = stair_space(b, st["level_to"], st)
        if a and c: G[a].add(c); G[c].add(a)
    for e in d["elevators"]:
        ids = [s["id"] for s in d["spaces"] if s["type"] == "elevator" and s["level"] in e["levels"] and s["poly"] and b.spoly(s["id"]).intersects(sbox(*e["rect"]))]
        for i in ids:
            for j in ids:
                if i != j: G[i].add(j)
    seen, stack = {"OUT"}, ["OUT"]
    while stack:
        n = stack.pop()
        for m in G[n]:
            if m not in seen: seen.add(m); stack.append(m)
    for s in d["spaces"]:
        if not s["poly"] or SPACE[s["type"]].get("walk") is False: continue
        if s["id"] not in seen: R.err("C-REACH", f"{s['name']} cannot be reached from the street (no door path)", P2(s["seed"]), s["level"])
        else: R.ok("C-REACH")
    # accessible route to accessible spaces: no stairs
    if d["accessible"]:
        G2 = defaultdict(set)
        for n, ms in G.items():
            for m in ms:
                if n in sp and m in sp and sp[n]["type"] == "stair" and sp[m]["type"] == "stair" and sp[n]["level"] != sp[m]["level"]: continue
                G2[n].add(m)
        seen2, stack = {"OUT"}, ["OUT"]
        while stack:
            n = stack.pop()
            for m in G2[n]:
                if m not in seen2: seen2.add(m); stack.append(m)
        for s in d["spaces"]:
            if s.get("accessible") and s["id"] not in seen2: R.err("A-ROUTE", f"accessible space {s['name']} is only reachable by stairs", P2(s["seed"]), s["level"])
            elif s.get("accessible"): R.ok("A-ROUTE")

    # ===== K: CODE ========================================================
    sprk = d["sprinklered"]
    for L in d["levels"]:
        lid = L["id"]; ss = [s for s in d["spaces"] if s["level"] == lid and s["poly"]]
        for s in ss:
            ty = SPACE[s["type"]]; area = b.spoly(s["id"]).area; clg = s["ceiling"] or L["ceiling"]
            if ty["hab"]:
                minx, miny, maxx, maxy = b.spoly(s["id"]).bounds
                if area < 70: R.err("K-ROOM-SIZE", f"{s['name']} {area:.0f} SF < 70 SF habitable minimum", P2(s['seed']), lid)
                elif min(maxx - minx, maxy - miny) < 7: R.err("K-ROOM-SIZE", f"{s['name']} narrower than 7'-0\"", P2(s['seed']), lid)
                else: R.ok("K-ROOM-SIZE")
            mc = ty.get("min_clg", 7.5)
            if clg + 1e-6 < mc: R.err("K-CEILING", f"{s['name']} ceiling {clg}' < {mc}'", P2(s['seed']), lid)
            else: R.ok("K-CEILING")
            if clg > L["height"] - 0.75: R.err("K-CEILING", f"{s['name']} ceiling {clg}' leaves no room for the floor structure above ({L['height']}' floor-to-floor)", P2(s['seed']), lid)
            if ty.get("sleep") and not sprk:
                win = [o for o in d["openings"] if o["kind"] == "window" and o["width"] * o["height"] * 0.8 >= 5.7 and o["sill"] <= 3.67 and s["id"] in [locate(b, lid, side_pt(b, o, 1)), locate(b, lid, side_pt(b, o, -1))]]
                if not win: R.err("K-EGRESS-WINDOW", f"{s['name']}: sleeping room needs an emergency escape window (5.7 SF, sill ≤ 44\") or sprinklers", P2(s['seed']), lid)
        # exits
        occ = occupant_load(b, lid)
        exits = exit_points(b, lid, conn, sp)
        need = 1 if (occ <= 49 and not (d["occupancy"].startswith("R") and occ > 10)) else (2 if occ <= 500 else 3)
        if len(exits) < need: R.err("K-EXITS", f"{lid}: occupant load {occ} needs {need} exits, found {len(exits)}", None, lid)
        else: R.ok("K-EXITS")
        if need >= 2 and len(exits) >= 2:
            fp = unary_union([b.spoly(s["id"]) for s in ss]); x0, y0, x1, y1 = fp.bounds
            diag = math.hypot(x1 - x0, y1 - y0); sep = max(math.dist(p, q) for p in exits for q in exits)
            req = diag / (3 if sprk else 2)
            if sep + 1e-6 < req: R.err("K-EXIT-SEP", f"{lid}: exits {sep:.0f}' apart < required {req:.0f}'", None, lid)
            else: R.ok("K-EXIT-SEP")
        # travel distance (grid BFS through walkable space and doors)
        lim = {"R": 250 if sprk else 200, "B": 300 if sprk else 200, "A": 250 if sprk else 200, "M": 250 if sprk else 200, "S": 250 if sprk else 200}.get(d["occupancy"][0], 200)
        td, worst = travel(b, lid, walk_by_level[lid], doors, conn, exits)
        if td is None: R.warn("K-TRAVEL", f"{lid}: could not compute travel distance", None, lid)
        elif td > lim: R.err("K-TRAVEL", f"{lid}: exit travel {td:.0f}' > {lim}'", P2(worst), lid)
        else: R.ok("K-TRAVEL")
    # ADA guest room counts (2010 ADA 224)
    if d["accessible"] and d["occupancy"] == "R-1":
        rooms = [s for s in d["spaces"] if s["type"] == "guest_room"]
        n = len(rooms); acc = sum(1 for s in rooms if s.get("accessible"))
        req = ada_rooms(n)
        if acc < req: R.err("A-ROOM-COUNT", f"{acc} accessible guest rooms < {req} required for {n} rooms")
        else: R.ok("A-ROOM-COUNT")

    # ===== M: MEP / DEVICES ==============================================
    for s in d["spaces"]:
        if not s["poly"]: continue
        have = {dv["type"] for dv in d["devices"] if dv["space"] == s["id"]}
        if "light" in SPACE[s["type"]]["need"] and not ({"light", "light_pendant", "wall_sconce"} & have):
            R.err("M-DEVICES", f"{s['name']} has no light fixture", P2(s['seed']), s["level"])
        for need in SPACE[s["type"]]["need"]:
            if need == "light": continue
            if need not in have: (R.err if need in ("smoke_alarm", "exhaust_fan") else R.warn)("M-DEVICES", f"{s['name']} is missing a {need.replace('_', ' ')}", P2(s['seed']), s["level"])
            else: R.ok("M-DEVICES")
    for f in d["objects"]:
        if OBJ[f["type"]].get("plumb"):
            lid = f.get("_level");
            if not lid: continue
            wet = [LineString([w["a"], w["b"]]) for w in d["walls"] if w["level"] == lid and w["wet"]]
            dist = min([b.footprint(f).distance(l) for l in wet] or [99])
            if dist > 6: R.warn("M-WET-WALL", f"{f['label']} is {dist:.0f}' from any plumbing (wet) wall", [f["x"], f["y"]], lid)
            else: R.ok("M-WET-WALL")
    for i in range(1, len(order)):
        lo = [LineString([w["a"], w["b"]]) for w in d["walls"] if w["level"] == order[i - 1]["id"] and w["wet"]]
        lou = unary_union(lo).buffer(0.5) if lo else Polygon()
        for w in d["walls"]:
            if w["level"] == order[i]["id"] and w["wet"]:
                if LineString([w["a"], w["b"]]).intersection(lou).length < 0.5: R.warn("M-WET-STACK", f"wet wall {w['id']} does not stack over a wet wall below (offset the stack in the floor)", P2(w["a"]), w["level"])
                else: R.ok("M-WET-STACK")
    return R


# ---------------- helpers ----------------
def wall_normal(w):
    ax, ay = w["a"]; bx, by = w["b"]; L = math.dist(w["a"], w["b"])
    return (-(by - ay) / L, (bx - ax) / L)


def opening_center(b, o):
    w = b.get("walls", o["wall"]); ax, ay = w["a"]; bx, by = w["b"]; L = math.dist(w["a"], w["b"])
    s = o["offset"] + o["width"] / 2
    return (ax + (bx - ax) * s / L, ay + (by - ay) * s / L)


def side_pt(b, o, sgn, k=None):
    w = b.get("walls", o["wall"]); c = opening_center(b, o); n = wall_normal(w); k = k or w["t"] / 2 + 0.35
    return (c[0] + sgn * n[0] * k, c[1] + sgn * n[1] * k)


def locate(b, lid, pt):
    P = Point(pt)
    for s in b.d["spaces"]:
        if s["level"] == lid and s["poly"] and b.spoly(s["id"]).contains(P): return s["id"]
    return None


def swing_polys(b, o):
    """quarter-circle swept by the leaf, on the swing side"""
    w = b.get("walls", o["wall"]); ax, ay = w["a"]; bx, by = w["b"]; L = math.dist(w["a"], w["b"])
    ux, uy = (bx - ax) / L, (by - ay) / L; n = wall_normal(w); sg = o["side"]
    s0 = o["offset"] if o["hinge"] == "start" else o["offset"] + o["width"]
    leaves = [(s0, o["width"], 1 if o["hinge"] == "start" else -1)]
    if o["door"] == "double": leaves = [(o["offset"], o["width"] / 2, 1), (o["offset"] + o["width"], o["width"] / 2, -1)]
    polys = []
    for s, r, dirn in leaves:
        hx, hy = ax + ux * s, ay + uy * s
        hx += n[0] * sg * w["t"] / 2; hy += n[1] * sg * w["t"] / 2
        pts = [(hx, hy)]
        for k in range(0, 17):
            a = k / 16 * math.pi / 2
            vx = dirn * ux * math.cos(a) + sg * n[0] * math.sin(a)
            vy = dirn * uy * math.cos(a) + sg * n[1] * math.sin(a)
            pts.append((hx + vx * r, hy + vy * r))
        polys.append(Polygon(pts))
    return unary_union(polys), None


def door_zone(b, o, sgn, depth, latch=1.5):
    w = b.get("walls", o["wall"]); ax, ay = w["a"]; bx, by = w["b"]; L = math.dist(w["a"], w["b"])
    ux, uy = (bx - ax) / L, (by - ay) / L; n = wall_normal(w)
    s0, s1 = o["offset"], o["offset"] + o["width"]
    if o["door"] in ("swing",):
        if o["hinge"] == "start": s1 += latch
        else: s0 -= latch
    base = w["t"] / 2 + 0.01
    pts = []
    for s, k in ((s0, base), (s1, base), (s1, base + depth), (s0, base + depth)):
        pts.append((ax + ux * s + sgn * n[0] * k, ay + uy * s + sgn * n[1] * k))
    return Polygon(pts)


def stair_holes(b, s, lid):
    """floor openings inside a stair space: footprints of stairs arriving from below"""
    out = []
    for st in b.d["stairs"]:
        if st["level_to"] == lid: out.append(Polygon(st["footprint"]))
    return unary_union(out) if out else Polygon()


def stair_space(b, lid, st):
    for s in b.d["spaces"]:
        if s["level"] == lid and s["type"] == "stair" and s["poly"] and b.spoly(s["id"]).intersects(Polygon(st["footprint"]).buffer(-0.1)): return s["id"]
    return None


def check_stairs(b, R, lv, sp):
    for st in b.d["stairs"]:
        L0, L1 = lv[st["level_from"]], lv[st["level_to"]]
        n = sum(f["risers"] for f in st["flights"]); H = L1["elev"] - L0["elev"]
        rmax, tmin = ((7.75, 10) if st["res"] else (7.0, 11))
        if abs(n * st["riser"] - H) > 0.01: R.err("C-STAIR-RISE", f"stair {st['id']}: risers do not add up to the floor-to-floor height", st["origin"], st["level_from"])
        if st["riser"] * 12 > rmax + 1e-6 or st["riser"] * 12 < 4: R.err("C-STAIR-RISE", f"stair {st['id']}: riser {st['riser'] * 12:.2f}\" outside 4-{rmax}\"", st["origin"], st["level_from"])
        else: R.ok("C-STAIR-RISE")
        if st["tread"] * 12 + 1e-6 < tmin: R.err("C-STAIR-TREAD", f"stair {st['id']}: tread {st['tread'] * 12:.1f}\" < {tmin}\"", st["origin"], st["level_from"])
        else: R.ok("C-STAIR-TREAD")
        wmin = 3.0 if st["res"] else 3.67
        for f in st["flights"]:
            if f["width"] + 1e-6 < wmin: R.err("C-STAIR-WIDTH", f"stair {st['id']}: flight width {f['width'] * 12:.0f}\" < {wmin * 12:.0f}\"", f["start"], st["level_from"])
            else: R.ok("C-STAIR-WIDTH")
        for lg in st["landings"]:
            p = Polygon(lg["poly"]); x0, y0, x1, y1 = p.bounds
            if min(x1 - x0, y1 - y0) + 1e-6 < st["flights"][0]["width"]: R.err("C-STAIR-LANDING", f"stair {st['id']}: landing shallower than stair width", st["origin"], st["level_from"])
            else: R.ok("C-STAIR-LANDING")
        # footprint inside stair spaces; arrival points on floor
        a = stair_space(b, st["level_from"], st); c = stair_space(b, st["level_to"], st)
        fp = Polygon(st["footprint"])
        if not a or not b.spoly(a).buffer(0.05).contains(fp): R.err("C-STAIR-ENCLOSE", f"stair {st['id']} does not fit inside a stair space on {st['level_from']}", st["origin"], st["level_from"])
        else: R.ok("C-STAIR-ENCLOSE")
        if not c: R.err("C-STAIR-ARRIVE", f"stair {st['id']} arrives on {st['level_to']} with no stair space/opening above", st["origin"], st["level_to"])
        else:
            if not b.spoly(c).buffer(0.05).contains(fp): R.err("C-STAIR-HEADROOM", f"stair {st['id']}: slab above is not opened over the whole stair (headroom)", st["origin"], st["level_to"])
            else: R.ok("C-STAIR-HEADROOM")
        # open edges: every edge of the stair footprint except the arrival/approach edge must bear on a wall
        if a:
            ring = b.spoly(a).exterior; fpts = list(Polygon(st["footprint"]).exterior.coords)
            f1s = Point(st["flights"][0]["start"])
            for p, q in zip(fpts, fpts[1:]):
                e = LineString([p, q])
                if e.distance(f1s) < 0.05: continue           # the bottom/top edge where people step on/off
                if e.hausdorff_distance(ring.intersection(e.buffer(0.15))) > 0.2 if not ring.intersection(e.buffer(0.15)).is_empty else True:
                    R.err("C-STAIR-GUARD", f"stair {st['id']}: footprint edge {P2(p)}-{P2(q)} is open to a drop - put the stair against walls or add a guard", P2(e.centroid.coords[0]), st["level_from"])
                else: R.ok("C-STAIR-GUARD")
        f1, f2 = st["flights"][0], st["flights"][-1]
        dirv = unit(f1["start"], f1["end"])
        bot = (f1["start"][0] - dirv[0] * 1.5, f1["start"][1] - dirv[1] * 1.5)
        top = (f2["end"][0] - dirv[0] * 1.5, f2["end"][1] - dirv[1] * 1.5)
        if not a or not b.spoly(a).contains(Point(bot)): R.err("C-STAIR-ARRIVE", f"stair {st['id']}: no floor to step onto at the bottom", P2(bot), st["level_from"])
        else: R.ok("C-STAIR-ARRIVE")
        if not c or not b.spoly(c).contains(Point(top)) or Polygon(st["footprint"]).contains(Point(top)):
            R.err("C-STAIR-ARRIVE", f"stair {st['id']}: no floor to step onto at the top", P2(top), st["level_to"])
        else: R.ok("C-STAIR-ARRIVE")
    return True


def unit(p, q):
    L = math.dist(p, q); return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def occupant_load(b, lid):
    tot = 0
    for s in b.d["spaces"]:
        if s["level"] == lid and s["poly"] and SPACE[s["type"]]["olf"]:
            tot += math.ceil(b.spoly(s["id"]).area / SPACE[s["type"]]["olf"])
    return tot


def exit_points(b, lid, conn, sp):
    pts = []
    for o in b.d["openings"]:
        if o["kind"] != "door": continue
        w = b.get("walls", o["wall"])
        if w["level"] != lid: continue
        A, Bs = conn[o["id"]]
        if A is None or Bs is None: pts.append(opening_center(b, o))
    for st in b.d["stairs"]:
        for L_ in (st["level_from"], st["level_to"]):
            if L_ == lid:
                s = stair_space(b, lid, st)
                if s: pts.append(tuple(b.spoly(s).centroid.coords[0]))
    uniq = []
    for p in pts:
        if all(math.dist(p, q) > 3 for q in uniq): uniq.append(p)
    return uniq


def travel(b, lid, walk, doors, conn, exits, step=1.0):
    if walk.is_empty or not exits: return None, None
    for o in doors:
        if b.get("walls", o["wall"])["level"] == lid:
            w = b.get("walls", o["wall"]); c = opening_center(b, o); n = wall_normal(w); k = w["t"] / 2 + 0.6
            walk = walk.union(LineString([(c[0] - n[0] * k, c[1] - n[1] * k), (c[0] + n[0] * k, c[1] + n[1] * k)]).buffer(min(o["width"] / 2, 1.2)))
    pw = prep(walk); x0, y0, x1, y1 = walk.bounds
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    ok = {}
    for i in range(nx):
        for j in range(ny):
            p = Point(x0 + i * step, y0 + j * step)
            if pw.contains(p): ok[(i, j)] = True
    dist = {}; pq = []
    for e in exits:
        best = min(ok, key=lambda c: (x0 + c[0] * step - e[0]) ** 2 + (y0 + c[1] * step - e[1]) ** 2)
        dist[best] = 0; heapq.heappush(pq, (0, best))
    nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    while pq:
        dd, c = heapq.heappop(pq)
        if dd > dist.get(c, 9e9): continue
        for di, dj, w in nb:
            n2 = (c[0] + di, c[1] + dj)
            if n2 in ok and dd + w * step < dist.get(n2, 9e9): dist[n2] = dd + w * step; heapq.heappush(pq, (dist[n2], n2))
    if not dist: return None, None
    unreached = [c for c in ok if c not in dist]
    worst = max(dist, key=dist.get)
    return dist[worst], (x0 + worst[0] * step, y0 + worst[1] * step)


def ada_rooms(n):
    tbl = [(25, 1), (50, 2), (75, 4), (100, 5), (150, 7), (200, 8), (300, 10), (400, 12), (500, 14)]
    for lim, r in tbl:
        if n <= lim: return r if n > 0 else 0
    return 14 + math.ceil((n - 500) / 100) * 1 if n <= 1000 else 21 + math.ceil((n - 1000) / 100)


def format_report(R):
    lines = []
    errs = [i for i in R.items if i["sev"] == "ERROR"]; wrn = [i for i in R.items if i["sev"] == "WARN"]
    lines.append(f"RESULT: {'PASS' if not errs else 'FAIL'}  -  {len(errs)} errors, {len(wrn)} warnings, {sum(R.passed.values())} checks passed")
    for i in errs + wrn:
        at = f" @ {i['level'] or ''} {i['at']}" if i.get("at") else (f" @ {i['level']}" if i.get("level") else "")
        lines.append(f"  [{i['sev']}] {i['code']}: {i['msg']}{at}")
    lines.append("Passed by check: " + ", ".join(f"{k}={v}" for k, v in sorted(R.passed.items())))
    return "\n".join(lines)


def main():
    path = sys.argv[1]; b = load(path); R = validate(b)
    print(format_report(R))
    if "--json" in sys.argv:
        json.dump(dict(items=R.items, passed=R.passed), open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    sys.exit(1 if R.errors else 0)


if __name__ == "__main__":
    main()
