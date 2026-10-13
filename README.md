# Low-Poly Character System

A customizable low-poly character system for web 3D games, with body and face sliders, hundreds of mix-and-match recolorable clothes and accessories, and up to 100 unique animated characters on screen on budget laptops and tablets.

Built for a sandbox MMO life-sim on Babylon.js 8, Havok, Vite and TypeScript. The dev server runs at `/low-poly-character-system/`. The research and the plan are in [`PLAN.md`](PLAN.md); the decisions are in [`SPEC.md`](SPEC.md).

## Run

`vite@low-poly-character-system.service` already runs `npm run dev` at boot. To restart manually:

```bash
sudo systemctl restart vite@low-poly-character-system.service
journalctl -u vite@low-poly-character-system.service -f
```
