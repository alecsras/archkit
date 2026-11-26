"""archkit.model - single source of truth for a building.
Units: feet. Plan axes: +x east, +y south (screen-down). Elevation z up.
Rules baked in:
  * rooms (spaces) are TRACED from the walls, never typed - a wall gap shows up as a leak
  * every height is DERIVED (floor, ceiling, wall face, host object) - nothing can float
"""
import json, math
from shapely.geometry import Polygon, LineString, Point, box as sbox, mapping, shape
from shapely.ops import unary_union

TOL = 0.02
FACING = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}

# ---------------- catalogs ----------------
# object type: w = width across its front, d = depth front-to-back, h = height,
# clear = required free zones {front, sides, back} in ft, block = obstructs walking
OBJ = {
    "bed_king": dict(w=6.33, d=6.67, h=2.1, clear=dict(front=2.5, sides=2.5)),
    "bed_queen": dict(w=5.0, d=6.67, h=2.1, clear=dict(front=2.5, sides=2.5)),
    "bed_full": dict(w=4.5, d=6.25, h=2.1, clear=dict(front=2.5, sides=2.0)),
    "bed_twin": dict(w=3.25, d=6.25, h=2.1, clear=dict(front=2.5, sides=2.0)),
    "nightstand": dict(w=1.67, d=1.5, h=2.1, clear={}),
    "dresser": dict(w=5.0, d=1.67, h=2.6, clear=dict(front=3.0)),
    "desk": dict(w=4.0, d=2.0, h=2.5, clear=dict(front=3.0)),
    "chair": dict(w=1.7, d=1.7, h=2.8, clear={}, movable=True),
    "armchair": dict(w=2.7, d=2.7, h=2.8, clear=dict(front=1.5)),
    "sofa": dict(w=7.0, d=3.0, h=2.8, clear=dict(front=1.5)),
    "coffee_table": dict(w=4.0, d=2.0, h=1.4, clear={}),
    "table_4": dict(w=3.5, d=3.5, h=2.5, clear=dict(front=2.5, sides=2.5, back=2.5)),
    "table_round_4": dict(w=3.5, d=3.5, h=2.5, clear=dict(front=2.5, sides=2.5, back=2.5)),
    "wardrobe": dict(w=3.0, d=2.0, h=7.0, clear=dict(front=3.0)),
    "shelving": dict(w=4.0, d=1.5, h=7.0, clear=dict(front=3.0)),
    "tv_wall": dict(w=4.0, d=0.25, h=2.4, clear={}, mount="wall", elev=3.6, block=False),
    "mirror": dict(w=3.0, d=0.08, h=3.0, clear={}, mount="wall", elev=3.4, block=False),
    "toilet": dict(w=1.67, d=2.5, h=2.5, clear=dict(front=1.75, sides=0.42), plumb=True),
    "toilet_ada": dict(w=1.67, d=2.5, h=2.5, clear={}, plumb=True, ada_wc=True),
    "lavatory": dict(w=2.0, d=1.75, h=2.83, clear=dict(front=2.5), plumb=True),
    "lavatory_ada": dict(w=2.0, d=1.75, h=2.83, clear=dict(front=4.0), plumb=True, knee=True),
    "vanity": dict(w=4.0, d=1.83, h=2.83, clear=dict(front=2.5), plumb=True),
    "tub": dict(w=5.0, d=2.5, h=1.67, clear=dict(front=1.75), plumb=True),
    "shower": dict(w=3.0, d=3.0, h=0.1, clear=dict(front=2.5), plumb=True),
    "shower_rollin": dict(w=5.0, d=2.5, h=0.05, clear=dict(front=2.5), plumb=True, block=False),
    "kitchen_counter": dict(w=6.0, d=2.08, h=3.0, clear=dict(front=3.5)),
    "kitchen_sink": dict(w=3.0, d=2.08, h=3.0, clear=dict(front=3.5), plumb=True),
    "range": dict(w=2.5, d=2.17, h=3.0, clear=dict(front=3.5)),
    "fridge": dict(w=3.0, d=2.5, h=6.0, clear=dict(front=3.5)),
    "washer": dict(w=2.25, d=2.25, h=3.2, clear=dict(front=3.0), plumb=True),
    "dryer": dict(w=2.25, d=2.25, h=3.2, clear=dict(front=3.0)),
    "reception_desk": dict(w=8.0, d=2.5, h=3.5, clear=dict(front=4.0, back=3.0)),
    "counter": dict(w=6.0, d=2.0, h=3.0, clear=dict(front=3.0)),
    "vending": dict(w=3.0, d=2.75, h=6.0, clear=dict(front=3.0)),
    "ptac": dict(w=3.5, d=1.25, h=1.4, clear=dict(front=1.5)),
    "equipment": dict(w=3.0, d=3.0, h=6.0, clear=dict(front=3.0)),
    "planter": dict(w=2.0, d=2.0, h=3.0, clear={}),
}
# space types: olf = occupant load factor (sf/person, gross unless noted), hab = habitable,
# need = required devices, walk = people move through it
SPACE = {
    "bedroom": dict(olf=200, hab=True, need=["light", "smoke_alarm", "receptacle"], sleep=True),
    "guest_room": dict(olf=200, hab=True, need=["light", "smoke_alarm", "receptacle"], sleep=True),
    "living": dict(olf=200, hab=True, need=["light", "receptacle"]),
    "kitchen": dict(olf=200, hab=False, need=["light", "gfci"]),
    "bath": dict(olf=200, hab=False, need=["light", "exhaust_fan", "gfci"], min_clg=7.0),
    "restroom": dict(olf=200, hab=False, need=["light", "exhaust_fan"], min_clg=7.0),
    "closet": dict(olf=300, hab=False, need=[], min_clg=7.0, nopass=True),
    "corridor": dict(olf=0, hab=False, need=["light"], corridor=True),
    "lobby": dict(olf=15, hab=False, need=["light"]),
    "dining": dict(olf=15, hab=False, need=["light"]),
    "office": dict(olf=150, hab=True, need=["light", "receptacle"]),
    "storage": dict(olf=300, hab=False, need=["light"]),
    "laundry": dict(olf=300, hab=False, need=["light"]),
    "mechanical": dict(olf=300, hab=False, need=["light"]),
    "retail": dict(olf=60, hab=False, need=["light"]),
    "stair": dict(olf=0, hab=False, need=["light"], vertical=True),
    "elevator": dict(olf=0, hab=False, need=[], vertical=True),
    "shaft": dict(olf=0, hab=False, need=[], walk=False, vertical=True),
    "balcony": dict(olf=0, hab=False, need=[], exterior=True),
}
DEVICE_MOUNT = {"light": "ceiling", "light_pendant": "ceiling", "exhaust_fan": "ceiling", "smoke_alarm": "ceiling", "sprinkler": "ceiling",
                "diffuser": "ceiling", "wall_sconce": ("wall", 5.5), "receptacle": ("wall", 1.5), "gfci": ("wall", 3.5),
                "switch": ("wall", 4.0), "thermostat": ("wall", 4.0), "panel": ("wall", 5.0), "exit_sign": ("wall", 7.2),
                "pull_station": ("wall", 4.0), "horn_strobe": ("wall", 7.0), "camera": ("wall", 8.0), "fire_extinguisher": ("wall", 3.5),
                "floor_drain": "floor", "floor_box": "floor"}


class Building:
    def __init__(self, name, code="IBC2021", occupancy="R-1", sprinklered=True, accessible=True, residential_interior=False):
        self.d = dict(name=name, code=code, occupancy=occupancy, sprinklered=sprinklered, accessible=accessible,
                      residential_interior=residential_interior, levels=[], walls=[], openings=[], spaces=[], objects=[],
                      devices=[], stairs=[], elevators=[])
        self._n = 0

    # ---------- ids ----------
    def _id(self, p):
        self._n += 1
        return f"{p}{self._n}"

    def lvl(self, lid):
        for L in self.d["levels"]:
            if L["id"] == lid: return L
        raise KeyError(lid)

    def get(self, coll, oid):
        for e in self.d[coll]:
            if e["id"] == oid: return e
        raise KeyError(oid)

    # ---------- levels ----------
    def level(self, lid, elev, height=10.0, ceiling=8.0, slab=1.0):
        self.d["levels"].append(dict(id=lid, elev=elev, height=height, ceiling=ceiling, slab=slab))
        return lid

    # ---------- walls ----------
    def wall(self, level, a, b, t=0.5, kind="interior", bearing=None, wet=False, rating=0, h=None, free_end=False):
        if bearing is None: bearing = kind in ("exterior", "shaft")
        wid = self._id("W")
        self.d["walls"].append(dict(id=wid, level=level, a=list(map(float, a)), b=list(map(float, b)), t=t, kind=kind,
                                    bearing=bearing, wet=wet, rating=rating, h=h, free_end=free_end))
        return wid

    def loop(self, level, pts, t=0.5, kind="exterior", **kw):
        return [self.wall(level, pts[i], pts[(i + 1) % len(pts)], t=t, kind=kind, **kw) for i in range(len(pts))]

    def rect_walls(self, level, x0, y0, x1, y1, **kw):
        return self.loop(level, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **kw)

    def wall_at(self, level, p, q=None):
        """find the wall whose centerline passes through point p (and q if given)"""
        P = Point(p)
        for w in self.d["walls"]:
            if w["level"] != level: continue
            ls = LineString([w["a"], w["b"]])
            if ls.distance(P) < 0.05 and (q is None or ls.distance(Point(q)) < 0.05): return w["id"]
        raise KeyError(f"no wall through {p} on {level}")

    # ---------- openings ----------
    def _open(self, wall, center=None, offset=None, width=3.0, **kw):
        w = self.get("walls", wall)
        L = math.dist(w["a"], w["b"])
        if center is not None:
            ax, ay = w["a"]; bx, by = w["b"]
            s = ((center[0] - ax) * (bx - ax) + (center[1] - ay) * (by - ay)) / L
            offset = s - width / 2
        oid = self._id("O")
        o = dict(id=oid, wall=wall, offset=round(offset, 4), width=width)
        o.update(kw)
        self.d["openings"].append(o)
        return oid

    def door(self, wall, center=None, offset=None, width=3.0, height=6.67, hinge="start", into=None, kind="swing",
             exterior=False, route=True):
        """into: a point (x,y) on the side the leaf swings toward. hinge: 'start'|'end' end of the opening along a->b.
        kind: swing | pocket | slide | double | cased (no leaf)."""
        side = 0
        if into is not None and kind in ("swing", "double"):
            w = self.get("walls", wall)
            ax, ay = w["a"]; bx, by = w["b"]
            cross = (bx - ax) * (into[1] - ay) - (by - ay) * (into[0] - ax)
            side = 1 if cross > 0 else -1
        return self._open(wall, center, offset, width, kind="door", door=kind, height=height, sill=0.0, hinge=hinge,
                          side=side, exterior=exterior, route=route)

    def window(self, wall, center=None, offset=None, width=4.0, height=4.5, sill=3.0):
        return self._open(wall, center, offset, width, kind="window", height=height, sill=sill)

    # ---------- geometry helpers ----------
    def wall_ends(self, level):
        """for each wall end: list of joined walls (by point-on-centerline test)"""
        ws = [w for w in self.d["walls"] if w["level"] == level]
        out = {}
        for w in ws:
            for end in ("a", "b"):
                P = Point(w[end]); j = []
                for v in ws:
                    if v is w: continue
                    if LineString([v["a"], v["b"]]).distance(P) < TOL: j.append(v["id"])
                out[(w["id"], end)] = j
        return out

    def wall_body(self, w, ends=None, ext=True):
        """rectangle around the centerline; joined ends extended by half the other wall's thickness"""
        ax, ay = w["a"]; bx, by = w["b"]
        L = math.dist(w["a"], w["b"]); ux, uy = (bx - ax) / L, (by - ay) / L
        ea = eb = 0.0
        if ext and ends is not None:
            V = {v["id"]: v for v in self.d["walls"]}
            def corner(end, j):   # extend only at true corners (end meets the other wall's END); T-joints stop at the centerline
                return min(math.dist(w[end], V[j]["a"]), math.dist(w[end], V[j]["b"])) < TOL
            ea = max([V[j]["t"] / 2 for j in ends.get((w["id"], "a"), []) if corner("a", j)] or [0])
            eb = max([V[j]["t"] / 2 for j in ends.get((w["id"], "b"), []) if corner("b", j)] or [0])
        s0, s1 = -ea, L + eb
        nx, ny = -uy, ux; h = w["t"] / 2
        pts = [(ax + ux * s0 + nx * h, ay + uy * s0 + ny * h), (ax + ux * s1 + nx * h, ay + uy * s1 + ny * h),
               (ax + ux * s1 - nx * h, ay + uy * s1 - ny * h), (ax + ux * s0 - nx * h, ay + uy * s0 - ny * h)]
        return Polygon(pts), (s0, s1)

    def walls_union(self, level):
        ends = self.wall_ends(level)
        return unary_union([self.wall_body(w, ends)[0] for w in self.d["walls"] if w["level"] == level])

    # ---------- spaces (traced) ----------
    def space(self, level, point, name, type, ceiling=None, accessible=False, finish=None, exterior_open=False):
        """Trace the enclosed region containing `point`. exterior_open spaces (balconies, porches) take a rectangle via rect=."""
        sid = self._id("S")
        self.d["spaces"].append(dict(id=sid, level=level, seed=list(point), name=name, type=type, ceiling=ceiling,
                                     accessible=accessible, finish=finish, poly=None))
        return sid

    def open_space(self, level, rect, name, type="balcony", ceiling=None, finish=None):
        """unenclosed space (balcony, porch, walkway): give its rectangle explicitly"""
        sid = self._id("S")
        x0, y0, x1, y1 = rect
        self.d["spaces"].append(dict(id=sid, level=level, seed=[(x0 + x1) / 2, (y0 + y1) / 2], name=name, type=type, ceiling=ceiling,
                                     accessible=False, finish=finish, poly=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], open=True))
        return sid

    def trace(self):
        """resolve every traced space polygon from the walls. Leaks are recorded for the validator."""
        self.d["_trace"] = []
        for L in self.d["levels"]:
            regs, frame = None, None
            for s in self.d["spaces"]:
                if s["level"] != L["id"] or s.get("open"): continue
                if regs is None:
                    U = self.walls_union(L["id"]); x0, y0, x1, y1 = U.bounds
                    frame = sbox(x0 - 5, y0 - 5, x1 + 5, y1 + 5); rest = frame.difference(U)
                    regs = list(rest.geoms) if rest.geom_type == "MultiPolygon" else [rest]
                P = Point(s["seed"]); hit = [g for g in regs if g.contains(P)]
                if not hit:
                    s["poly"] = None; self.d["_trace"].append(dict(space=s["id"], problem="seed inside a wall or off-plan")); continue
                g = hit[0]
                if g.exterior.distance(Point(frame.exterior.coords[0])) < 0.01 or g.intersects(frame.exterior):
                    s["poly"] = None; self.d["_trace"].append(dict(space=s["id"], problem="LEAK: region is open to the outside (gap in walls)"))
                    continue
                g = g.simplify(0.001)
                s["poly"] = [list(map(lambda v: round(v, 4), c)) for c in g.exterior.coords[:-1]]
                s["holes"] = [[list(map(lambda v: round(v, 4), c)) for c in r.coords[:-1]] for r in g.interiors]
        # two seeds in one region = missing wall between them
        for L in self.d["levels"]:
            ss = [s for s in self.d["spaces"] if s["level"] == L["id"] and s["poly"] and not s.get("open")]
            for i in range(len(ss)):
                for j in range(i + 1, len(ss)):
                    if Polygon(ss[i]["poly"]).contains(Point(ss[j]["seed"])):
                        self.d["_trace"].append(dict(space=ss[j]["id"], problem=f"shares one region with {ss[i]['name']} (missing wall)"))
        return self

    def spoly(self, sid):
        s = self.get("spaces", sid)
        return Polygon(s["poly"], s.get("holes") or [])

    # ---------- objects ----------
    def obj(self, space, type, x=None, y=None, facing="S", against=None, along=None, gap=0.0, w=None, d=None, h=None,
            mount=None, elev=None, on=None, label=None):
        """Place a catalog object.
        Either give the min-corner (x, y) of its footprint, or `against`='N'|'S'|'E'|'W' (back flush to that wall of the
        space's bounding box, facing away) plus `along` = coordinate of the object's CENTER along that wall."""
        c = OBJ[type]
        w = w or c["w"]; d = d or c["d"]; h = h or c["h"]
        if against:
            facing = OPP[against]
            s = self.get("spaces", space)
            if s["poly"] is None: self.trace()
            bx0, by0, bx1, by1 = self.spoly(space).bounds
            fw, fd = (w, d) if facing in "NS" else (d, w)
            if against == "N": x, y = along - fw / 2, by0 + gap
            if against == "S": x, y = along - fw / 2, by1 - fd - gap
            if against == "W": x, y = bx0 + gap, along - fd / 2
            if against == "E": x, y = bx1 - fw - gap, along - fd / 2
        oid = self._id("F")
        self.d["objects"].append(dict(id=oid, space=space, type=type, x=round(x, 4), y=round(y, 4), facing=facing, w=w, d=d, h=h,
                                      mount=mount or c.get("mount", "floor"), elev=c.get("elev", 0.0) if elev is None else elev,
                                      on=on, label=label or type))
        return oid

    def footprint(self, o):
        fw, fd = (o["w"], o["d"]) if o["facing"] in "NS" else (o["d"], o["w"])
        return sbox(o["x"], o["y"], o["x"] + fw, o["y"] + fd)

    def clear_zones(self, o):
        """required clear areas in plan, by name"""
        c = OBJ[o["type"]]["clear"]; fp = self.footprint(o); x0, y0, x1, y1 = fp.bounds
        f = o["facing"]; Z = {}
        def z(side, depth):
            if side == "N": return sbox(x0, y0 - depth, x1, y0)
            if side == "S": return sbox(x0, y1, x1, y1 + depth)
            if side == "W": return sbox(x0 - depth, y0, x0, y1)
            if side == "E": return sbox(x1, y0, x1 + depth, y1)
        if c.get("front"): Z["front"] = z(f, c["front"])
        if c.get("back"): Z["back"] = z(OPP[f], c["back"])
        if c.get("sides"):
            L4 = 4.0
            if f == "S": Z["side1"] = sbox(x1, max(y0, y1 - L4), x1 + c["sides"], y1); Z["side2"] = sbox(x0 - c["sides"], max(y0, y1 - L4), x0, y1)
            if f == "N": Z["side1"] = sbox(x1, y0, x1 + c["sides"], min(y1, y0 + L4)); Z["side2"] = sbox(x0 - c["sides"], y0, x0, min(y1, y0 + L4))
            if f == "E": Z["side1"] = sbox(max(x0, x1 - L4), y0 - c["sides"], x1, y0); Z["side2"] = sbox(max(x0, x1 - L4), y1, x1, y1 + c["sides"])
            if f == "W": Z["side1"] = sbox(x0, y0 - c["sides"], min(x1, x0 + L4), y0); Z["side2"] = sbox(x0, y1, min(x1, x0 + L4), y1 + c["sides"])
        if OBJ[o["type"]].get("ada_wc"):
            Z["ada_wc"] = self.ada_wc_zone(o)
        return Z

    def ada_wc_zone(self, o):
        """ADA 604.3: 60" wide measured from the side wall, 56" deep from the rear wall"""
        fp = self.footprint(o); x0, y0, x1, y1 = fp.bounds
        sb = self.spoly(o["space"]).bounds
        f = o["facing"]
        if f in "NS":
            wall_left = (x0 - sb[0]) <= (sb[2] - x1)
            xa = sb[0] if wall_left else sb[2] - 5.0
            return sbox(xa, y0, xa + 5.0, y0 + 4.67) if f == "S" else sbox(xa, y1 - 4.67, xa + 5.0, y1)
        wall_top = (y0 - sb[1]) <= (sb[3] - y1)
        ya = sb[1] if wall_top else sb[3] - 5.0
        return sbox(x0, ya, x0 + 4.67, ya + 5.0) if f == "E" else sbox(x1 - 4.67, ya, x1, ya + 5.0)

    # ---------- devices ----------
    def device(self, space, type, x, y, h=None):
        m = DEVICE_MOUNT[type]
        mount, mh = (m, None) if isinstance(m, str) else m
        did = self._id("D")
        self.d["devices"].append(dict(id=did, space=space, type=type, x=x, y=y, mount=mount, h=h if h is not None else mh))
        return did

    # ---------- vertical circulation ----------
    def stair_u(self, sid, level_from, level_to, x, y, width=3.67, up="N", gap=0.33, res=False):
        """U-shaped stair. (x, y) = bottom-left of the stair footprint as seen with 'up' pointing to the top of the page.
        Flight 1 climbs in direction `up` on the left, landing, flight 2 returns on the right."""
        L0, L1 = self.lvl(level_from), self.lvl(level_to)
        H = (L1["elev"] - L0["elev"]) * 12
        rmax, tread = (7.75, 10.0) if res else (7.0, 11.0)
        n = math.ceil(H / rmax); n += n % 2
        riser = H / n / 12; tr = tread / 12; per = n // 2
        run = (per - 1) * tr
        land = max(width, 4.0)
        # local frame: u = across (left->right), v = up direction
        dirs = {"N": ((1, 0), (0, -1)), "S": ((-1, 0), (0, 1)), "E": ((0, 1), (1, 0)), "W": ((0, -1), (-1, 0))}
        (ux, uy), (vx, vy) = dirs[up]
        def P(u, v): return [round(x + ux * u + vx * v, 4), round(y + uy * u + vy * v, 4)]
        f1 = dict(start=P(width / 2, 0), end=P(width / 2, run), width=width, risers=per, z0=0.0)
        f2 = dict(start=P(width + gap + width / 2, run), end=P(width + gap + width / 2, 0), width=width, risers=per, z0=per * riser)
        landing = [P(0, run), P(2 * width + gap, run), P(2 * width + gap, run + land), P(0, run + land)]
        foot = [P(0, -0.0), P(2 * width + gap, 0), P(2 * width + gap, run + land), P(0, run + land)]
        self.d["stairs"].append(dict(id=sid, level_from=level_from, level_to=level_to, riser=round(riser, 4), tread=tr,
                                     flights=[f1, f2], landings=[dict(poly=landing, z=per * riser)], footprint=foot, res=res,
                                     up=up, origin=[x, y], gap=gap))
        return sid

    def elevator(self, eid, levels, rect):
        self.d["elevators"].append(dict(id=eid, levels=levels, rect=list(rect)))
        return eid

    # ---------- io ----------
    def save(self, path):
        self.trace()
        json.dump(self.d, open(path, "w"), indent=1)
        return path


def flight_rect(f):
    (sx, sy), (ex, ey) = f["start"], f["end"]; L = math.dist(f["start"], f["end"]) or 1
    ux, uy = (ex - sx) / L, (ey - sy) / L; nx, ny = -uy, ux; h = f["width"] / 2
    return Polygon([(sx + nx * h, sy + ny * h), (ex + nx * h, ey + ny * h), (ex - nx * h, ey - ny * h), (sx - nx * h, sy - ny * h)])


def under_stair(st):
    """plan area under a stair's upper flights and landings (low headroom) - not walkable on the level it starts from"""
    fp = Polygon(st["footprint"]); return fp.difference(flight_rect(st["flights"][0]).buffer(0.01))


def load(path):
    b = Building("x"); b.d = json.load(open(path)); b._n = 10 ** 6
    return b
