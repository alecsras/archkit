from html import escape as esc
"""archkit.render - 2D plan sheets (SVG) and a 3D first-person walkthrough (HTML), both from build_scene()/model only.
Usage: python -m archkit.render model.json outdir [--report report.json]"""
import sys, os, json, math
from shapely.geometry import Polygon
from shapely.ops import unary_union
from .model import load, SPACE, OBJ
from .scene import build_scene, wall_frame
from .validate import swing_polys, opening_center

K = 12.0   # px per foot
FILL = {"guest_room": "#f3efe6", "bedroom": "#f3efe6", "bath": "#e3eef3", "restroom": "#e3eef3", "corridor": "#f7f7f5", "lobby": "#f6ecdc",
        "stair": "#eceff3", "elevator": "#e5e7eb", "shaft": "#d6d3d1", "office": "#eef2f7", "storage": "#f1f0ee", "laundry": "#e9f0f6",
        "mechanical": "#ececec", "living": "#f3efe6", "kitchen": "#f1efe8", "dining": "#f6ecdc", "closet": "#f1f0ee", "balcony": "#f0f4ec", "retail": "#f6ecdc"}


def plan_svg(b, lid, report=None):
    b.trace(); d = b.d
    ws = [w for w in d["walls"] if w["level"] == lid]
    ends = b.wall_ends(lid)
    U = unary_union([b.wall_body(w, ends)[0] for w in ws])
    x0, y0, x1, y1 = U.bounds; M = 6
    W, H = (x1 - x0 + 2 * M) * K, (y1 - y0 + 2 * M) * K + 60
    X = lambda x: (x - x0 + M) * K; Y = lambda y: (y - y0 + M) * K + 60
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" font-family="Helvetica,Arial,sans-serif"><rect width="100%" height="100%" fill="#fff"/>']
    o.append(f'<text x="20" y="34" font-size="22" font-weight="700">{esc(d["name"])} - {lid}</text>')
    def poly(pts, **a):
        attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in a.items())
        return f'<polygon points="{" ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)}" {attrs}/>'
    for s in d["spaces"]:
        if s["level"] != lid or not s["poly"]: continue
        o.append(poly(s["poly"], fill=FILL.get(s["type"], "#f5f5f5"), stroke="none"))
        p = b.spoly(s["id"]); c = p.representative_point()
        o.append(f'<text x="{X(c.x):.1f}" y="{Y(c.y):.1f}" font-size="11" text-anchor="middle" font-weight="700" fill="#334155">{esc(s["name"])}</text>')
        o.append(f'<text x="{X(c.x):.1f}" y="{Y(c.y) + 13:.1f}" font-size="9" text-anchor="middle" fill="#64748b">{p.area:.0f} SF</text>')
    # walls minus openings
    cut = []
    for op in d["openings"]:
        w = next((w for w in ws if w["id"] == op["wall"]), None)
        if not w: continue
        ax, ay, ux, uy, n, L = wall_frame(w); h = w["t"] / 2 + 0.02
        a, c = op["offset"], op["offset"] + op["width"]
        cut.append(Polygon([(ax + ux * a + n[0] * h, ay + uy * a + n[1] * h), (ax + ux * c + n[0] * h, ay + uy * c + n[1] * h),
                            (ax + ux * c - n[0] * h, ay + uy * c - n[1] * h), (ax + ux * a - n[0] * h, ay + uy * a - n[1] * h)]))
        if op["kind"] == "window":
            o.append(f'<line x1="{X(ax + ux * a):.1f}" y1="{Y(ay + uy * a):.1f}" x2="{X(ax + ux * c):.1f}" y2="{Y(ay + uy * c):.1f}" stroke="#2563eb" stroke-width="2"/>')
    solid = U.difference(unary_union(cut)) if cut else U
    for g in (solid.geoms if solid.geom_type == "MultiPolygon" else [solid]):
        rings = [list(g.exterior.coords)] + [list(r.coords) for r in g.interiors]
        dpath = " ".join("M" + " L".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in r) + " Z" for r in rings)
        o.append(f'<path d="{dpath}" fill="#1f2937" fill-rule="evenodd" stroke="none"/>')
    # doors
    for op in d["openings"]:
        w = next((w for w in ws if w["id"] == op["wall"]), None)
        if not w or op["kind"] != "door": continue
        if op["door"] in ("swing", "double") and op["side"]:
            arc, _ = swing_polys(b, op)
            for g in (arc.geoms if arc.geom_type == "MultiPolygon" else [arc]):
                pts = list(g.exterior.coords)
                o.append(f'<polyline points="{" ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts[1:-1])}" fill="none" stroke="#94a3b8" stroke-dasharray="3,2"/>')
                o.append(f'<line x1="{X(pts[0][0]):.1f}" y1="{Y(pts[0][1]):.1f}" x2="{X(pts[-2][0]):.1f}" y2="{Y(pts[-2][1]):.1f}" stroke="#111827" stroke-width="2"/>')
        elif op["door"] in ("pocket", "slide"):
            ax, ay, ux, uy, n, L = wall_frame(w); a, c = op["offset"], op["offset"] + op["width"]
            o.append(f'<line x1="{X(ax + ux * a):.1f}" y1="{Y(ay + uy * a):.1f}" x2="{X(ax + ux * c):.1f}" y2="{Y(ay + uy * c):.1f}" stroke="#111827" stroke-width="2" stroke-dasharray="6,3"/>')
    for g in d.get("guards", []):
        if g["level"] == lid: o.append(f'<line x1="{X(g["a"][0]):.1f}" y1="{Y(g["a"][1]):.1f}" x2="{X(g["b"][0]):.1f}" y2="{Y(g["b"][1]):.1f}" stroke="#0f172a" stroke-width="3"/>')
    # stairs
    for st in d["stairs"]:
        if st["level_from"] != lid and st["level_to"] != lid: continue
        o.append(poly(st["footprint"], fill="none", stroke="#475569", stroke_width="1"))
        for f in st["flights"]:
            (sx, sy), (ex, ey) = f["start"], f["end"]; L = math.dist(f["start"], f["end"]); ux, uy = (ex - sx) / L, (ey - sy) / L; nx, ny = -uy, ux
            for i in range(f["risers"]):
                cx, cy = sx + ux * i * st["tread"], sy + uy * i * st["tread"]
                o.append(f'<line x1="{X(cx - nx * f["width"] / 2):.1f}" y1="{Y(cy - ny * f["width"] / 2):.1f}" x2="{X(cx + nx * f["width"] / 2):.1f}" y2="{Y(cy + ny * f["width"] / 2):.1f}" stroke="#64748b" stroke-width="0.8"/>')
            o.append(f'<line x1="{X(sx):.1f}" y1="{Y(sy):.1f}" x2="{X(ex):.1f}" y2="{Y(ey):.1f}" stroke="#0f172a" stroke-width="1.2" marker-end="url(#ar)"/>')
    o.insert(1, '<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#0f172a"/></marker></defs>')
    for e in d["elevators"]:
        if lid in e["levels"]:
            a, c, e2, f2 = e["rect"]
            o.append(f'<line x1="{X(a):.1f}" y1="{Y(c):.1f}" x2="{X(e2):.1f}" y2="{Y(f2):.1f}" stroke="#64748b"/><line x1="{X(e2):.1f}" y1="{Y(c):.1f}" x2="{X(a):.1f}" y2="{Y(f2):.1f}" stroke="#64748b"/>')
    # objects
    for ob in d["objects"]:
        if b.get("spaces", ob["space"])["level"] != lid: continue
        fp = b.footprint(ob); a, c, e2, f2 = fp.bounds
        wall = ob["mount"] == "wall"
        o.append(f'<rect x="{X(a):.1f}" y="{Y(c):.1f}" width="{(e2 - a) * K:.1f}" height="{(f2 - c) * K:.1f}" fill="{"#fde68a" if wall else "#fff"}" stroke="#57534e" stroke-width="1"/>')
        if (e2 - a) * K > 30 and (f2 - c) * K > 14:
            o.append(f'<text x="{X((a + e2) / 2):.1f}" y="{Y((c + f2) / 2) + 3:.1f}" font-size="8" text-anchor="middle" fill="#57534e">{esc(ob["label"].replace("_", " "))}</text>')
    # devices
    for dv in d["devices"]:
        s = b.get("spaces", dv["space"])
        if s["level"] != lid: continue
        col = {"light": "#ca8a04", "smoke_alarm": "#e11d48", "exhaust_fan": "#7c3aed"}.get(dv["type"], "#c2410c")
        o.append(f'<circle cx="{X(dv["x"]):.1f}" cy="{Y(dv["y"]):.1f}" r="3.2" fill="{col}"/>')
    # validation issues
    if report:
        for it in report["items"]:
            if it.get("level") == lid and it.get("at"):
                col = "#dc2626" if it["sev"] == "ERROR" else "#f59e0b"
                o.append(f'<circle cx="{X(it["at"][0]):.1f}" cy="{Y(it["at"][1]):.1f}" r="10" fill="none" stroke="{col}" stroke-width="2.5"/>')
                o.append(f'<text x="{X(it["at"][0]) + 12:.1f}" y="{Y(it["at"][1]) - 8:.1f}" font-size="9" fill="{col}" font-weight="700">{it["code"]}</text>')
    o.append("</svg>")
    return "\n".join(o)


def walk_html(b, title=None):
    S = build_scene(b)
    tpl = open(os.path.join(os.path.dirname(__file__), "walk_template.html")).read()
    return tpl.replace("__TITLE__", title or b.d["name"]).replace("__SCENE__", json.dumps(S, separators=(",", ":")))


def main():
    path, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
    b = load(path)
    rep = json.load(open(sys.argv[sys.argv.index("--report") + 1])) if "--report" in sys.argv else None
    for L in b.d["levels"]:
        open(os.path.join(out, f"plan_{L['id']}.svg"), "w").write(plan_svg(b, L["id"], rep))
    open(os.path.join(out, "walkthrough.html"), "w").write(walk_html(b))
    print("rendered to", out)


if __name__ == "__main__":
    main()
