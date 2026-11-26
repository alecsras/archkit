"""Sample: 2-story, 9-key inn. 64' x 46', double-loaded corridor, 2 stairs, elevator."""
import sys; sys.path.insert(0, __file__.rsplit("/examples", 1)[0])
from archkit.model import Building

b = Building("Two-Story Inn", occupancy="R-1", sprinklered=True, accessible=True)
LV = [b.level("L1", 0, 10.0, 8.5), b.level("L2", 10.0, 10.0, 8.0)]
EXT, INT = 0.67, 0.5
NY, CY0, CY1, SY = 0.0, 20.0, 26.0, 46.0   # north wall, corridor walls, south wall


def M(y, south):   # mirror a north-row y to the south row
    return SY - y if south else y


def F(f, south):   # mirror a facing
    return {"N": "S", "S": "N"}.get(f, f) if south else f


def guest_room(L, x0, x1, num, south=False, acc=False, bw=None, big=False):
    bw = bw or (8.5 if (acc or big) else (5.67 if x0 == 0 else 5.5))   # bath width to wet-wall centerline
    by = 11.0 if (acc or big) else 12.0                        # bath back wall (north-row y)
    xb = x0 + bw
    wb = b.wall(L, (xb, M(by, south)), (xb, M(CY0, south)), t=INT, kind="interior", wet=True)
    b.wall(L, (x0, M(by, south)), (xb, M(by, south)), t=INT, kind="interior", wet=True)
    room = b.space(L, ((x0 + x1) / 2, M(5, south)), f"Room {num}", "guest_room", accessible=acc)
    bath = b.space(L, (x0 + 1.5, M(CY0 - 1.5, south)), f"Bath {num}", "bath", accessible=acc)
    cw = b.wall_at(L, (x0 + 1, M(CY0, south)))
    ex = b.wall_at(L, (x0 + 1, M(NY, south)))
    b.door(cw, center=(xb + 3.25, M(CY0, south)), width=3.0, hinge="start", into=(xb + 3.25, M(CY0 - 2, south)))
    if acc: b.door(wb, center=(xb, M(by + 4.25, south)), width=3.0, kind="pocket")
    else: b.door(wb, center=(xb, M(by + 3.6, south)), width=2.84, hinge="start", into=(xb + 2, M(by + 3.6, south)))
    b.window(ex, center=((x0 + x1) / 2 + 1.5, M(NY, south)), width=5.0, height=4.5, sill=2.5)
    b.trace()
    rx0, ry0, rx1, ry1 = b.spoly(room).bounds
    yc = M(5.6, south)
    b.obj(room, "bed_queen", against="W", along=yc)
    b.obj(room, "nightstand", against="W", along=yc - 3.4 if not south else yc + 3.4)
    b.obj(room, "dresser", against="E", along=yc, w=4.5)
    b.obj(room, "tv_wall", against="E", along=yc)
    b.obj(room, "ptac", against=F("N", south), along=x1 - 2.4)
    b.obj(room, "desk", against=F("N", south), along=rx0 + 9.6, w=3.5)
    b.obj(room, "chair", x=rx0 + 8.75, y=M(3.2, south) - (1.7 if south else 0))
    b.obj(room, "wardrobe", against="E", along=M(by + (1.6 if (acc or big) else 2.3), south), w=2.5 if (acc or big) else 3.0)
    bx0, by0, bx1, by1 = b.spoly(bath).bounds
    if acc:
        b.obj(bath, "shower_rollin", against="W", along=(by0 + by1) / 2 + (0.6 if south else -0.6))
        b.obj(bath, "toilet_ada", against=F("S", south), along=bx1 - 1.42)
        b.obj(bath, "lavatory_ada", against=F("N", south), along=bx1 - 1.6)
    else:   # tub across the corridor wall; toilet + lav on the back (wet) wall
        b.obj(bath, "tub", against=F("S", south), along=(bx0 + bx1) / 2)
        b.obj(bath, "toilet", against=F("N", south), along=bx0 + 1.25)
        b.obj(bath, "lavatory", against=F("N", south), along=bx1 - 1.0)
    b.device(room, "light", (rx0 + rx1) / 2, M(6, south)); b.device(room, "smoke_alarm", (rx0 + rx1) / 2, M(8.5, south))
    b.device(room, "receptacle", rx1, M(9, south)); b.device(room, "receptacle", rx0, M(9.5, south))
    b.device(room, "switch", xb + 1.0, M(CY0 - 0.25, south))   # latch-side wall between bath wall and door jamb
    b.device(bath, "light", (bx0 + bx1) / 2, (by0 + by1) / 2); b.device(bath, "exhaust_fan", (bx0 + bx1) / 2 + 0.8, (by0 + by1) / 2)
    b.device(bath, "gfci", bx1 - (1.6 if acc else 1.0), by1 if south else by0)   # above the lavatory, on its wall
    return room


for L in ("L1", "L2"):
    b.rect_walls(L, 0, NY, 64, SY, t=EXT, kind="exterior")
    b.wall(L, (0, CY0), (64, CY0), t=INT, kind="corridor", bearing=True)
    b.wall(L, (0, CY1), (64, CY1), t=INT, kind="corridor", bearing=True)
    for x in (12, 20, 36, 52): b.wall(L, (x, NY), (x, CY0), t=INT, kind="demising")
    b.wall(L, (12, 10), (20, 10), t=INT, kind="shaft")
    corr = b.space(L, (32, 23), "Corridor", "corridor")
    b.space(L, (6, 10), "Stair A", "stair"); b.space(L, (58, 10), "Stair B", "stair")
    b.space(L, (16, 15), "Elevator", "elevator"); b.space(L, (16, 5), "Chase", "shaft")
    cn = b.wall_at(L, (5, CY0))
    b.door(cn, center=(9.5, CY0), width=3.0, hinge="end", into=(9.5, 18))
    b.door(cn, center=(55.0, CY0), width=3.0, hinge="start", into=(55.0, 18))
    b.door(cn, center=(16.0, CY0), width=3.5, kind="slide")
    for x in (8, 22, 36, 50, 60): b.device(corr, "light", x, 23)
    b.device(corr, "smoke_alarm", 32, 23)
    for s in ("Stair A", "Stair B"):
        sid = next(x["id"] for x in b.d["spaces"] if x["name"] == s and x["level"] == L)
        b.device(sid, "light", 6 if s == "Stair A" else 58, 18)

b.elevator("E1", ["L1", "L2"], (12.25, 10.25, 19.75, 19.75))
# stairs fill their enclosures wall-to-wall: no open edges (validator C-STAIR-GUARD)
SW = (11.75 - 0.335 - 0.33) / 2                    # flight width so two flights + gap span the enclosure
RUN = 8 * 11 / 12; LAND = max(SW, 4.0)
b.stair_u("ST-A", "L1", "L2", 0.335, 0.335 + RUN + LAND, width=SW, up="N")
b.stair_u("ST-B", "L1", "L2", 52.25, 0.335 + RUN + LAND, width=SW, up="N")
# stair exterior exit doors (L1)
b.door(b.wall_at("L1", (0, 5)), center=(0, 18), width=3.0, hinge="start", into=(-2, 18), exterior=True)
b.door(b.wall_at("L1", (64, 5)), center=(64, 18), width=3.0, hinge="end", into=(66, 18), exterior=True)

# ---------- L1 ----------
guest_room("L1", 20, 36, "101", acc=True)
guest_room("L1", 36, 52, "102")
for x in (24, 32, 40, 48): b.wall("L1", (x, CY1), (x, SY), t=INT, kind="interior", wet=(x == 40))
b.wall("L1", (32, 36), (40, 36), t=INT, kind="interior"); b.wall("L1", (40, 36), (48, 36), t=INT, kind="interior")
lobby = b.space("L1", (12, 36), "Lobby", "lobby", ceiling=8.5)
office = b.space("L1", (28, 36), "Office", "office")
rr = b.space("L1", (36, 30), "Restroom", "restroom", accessible=True)
stor = b.space("L1", (36, 41), "Storage", "storage")
laun = b.space("L1", (44, 30), "Laundry", "laundry")
mech = b.space("L1", (44, 41), "Mechanical", "mechanical")
cs = b.wall_at("L1", (5, CY1))
b.door(cs, center=(12, CY1), width=10.0, kind="cased")
b.door(cs, center=(28, CY1), width=3.0, hinge="start", into=(28, 28))
b.door(cs, center=(36, CY1), width=3.0, hinge="end", into=(35, 28.5))
b.door(cs, center=(44, CY1), width=3.0, hinge="start", into=(44, 28))
b.door(b.wall_at("L1", (32, 40)), center=(32, 41.5), width=3.0, hinge="start", into=(34, 41.5))
south = b.wall_at("L1", (5, SY))
b.door(south, center=(12, SY), width=6.0, kind="double", into=(12, SY + 2), exterior=True)
b.door(south, center=(44, SY), width=3.0, hinge="start", into=(44, SY + 2), exterior=True)
for xc in (5, 19): b.window(south, center=(xc, SY), width=5.0, sill=2.5)
b.window(south, center=(28, SY), width=4.0, sill=3.0)
b.wall("L1", (48, 26), (48, 46), t=INT, kind="demising") if False else None
guest_room("L1", 48, 64, "103", south=True)
b.trace()
b.obj(lobby, "reception_desk", x=18.0, y=33.0, facing="W", w=8.0)
b.obj(lobby, "sofa", against="W", along=38.0)
b.obj(lobby, "coffee_table", x=5.0, y=37.0, facing="W")
b.obj(lobby, "armchair", x=9.0, y=31.0, facing="S")
b.obj(lobby, "planter", x=1.0, y=43.0)
b.obj(office, "desk", against="E", along=38.0)
b.obj(office, "chair", x=28.0, y=37.2)
b.obj(office, "shelving", against="S", along=26.0, w=3.5)
b.obj(rr, "toilet_ada", against="N", along=39.75 - 1.42)
b.obj(rr, "lavatory_ada", against="E", along=33.0)
b.obj(laun, "washer", against="S", along=42.0); b.obj(laun, "dryer", against="S", along=44.6)
b.obj(stor, "shelving", against="E", along=40.0, w=6.0)
b.obj(mech, "equipment", against="N", along=46.0, w=3.0, label="water heater")
for sp_, pts in ((lobby, [(8, 33), (8, 40), (16, 37)]), (office, [(28, 36)]), (rr, [(36, 31)]), (stor, [(36, 41)]), (laun, [(44, 31)]), (mech, [(44, 41)])):
    for x, y in pts: b.device(sp_, "light", x, y)
b.device(rr, "exhaust_fan", 36, 32); b.device(office, "receptacle", 24.25, 40); b.device(lobby, "receptacle", 0.335, 30)

# ---------- L2 ----------
guest_room("L2", 20, 36, "201", big=True); guest_room("L2", 36, 52, "202")
for x in (16, 32, 48): b.wall("L2", (x, CY1), (x, SY), t=INT, kind="demising")
for i, x0 in enumerate((0, 16, 32, 48)): guest_room("L2", x0, x0 + 16, f"20{3 + i}", south=True, bw=8.0 if x0 == 32 else None, big=(x0 == 32))

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "inn.json"
    b.save(out); print("saved", out)
