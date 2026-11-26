"""4-level, 60-key exterior-walkway motel. 240' x 28' room bar, 12'-6" modules, 10' floor-to-floor.
Plan: +x east, +y south. North wall y=0 (back), room fronts y=28 face a 6' walkway (upper) / sidewalk (ground).
Enclosed stair towers at both ends (x 0-10, 230-240, y 0-34). Elevator + linen/vend core at x 110-130.
Ground floor centre (x 85-155): lobby + breakfast, 2 accessible restrooms, office, elevator, laundry, housekeeping, mechanical."""
import sys; sys.path.insert(0, __file__.rsplit("/examples", 1)[0])
from archkit.model import Building

b = Building("Four-Level Motel", occupancy="R-1", sprinklered=True, accessible=True)
LV = ["L1", "L2", "L3", "L4"]
for i, L in enumerate(LV): b.level(L, 10.0 * i, 10.0, 8.5 if i == 0 else 8.0)
EXT, INT = 0.67, 0.5
D, WK = 28.0, 34.0                         # room-bar depth, walkway outer edge
MOD = 12.5
WX0, WX1, EX0, EX1 = 10.0, 230.0, 0.0, 240.0
UPPER = ["K", "K", "QQ", "QQ", "QQ", "QQ", "QQ", "K", "K", "QQ", "QQ", "QQ", "QQ", "QQ", "K", "K"]
BACK_BATH = {4, 5, 10, 11}                 # modules over / at the ground-floor accessible rooms (baths stack)


def mod_x(i): return WX0 + i * MOD if i < 8 else 130.0 + (i - 8) * MOD


def room(L, x0, num, kind, mirror, acc=False, back=False, rollin=False):
    """one guest room in module x0..x0+12.5. mirror: bath on the east side."""
    x1 = x0 + MOD
    edge = x0 == WX0 or x1 == WX1
    south = b.wall_at(L, (x0 + 1, D))
    if back:   # full-width bath at the back (accessible / stacks over accessible)
        BY = 8.6
        b.wall(L, (x0, BY), (x1, BY), t=INT, kind="interior", wet=True)
        rm = b.space(L, ((x0 + x1) / 2, 18), f"Room {num}", "guest_room", accessible=acc)
        ba = b.space(L, ((x0 + x1) / 2, 4), f"Bath {num}", "bath", accessible=acc)
        b.trace()
        rx0, ry0, rx1, ry1 = b.spoly(rm).bounds; bx0, by0, bx1, by1 = b.spoly(ba).bounds
        F = (lambda u: rx1 - u) if mirror else (lambda u: rx0 + u)     # u = distance from the bed wall
        Wb, We = ("E", "W") if mirror else ("W", "E")
        dc = F(9.75)                                                   # entry door centre: latch side clear of the bed
        b.door(south, center=(dc, D), width=3.0, hinge="start" if mirror else "end", into=(dc, D - 2),
               exterior=(L == "L1"))
        b.window(south, center=(F(2.75), D), width=4.0, height=4.5, sill=2.5)
        bwall = b.wall_at(L, ((x0 + x1) / 2, BY))
        pc = (lambda u: bx1 - u) if mirror else (lambda u: bx0 + u)
        b.door(bwall, center=(pc(9.0), BY), width=3.0, kind="pocket")
        # bath: bathing on the bed-wall side, WC + lav on the far side wall
        b.obj(ba, "shower_rollin" if rollin else "tub", against=Wb, along=(by0 + by1) / 2)
        far = (lambda u: bx0 + u) if mirror else (lambda u: bx1 - u)
        b.obj(ba, "toilet_ada", against="N", along=far(1.42))
        b.obj(ba, "lavatory_ada", against="S", along=pc(6.0))
        b.device(ba, "light", (bx0 + bx1) / 2, (by0 + by1) / 2); b.device(ba, "exhaust_fan", (bx0 + bx1) / 2 + 1, (by0 + by1) / 2)
        b.device(ba, "gfci", pc(6.0), by1)
        # bedroom
        if kind == "K":
            yc = 15.5
            b.obj(rm, "bed_king", against=Wb, along=yc)
            b.obj(rm, "nightstand", against=Wb, along=yc - 3.165 - 0.9); b.obj(rm, "nightstand", against=Wb, along=yc + 3.165 + 0.9)
            b.obj(rm, "dresser", against=We, along=15.6); b.obj(rm, "tv_wall", against=We, along=15.6)
            b.obj(rm, "desk", against=We, along=20.6, w=3.5)
            b.obj(rm, "chair", x=F(8.4) - (1.7 if not mirror else 0), y=19.8)
        else:
            y1c, y2c = ry0 + 2.5 + 2.5, ry0 + 2.5 + 5 + 2.5 + 2.5
            b.obj(rm, "bed_queen", against=Wb, along=y1c); b.obj(rm, "bed_queen", against=Wb, along=y2c)
            b.obj(rm, "nightstand", against=Wb, along=(y1c + y2c) / 2)
            b.obj(rm, "dresser", against=We, along=15.6); b.obj(rm, "tv_wall", against=We, along=15.6)
            b.obj(rm, "desk", against=We, along=20.6, w=3.5)
        b.obj(rm, "ptac", against="S", along=F(2.75))
        b.device(rm, "light", (rx0 + rx1) / 2, 17); b.device(rm, "smoke_alarm", (rx0 + rx1) / 2, 14)
        b.device(rm, "receptacle", rx0, 22.5); b.device(rm, "receptacle", rx1, 23.0)
        b.device(rm, "switch", F(7.6), ry1)
        return rm
    # standard: bath beside the entry, tub across the front wall, WC + lav on the bath's back wall
    bw = 5.67 if edge else 5.5
    xb = x1 - bw if mirror else x0 + bw
    xo = x1 if mirror else x0
    b.wall(L, (xb, 20.0), (xb, D), t=INT, kind="interior", wet=True)
    b.wall(L, (xo, 20.0), (xb, 20.0), t=INT, kind="interior", wet=True)
    rm = b.space(L, ((x0 + x1) / 2, 10), f"Room {num}", "guest_room")
    ba = b.space(L, ((xb + xo) / 2, 24), f"Bath {num}", "bath")
    b.trace()
    rx0, ry0, rx1, ry1 = b.spoly(rm).bounds; bx0, by0, bx1, by1 = b.spoly(ba).bounds
    sg = -1 if mirror else 1
    dc = xb + sg * 3.25
    b.door(south, center=(dc, D), width=3.0, hinge="end" if mirror else "start", into=(dc, D - 2), exterior=(L == "L1"))
    bwall = b.wall_at(L, (xb, 24))
    b.door(bwall, center=(xb, 23.5), width=2.84, hinge="start", into=(xb + sg * 2, 23.5))
    F = (lambda u: rx1 - u) if mirror else (lambda u: rx0 + u)       # mirror: bed wall is the bath side
    Wb, We = ("E", "W") if mirror else ("W", "E")
    b.window(b.wall_at(L, (x0 + 1, 0)), center=(F(8.0), 0), width=5.0, height=4.5, sill=2.5)
    b.obj(ba, "tub", against="S", along=(bx0 + bx1) / 2)
    tx = (lambda u: bx1 - u) if mirror else (lambda u: bx0 + u)      # toilet on the demising side, lav by the door
    b.obj(ba, "toilet", against="N", along=tx(1.25))
    b.obj(ba, "lavatory", against="N", along=tx(bx1 - bx0 - 1.0))
    b.device(ba, "light", (bx0 + bx1) / 2, 23.0); b.device(ba, "exhaust_fan", (bx0 + bx1) / 2, 22.0)
    b.device(ba, "gfci", tx(bx1 - bx0 - 1.0), by0)
    # bed wall is opposite the vestibule: bath on the west -> beds against the west wall too (over the bath line)
    if kind == "K":
        yc = 8.0
        b.obj(rm, "bed_king", against=Wb, along=yc)
        b.obj(rm, "nightstand", against=Wb, along=yc - 3.165 - 0.9); b.obj(rm, "nightstand", against=Wb, along=yc + 3.165 + 0.9)
        b.obj(rm, "dresser", against=We, along=8.0); b.obj(rm, "tv_wall", against=We, along=8.0)
        b.obj(rm, "desk", against=We, along=13.2, w=3.5)
        b.obj(rm, "chair", x=F(8.6) - (1.7 if not mirror else 0), y=12.4)
    else:
        y1c, y2c = ry0 + 5.0, ry0 + 12.5
        b.obj(rm, "bed_queen", against=Wb, along=y1c); b.obj(rm, "bed_queen", against=Wb, along=y2c)
        b.obj(rm, "nightstand", against=Wb, along=(y1c + y2c) / 2); b.obj(rm, "nightstand", against=Wb, along=ry0 + 1.5)
        b.obj(rm, "dresser", against=We, along=8.5); b.obj(rm, "tv_wall", against=We, along=8.5)
        b.obj(rm, "desk", against=We, along=13.5, w=3.5)
    b.obj(rm, "ptac", against="N", along=F(9.5))
    b.obj(rm, "wardrobe", against=We, along=17.9)
    b.device(rm, "light", (rx0 + rx1) / 2, 10); b.device(rm, "smoke_alarm", (rx0 + rx1) / 2, 13)
    b.device(rm, "receptacle", rx0, 12.5); b.device(rm, "receptacle", rx1, 12.0)
    b.device(rm, "switch", xb + sg * 1.0, ry1)
    return rm


# ---------------- shell, towers, core walls (every level) ----------------
for L in LV:
    g = L == "L1"
    for tx0 in (EX0, WX1):   # stair towers
        b.rect_walls(L, tx0, 0, tx0 + 10, WK, t=EXT, kind="exterior")
    b.wall(L, (WX0, 0), (WX1, 0), t=EXT, kind="exterior")
    b.wall(L, (WX0, D), (WX1, D), t=EXT, kind="exterior")
    for nm, xc in (("Stair W", 5), ("Stair E", 235)):
        st = b.space(L, (xc, 20), nm, "stair")
        b.device(st, "light", xc, 22)
    # stair door: from the walkway (upper) / to the sidewalk (ground), near the front
    b.door(b.wall_at(L, (WX0, 31)), center=(WX0, 31.5), width=3.0, hinge="end", into=(WX0 + (2 if g else -2), 31), exterior=g)
    b.door(b.wall_at(L, (WX1, 31)), center=(WX1, 31.5), width=3.0, hinge="start", into=(WX1 + (-2 if g else 2), 31), exterior=g)
    # elevator shaft x 110-120, y 0-10 at the back of the core (stacks), opening south on every level
    b.wall(L, (110, 0), (110, 20 if g else D), t=INT, kind="demising"); b.wall(L, (130, 0), (130, D), t=INT, kind="demising")
    b.wall(L, (120, 0), (120, 10), t=INT, kind="shaft"); b.wall(L, (110, 10), (120, 10), t=INT, kind="shaft")
    b.wall(L, (120, 10), (130, 10), t=INT, kind="interior")
    el = b.space(L, (115, 5), "Elevator", "elevator")
    b.door(b.wall_at(L, (115, 10)), center=(115, 10), width=3.5, kind="slide")
    if not g:
        b.open_space(L, (WX0 + EXT / 2, D + EXT / 2, WX1 - EXT / 2, WK), "Walkway", "balcony")
        b.guard(L, (WX0 + EXT / 2, WK), (WX1 - EXT / 2, WK))

SW = (10 - 0.335 - 0.335 - 0.33) / 2         # 4.5': two flights + 4" gap span each tower wall-to-wall
RUN = 8 * 11 / 12; LAND = max(SW, 4.0)
for i in range(3):
    for tx0, tag in ((EX0, "W"), (WX1, "E")):
        b.stair_u(f"ST-{tag}{i + 1}", LV[i], LV[i + 1], tx0 + 0.335, 0.335 + RUN + LAND, width=SW, up="N")
b.elevator("E1", LV, (110.25, 0.335, 119.75, 9.75))

# ---------------- ground floor ----------------
L = "L1"
for i in range(16):
    x0 = mod_x(i)
    if i < 6 or i >= 10:
        b.wall(L, (x0 + MOD, 0), (x0 + MOD, D), t=INT, kind="demising") if x0 + MOD not in (85.0, WX1) else None
for x in (85.0, 155.0):
    b.wall(L, (x, 0), (x, D), t=INT, kind="demising")
# restrooms x 102-110
b.wall(L, (102, 0), (102, 20), t=INT, kind="interior", wet=True)
b.wall(L, (102, 10), (110, 10), t=INT, kind="interior", wet=True); b.wall(L, (102, 20), (110, 20), t=INT, kind="interior")
# back of house x 130-155
b.wall(L, (130, 14), (155, 14), t=INT, kind="interior", wet=True); b.wall(L, (142.5, 14), (142.5, D), t=INT, kind="interior")
lobby = b.space(L, (95, 25), "Lobby & Breakfast", "lobby", ceiling=9.0)
rr1 = b.space(L, (106, 5), "Restroom 1", "restroom", accessible=True)
rr2 = b.space(L, (106, 15), "Restroom 2", "restroom", accessible=True)
office = b.space(L, (125, 5), "Office / IDF", "office")
laun = b.space(L, (142, 7), "Laundry", "laundry")
hsk = b.space(L, (136, 21), "Housekeeping", "storage")
mech = b.space(L, (149, 21), "Mechanical", "mechanical")
FW = b.wall_at(L, (100, D))
b.door(FW, center=(113.0, D), width=6.0, kind="double", into=(113.0, D + 2), exterior=True)
for xc in (90.0, 97.0, 104.0, 121.5): b.window(FW, center=(xc, D), width=5.0, sill=1.5, height=6.5)
b.window(b.wall_at(L, (90, 0)), center=(91, 0), width=8.0, sill=3.0)
w102 = b.wall_at(L, (102, 5))
b.door(w102, center=(102, 6.5), width=3.0, hinge="end", into=(104, 6.5))
b.door(w102, center=(102, 16.5), width=3.0, hinge="end", into=(104, 16.5))
b.door(b.wall_at(L, (125, 10)), center=(123.5, 10), width=3.0, hinge="start", into=(123.5, 8))
b.door(b.wall_at(L, (136, 14)), center=(136, 14), width=3.0, hinge="start", into=(136, 12))
b.door(b.wall_at(L, (136, D)), center=(136.5, D), width=3.0, hinge="start", into=(136.5, D + 2), exterior=True)
b.door(b.wall_at(L, (150, D)), center=(149.5, D), width=3.0, hinge="end", into=(149.5, D + 2), exterior=True)
GROUND = {0: "K", 1: "QQ", 2: "QQ", 3: "K", 4: "AQ", 5: "AK", 10: "AK", 11: "AQ", 12: "K", 13: "QQ", 14: "QQ", 15: "K"}
b.trace()
n = 101
for i in sorted(GROUND):
    k = GROUND[i]
    room(L, mod_x(i), str(n), {"AQ": "QQ", "AK": "K"}.get(k, k), mirror=(i % 2 == 1),
         acc=k[0] == "A", back=i in BACK_BATH, rollin=(i in (5, 10)))
    n += 1
b.trace()
# lobby / breakfast furniture
b.obj(lobby, "counter", against="N", along=93.0, label="breakfast buffet")
for tx in (87.75, 94.25):
    for ty in (6.0, 12.5, 19.0):
        b.obj(lobby, "table_4", x=tx, y=ty)
b.obj(lobby, "reception_desk", x=121.0, y=14.5, facing="S", w=8.0)
b.obj(lobby, "sofa", against="S", along=106.0)
b.obj(lobby, "planter", x=127.5, y=25.5)
for x, y in ((89, 4), (96, 4), (89, 11), (96, 11), (89, 18), (96, 18), (92, 25), (106, 24), (115, 14), (115, 22), (125, 20)):
    b.device(lobby, "light", x, y)
b.device(lobby, "smoke_alarm", 105, 25); b.device(lobby, "receptacle", 85.25, 25)
b.device(lobby, "receptacle", 129.75, 12.5)
for r, y0 in ((rr1, 0.335), (rr2, 10.25)):
    b.obj(r, "toilet_ada", against="N", along=109.75 - 1.42)
    b.obj(r, "lavatory_ada", against="E", along=y0 + 7.0)
    b.device(r, "light", 106, y0 + 4.5); b.device(r, "exhaust_fan", 107, y0 + 3)
b.obj(office, "desk", against="N", along=127.0, w=4.5)
b.obj(office, "chair", x=125.6, y=3.0)
b.obj(office, "shelving", against="W", along=4.0, w=5.0)
b.device(office, "light", 125, 5); b.device(office, "receptacle", 129.75, 5)
for k in range(4):
    b.obj(laun, "washer", against="S", along=141.2 + k * 2.4)     # on the plumbing wall
    b.obj(laun, "dryer", against="N", along=131.5 + k * 2.4)      # vented through the back wall
b.obj(laun, "counter", against="N", along=147.0, w=8.0, label="folding counter")
b.device(laun, "light", 136, 7); b.device(laun, "light", 148, 7)
b.obj(hsk, "shelving", against="W", along=20.5, w=6.0); b.device(hsk, "light", 136, 21)
b.obj(mech, "equipment", against="N", along=146.0, label="water heater"); b.obj(mech, "equipment", against="N", along=151.0, label="water heater")
b.device(mech, "light", 148.5, 22)

# ---------------- upper floors ----------------
for f, L in enumerate(LV[1:], start=2):
    for i in range(16):
        x0 = mod_x(i)
        if x0 + MOD not in (110.0, WX1): b.wall(L, (x0 + MOD, 0), (x0 + MOD, D), t=INT, kind="demising")
    lin = b.space(L, (125, 5), "Linen / IDF", "storage")
    vend = b.space(L, (120, 19), "Elevator Lobby / Vend", "lobby")
    b.door(b.wall_at(L, (120, D)), center=(120, D), width=6.0, kind="cased")
    b.door(b.wall_at(L, (125, 10)), center=(123.5, 10), width=3.0, hinge="start", into=(123.5, 8))
    b.trace()
    for i, k in enumerate(UPPER):
        room(L, mod_x(i), f"{f}{i + 1:02d}", k, mirror=(i % 2 == 1), back=i in BACK_BATH)
    b.trace()
    b.obj(vend, "vending", against="E", along=16.0); b.obj(vend, "vending", against="E", along=19.5)
    b.obj(vend, "equipment", against="W", along=17.5, label="ice machine")
    b.obj(lin, "shelving", against="E", along=5.0, w=6.0)
    for sp_, x, y in ((lin, 125, 5), (vend, 120, 15), (vend, 120, 23)): b.device(sp_, "light", x, y)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "motel.json"
    b.save(out); print("saved", out)
