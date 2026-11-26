"""Inject known defects into the passing sample; every one must be caught. Run: python examples/defects.py"""
import sys, copy, importlib.util; sys.path.insert(0, __file__.rsplit("/examples", 1)[0])
from archkit.validate import validate
spec = importlib.util.spec_from_file_location("inn", __file__.rsplit("/", 1)[0] + "/inn.py"); inn = importlib.util.module_from_spec(spec); spec.loader.exec_module(inn)
base = inn.b; base.trace()
sp = lambda b, name, lvl="L1": next(s["id"] for s in b.d["spaces"] if s["name"] == name and s["level"] == lvl)

def gap(b):            # shorten a demising wall: a gap
    w = next(w for w in b.d["walls"] if w["level"] == "L2" and w["a"] == [36.0, 0.0] and w["b"] == [36.0, 20.0]); w["b"] = [36.0, 17.0]
def entrance(b):       # planter dropped just inside the front doors
    b.obj(sp(b, "Lobby"), "planter", x=11.0, y=42.6)
def floating_light(b): # wall sconce 2 ft off the wall
    b.device(sp(b, "Lobby"), "wall_sconce", 3.0, 36.0)
def light_outside(b):  # ceiling light outside its room
    b.device(sp(b, "Office"), "light", 20.0, 36.0)
def blocked_door(b):   # dresser parked in front of a guest-room door
    b.obj(sp(b, "Room 202", "L2"), "dresser", x=42.5, y=17.0, facing="N", w=4.0)
def corridor(b):       # vending machine pinching the corridor
    b.obj(sp(b, "Corridor"), "vending", x=30.0, y=20.25, facing="S")
def through_wall(b):   # desk pushed into a wall
    b.obj(sp(b, "Office"), "desk", x=30.5, y=30.0, facing="W")
def overlap(b):        # second bed on top of the first
    b.obj(sp(b, "Room 102"), "bed_queen", x=37.0, y=3.5, facing="E")
def bad_stair(b):      # floor-to-floor changed after the stair was drawn
    for L in b.d["levels"]:
        if L["id"] == "L2": L["elev"] = 11.5
def nowhere(b):        # second-floor door in an exterior wall
    w = next(w for w in b.d["walls"] if w["level"] == "L2" and w["kind"] == "exterior" and w["a"] == [0.0, 0.0]); b.door(w["id"], center=(30, 0), width=3.0, hinge="start", into=(30, 2))
def narrow_door(b):    # 24" door on a public room
    w = b.wall_at("L1", (5, 26)); b.door(w, center=(20, 26), width=2.0, hinge="start", into=(20, 28))
def stair_open(b):     # stair pulled off its walls
    st = b.d["stairs"][0]
    for f in st["flights"]: f["start"][0] += 0.6; f["end"][0] += 0.6
    st["footprint"] = [[p[0] + 0.6, p[1]] for p in st["footprint"]]
def missing_smoke(b):  # remove a room's smoke alarm
    b.d["devices"] = [d for d in b.d["devices"] if not (d["type"] == "smoke_alarm" and d["space"] == sp(b, "Room 203", "L2"))]
def switch_in_door(b): # light switch mounted inside a doorway
    b.device(sp(b, "Office"), "switch", 28.0, 26.25)
def no_guard(b):       # second-floor balcony with an open edge
    b.open_space("L2", (20, 46.335, 36, 52), "Balcony", "balcony")

CASES = [("wall gap", gap, {"G-WALL-JOIN", "G-ROOM-ENCLOSED"}), ("entrance obstruction", entrance, {"C-DOOR-CLEAR", "C-ROUTE"}),
         ("floating wall light", floating_light, {"P-DEV-ONWALL"}), ("ceiling light outside room", light_outside, {"P-DEV-INSIDE"}),
         ("furniture blocking door", blocked_door, {"C-DOOR-CLEAR", "C-DOOR-SWING", "C-ROUTE"}), ("corridor pinch", corridor, {"C-CORRIDOR", "C-ROUTE-SPLIT", "C-ROUTE"}),
         ("object through wall", through_wall, {"P-OBJ-INSIDE"}), ("overlapping furniture", overlap, {"P-OBJ-COLLIDE"}),
         ("stair rise mismatch", bad_stair, {"C-STAIR-RISE"}), ("door to a drop", nowhere, {"C-DOOR-NOWHERE"}),
         ("narrow door", narrow_door, {"C-DOOR-WIDTH"}), ("open stair edge", stair_open, {"C-STAIR-GUARD"}), ("missing smoke alarm", missing_smoke, {"M-DEVICES"}),
         ("switch inside a doorway", switch_in_door, {"P-DEV-OPENING"}), ("balcony without a guard", no_guard, {"K-GUARD"})]
ok_all = True
for name, fn, want in CASES:
    b = copy.deepcopy(base); fn(b); R = validate(b)
    got = {i["code"] for i in R.errors}; hit = want & got
    ok_all &= bool(hit)
    print(f"{'CAUGHT ' if hit else 'MISSED!'}  {name:28s} -> {', '.join(sorted(hit)) or 'none'}   ({len(R.errors)} errors)")
print("ALL DEFECTS CAUGHT" if ok_all else "SOME DEFECTS MISSED")
sys.exit(0 if ok_all else 1)
