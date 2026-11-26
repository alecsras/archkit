# archkit

Verified building models for floor plans, 3D walkthroughs and game levels. One JSON model is the single source of truth; rooms are traced from walls, every height is derived, and a validator (geometry, placement, circulation, ADA, IBC egress, MEP) must report 0 errors before anything is rendered.

```bash
pip install shapely --break-system-packages
python examples/inn.py inn.json
python -m archkit.validate inn.json --json report.json   # exit 1 on any error
python -m archkit.render inn.json out/ --report report.json
python examples/defects.py                               # 13 injected defects, all must be caught
```

Schematic accuracy only. Not construction documents.
