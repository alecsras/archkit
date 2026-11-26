"""archkit.scene - derive ALL renderable geometry from the model (2D and 3D use this, nothing else).
Every z value here is computed from a level, a ceiling, a host object or a wall face."""
import math
from shapely.geometry import Polygon, Point, LineString, box as sbox
from shapely.ops import unary_union
from .model import OBJ, SPACE, under_stair


def wall_frame(w):
    ax, ay = w["a"]; bx, by = w["b"]; L = math.dist(w["a"], w["b"])
    ux, uy = (bx - ax) / L, (by - ay) / L
    return ax, ay, ux, uy, (-uy, ux), L


def wall_pieces(b, w, ends, lev):
    """solid boxes for a wall: (s0, s1, z0, z1, kind) along its axis; openings cut out with sills/headers"""
    H = w["h"] or lev["height"]
    _, (s0, s1) = b.wall_body(w, ends)
    ops = sorted([o for o in b.d["openings"] if o["wall"] == w["id"]], key=lambda o: o["offset"])
    out, cur = [], s0
    for o in ops:
        a, c = o["offset"], o["offset"] + o["width"]
        if a > cur: out.append((cur, a, 0.0, H, "wall"))
        if o["kind"] == "window":
            out.append((a, c, 0.0, o["sill"], "wall")); out.append((a, c, o["sill"] + o["height"], H, "wall"))
            out.append((a, c, o["sill"], o["sill"] + o["height"], "glass"))
        else:
            out.append((a, c, o["height"], H, "wall"))
        cur = c
    if cur < s1: out.append((cur, s1, 0.0, H, "wall"))
    return out


def door_leaves(b, o, lev):
    """hinge point on the swing-side face, leaf width, closed and open angles (deg, plan, 0=+x, 90=+y)"""
    w = b.get("walls", o["wall"]); ax, ay, ux, uy, n, L = wall_frame(w)
    if o["door"] in ("cased",): return []
    sg = o["side"] or 1
    leaves = []
    if o["door"] in ("swing", "double"):
        specs = [(o["offset"], o["width"], 1), ] if o["hinge"] == "start" else [(o["offset"] + o["width"], o["width"], -1)]
        if o["door"] == "double": specs = [(o["offset"], o["width"] / 2, 1), (o["offset"] + o["width"], o["width"] / 2, -1)]
        for s, r, dirn in specs:
            hx = ax + ux * s + n[0] * sg * w["t"] / 2; hy = ay + uy * s + n[1] * sg * w["t"] / 2
            closed = math.degrees(math.atan2(uy * dirn, ux * dirn))
            opened = math.degrees(math.atan2(uy * dirn * 0 + n[1] * sg, ux * dirn * 0 + n[0] * sg))
            leaves.append(dict(kind="swing", hinge=[hx, hy], w=r, closed=closed, open=opened, z=lev["elev"], h=o["height"], id=o["id"], exterior=bool(o.get("exterior"))))
    else:   # pocket / slide: leaf slides along the wall
        s = o["offset"]; hx = ax + ux * s; hy = ay + uy * s
        leaves.append(dict(kind="slide", hinge=[hx, hy], w=o["width"], closed=math.degrees(math.atan2(uy, ux)), open=None, z=lev["elev"], h=o["height"], id=o["id"]))
    return leaves


def obj_z(b, o, lev):
    if o.get("on"):
        host = b.get("objects", o["on"]); return obj_z(b, host, lev) + host["h"]
    return lev["elev"] + o["elev"]


def stair_treads(b, st):
    lv = {L["id"]: L for L in b.d["levels"]}
    z0 = lv[st["level_from"]]["elev"]; out = []
    k = 0
    for f in st["flights"]:
        (sx, sy), (ex, ey) = f["start"], f["end"]; L = math.dist(f["start"], f["end"]) or 1
        ux, uy = (ex - sx) / L, (ey - sy) / L; nx, ny = -uy, ux
        n = f["risers"]
        for i in range(n):
            k += 1
            if i == n - 1: continue          # last riser lands on the landing / floor
            cx = sx + ux * (i * st["tread"] + st["tread"] / 2); cy = sy + uy * (i * st["tread"] + st["tread"] / 2)
            out.append(dict(c=[cx, cy], u=[ux, uy], len=st["tread"], w=f["width"], top=z0 + k * st["riser"]))
    return out


def build_scene(b):
    b.trace()
    d = b.d; lv = {L["id"]: L for L in d["levels"]}
    order = sorted(d["levels"], key=lambda L: L["elev"])
    S = dict(name=d["name"], levels=[], walls=[], glass=[], floors=[], ceilings=[], slabs=[], objects=[], devices=[],
             treads=[], landings=[], doors=[], guards=[], walk=[], ramps=[], roof=None, spawn=None)
    for L in order:
        lid = L["id"]; ends = b.wall_ends(lid)
        S["levels"].append(dict(id=lid, elev=L["elev"], height=L["height"], ceiling=L["ceiling"]))
        from .validate import locate
        for w in [w for w in d["walls"] if w["level"] == lid]:
            ax, ay, ux, uy, n, Lw = wall_frame(w)
            # exterior walls: painted inner layer + siding skin on the side that faces outdoors
            out_sg = 0
            if w["kind"] == "exterior":
                mx, my = ax + ux * Lw / 2, ay + uy * Lw / 2; k = w["t"] / 2 + 0.6
                out_sg = 1 if locate(b, lid, (mx + n[0] * k, my + n[1] * k)) is None else -1
            for s0, s1, z0, z1, kind in wall_pieces(b, w, ends, L):
                if s1 - s0 < 1e-3 or z1 - z0 < 1e-3: continue
                cx = ax + ux * (s0 + s1) / 2; cy = ay + uy * (s0 + s1) / 2
                base = dict(ang=math.degrees(math.atan2(uy, ux)), len=s1 - s0, z0=L["elev"] + z0, z1=L["elev"] + z1, level=lid)
                if kind == "glass": S["glass"].append(dict(base, c=[cx, cy], t=0.08, kind="glass")); continue
                if out_sg:
                    sk = 0.12; core = w["t"] - sk
                    S["walls"].append(dict(base, c=[cx - n[0] * out_sg * sk / 2, cy - n[1] * out_sg * sk / 2], t=core, kind="interior"))
                    S["walls"].append(dict(base, c=[cx + n[0] * out_sg * core / 2, cy + n[1] * out_sg * core / 2], t=sk, kind="exterior"))
                else:
                    S["walls"].append(dict(base, c=[cx, cy], t=w["t"], kind=w["kind"]))
        # stair holes = footprints of stairs arriving from below
        holes = unary_union([Polygon(st["footprint"]) for st in d["stairs"] if st["level_to"] == lid]) if any(st["level_to"] == lid for st in d["stairs"]) else Polygon()
        spaces = [s for s in d["spaces"] if s["level"] == lid and s["poly"]]
        for s in spaces:
            p = b.spoly(s["id"])
            walkp = None
            if s["type"] == "stair":
                p = p.difference(holes)
                walkp = p
                for st in d["stairs"]:
                    if st["level_from"] == lid: walkp = walkp.difference(under_stair(st))
            if s["type"] == "shaft": continue
            for g in (list(p.geoms) if p.geom_type == "MultiPolygon" else [p]):
                if g.is_empty: continue
                rec = dict(poly=[list(c) for c in g.exterior.coords[:-1]], holes=[[list(c) for c in r.coords[:-1]] for r in g.interiors],
                           z=L["elev"], type=s["type"], level=lid, name=s["name"], id=s["id"])
                S["floors"].append(rec)
            if SPACE[s["type"]].get("walk", True):
                wp = walkp if walkp is not None else p
                for g in (list(wp.geoms) if wp.geom_type == "MultiPolygon" else [wp]):
                    if g.is_empty: continue
                    S["walk"].append(dict(poly=[list(c) for c in g.exterior.coords[:-1]], holes=[[list(c) for c in r.coords[:-1]] for r in g.interiors],
                                          z=L["elev"], type=s["type"], level=lid, name=s["name"], id=s["id"]))
            top = L is order[-1]
            if s["type"] in ("stair",) and not top: continue
            clg = s["ceiling"] or L["ceiling"]
            S["ceilings"].append(dict(poly=s["poly"], holes=s.get("holes") or [], z=L["elev"] + clg, level=lid))
        # slab under this level (not the ground floor): footprint minus stair holes and the elevator shaft
        if L is not order[0]:
            fp = unary_union([b.spoly(s["id"]) for s in spaces] + [b.walls_union(lid)]).buffer(-0.04)   # inset: no coplanar faces with walls
            fp = fp.difference(holes)
            for e in d["elevators"]:
                if lid in e["levels"]: fp = fp.difference(sbox(*e["rect"]))
            for g in (list(fp.geoms) if fp.geom_type == "MultiPolygon" else [fp]):
                S["slabs"].append(dict(poly=[list(c) for c in g.exterior.coords[:-1]], holes=[[list(c) for c in r.coords[:-1]] for r in g.interiors],
                                       z0=L["elev"] - L["slab"], z1=L["elev"], level=lid))
        # objects
        for o in d["objects"]:
            if b.get("spaces", o["space"])["level"] != lid: continue
            fp = b.footprint(o); x0, y0, x1, y1 = fp.bounds; z = obj_z(b, o, L)
            S["objects"].append(dict(type=o["type"], label=o["label"], x0=x0, y0=y0, x1=x1, y1=y1, z0=z, z1=z + o["h"], facing=o["facing"],
                                     block=OBJ[o["type"]].get("block", True) and not OBJ[o["type"]].get("movable") and o["mount"] == "floor", level=lid))
        # devices: z from mounting surface
        for dv in d["devices"]:
            s = b.get("spaces", dv["space"])
            if s["level"] != lid: continue
            clg = s["ceiling"] or L["ceiling"]
            if dv["mount"] == "ceiling": z = L["elev"] + clg
            elif dv["mount"] == "floor": z = L["elev"]
            else: z = L["elev"] + dv["h"]
            nrm = None
            if dv["mount"] == "wall":   # inward normal of the nearest wall face
                ring = LineString(b.spoly(s["id"]).exterior.coords); pt = Point(dv["x"], dv["y"]); q = ring.interpolate(ring.project(pt))
                c = b.spoly(s["id"]).representative_point(); vx, vy = c.x - q.x, c.y - q.y
                seg = None; coords = list(ring.coords)
                for i in range(len(coords) - 1):
                    if LineString([coords[i], coords[i + 1]]).distance(q) < 1e-6: seg = (coords[i], coords[i + 1]); break
                if seg:
                    ex, ey = seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]; m = math.hypot(ex, ey); nx, ny = -ey / m, ex / m
                    if nx * vx + ny * vy < 0: nx, ny = -nx, -ny
                    nrm = [nx, ny]
                S["devices"].append(dict(type=dv["type"], x=q.x, y=q.y, z=z, mount="wall", n=nrm, level=lid)); continue
            S["devices"].append(dict(type=dv["type"], x=dv["x"], y=dv["y"], z=z, mount=dv["mount"], level=lid))
        # thresholds: door openings are walkable
        for o in d["openings"]:
            if o["kind"] == "door" and b.get("walls", o["wall"])["level"] == lid:
                w = b.get("walls", o["wall"]); ax, ay, ux, uy, n, _ = wall_frame(w); hh = w["t"] / 2 + 0.05
                a0, a1 = o["offset"], o["offset"] + o["width"]
                pts = [[ax + ux * a0 + n[0] * hh, ay + uy * a0 + n[1] * hh], [ax + ux * a1 + n[0] * hh, ay + uy * a1 + n[1] * hh],
                       [ax + ux * a1 - n[0] * hh, ay + uy * a1 - n[1] * hh], [ax + ux * a0 - n[0] * hh, ay + uy * a0 - n[1] * hh]]
                S["walk"].append(dict(poly=pts, holes=[], z=L["elev"], type="threshold", level=lid, name="Doorway", id=o["id"]))
        # doors
        for o in d["openings"]:
            if o["kind"] == "door" and b.get("walls", o["wall"])["level"] == lid:
                for lf in door_leaves(b, o, L): S["doors"].append(lf)
    # stairs: treads, landings, ramps (for walking), guards at open top edges
    for st in d["stairs"]:
        z0 = lv[st["level_from"]]["elev"]; z1 = lv[st["level_to"]]["elev"]
        S["treads"] += stair_treads(b, st)
        for lg in st["landings"]:
            S["landings"].append(dict(poly=lg["poly"], z=z0 + lg["z"]))
        zc = z0
        for f in st["flights"]:
            rise = f["risers"] * st["riser"]
            S["ramps"].append(dict(start=f["start"], end=f["end"], w=f["width"], z0=zc, z1=zc + rise, level=st["level_from"]))
            zc += rise
        # divider between flights + top guard when no stair continues upward
        f1, f2 = st["flights"][0], st["flights"][-1]
        mx = ((f1["start"][0] + f2["end"][0]) / 2, (f1["start"][1] + f2["end"][1]) / 2)
        L1 = math.dist(f1["start"], f1["end"]); ux, uy = (f1["end"][0] - f1["start"][0]) / L1, (f1["end"][1] - f1["start"][1]) / L1
        S["guards"].append(dict(a=list(mx), b=[mx[0] + ux * L1, mx[1] + uy * L1], z0=z0, z1=z1 + 3.5))
        if not any(s2["level_from"] == st["level_to"] and s2["origin"] == st["origin"] for s2 in d["stairs"]):
            nx, ny = -uy, ux; hw = f1["width"] / 2
            a = (f1["start"][0] - nx * hw, f1["start"][1] - ny * hw); c = (f1["start"][0] + nx * hw, f1["start"][1] + ny * hw)
            S["guards"].append(dict(a=list(a), b=list(c), z0=z1, z1=z1 + 3.5))
    for g in d.get("guards", []):
        z = lv[g["level"]]["elev"]; S["guards"].append(dict(a=g["a"], b=g["b"], z0=z, z1=z + g["h"], rail=True))
    top = order[-1]
    fp = unary_union([b.spoly(s["id"]) for s in d["spaces"] if s["level"] == top["id"] and s["poly"]] + [b.walls_union(top["id"])]).buffer(0)
    S["roof"] = dict(poly=[list(c) for c in fp.exterior.coords[:-1]], z=top["elev"] + top["height"])
    # spawn outside the first exterior door on the ground level
    ext = [o for o in d["openings"] if o["kind"] == "door" and o.get("exterior") and b.get("walls", o["wall"])["level"] == order[0]["id"]]
    for o in sorted(ext, key=lambda o: -o["width"]):
        w = b.get("walls", o["wall"])
        if True:
            from .validate import opening_center, wall_normal, locate
            c = opening_center(b, o); n = wall_normal(w)
            sg = 1 if locate(b, w["level"], (c[0] + n[0], c[1] + n[1])) is None else -1
            S["spawn"] = dict(x=c[0] + n[0] * sg * 14, y=c[1] + n[1] * sg * 14, yaw=math.atan2(n[0] * sg, n[1] * sg))
            break
    x0 = min(p[0] for p in S["roof"]["poly"]); y0 = min(p[1] for p in S["roof"]["poly"])
    x1 = max(p[0] for p in S["roof"]["poly"]); y1 = max(p[1] for p in S["roof"]["poly"])
    # ground inside the overall bounds but outside the ground-floor building is walkable grade
    g0 = order[0]["id"]
    built = unary_union([b.spoly(s["id"]) for s in d["spaces"] if s["level"] == g0 and s["poly"] and not s.get("open")] + [b.walls_union(g0)])
    grade = sbox(x0, y0, x1, y1).difference(built.buffer(0.01))
    for g in (grade.geoms if grade.geom_type == "MultiPolygon" else [grade]):
        if g.area > 0.5: S["walk"].append(dict(poly=[list(c) for c in g.exterior.coords[:-1]], holes=[[list(c) for c in r.coords[:-1]] for r in g.interiors], z=order[0]["elev"], type="grade", level=g0, name="Grade", id="grade"))
    S["bounds"] = [x0, y0, x1, y1]
    return S
