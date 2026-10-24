# Emotional Damage — Frontend Design Implementation

**Design reference (source of truth):** https://claude.ai/artifact/BwN4694vjhbntc9ogPLpdk

Open the link and press **Play** on any artboard to click through the flow. Whenever this guide and the design disagree, the design wins.

**Scope:** frontend only. Covers UI, layout, styling, routing, local state and mock data. Leaves out ElevenLabs, Presage, multiplayer sync and any server code: every screen renders from mock data behind props, so the real data can be wired in later without touching the components.

---

## 0. Screen map

| # | Artboard | Route | Purpose |
|---|---|---|---|
| 1 | Home | `/` | Create game or Join game |
| 2a | Join game | `/join` | Enter the 4-letter code and a gamer tag |
| 2b | Lobby (host) | `/lobby/:code` | Show the code, 5 player slots and settings, then Start |
| 3 | The round | `/play/:code` | Voice prompt, countdown, webcam, live metrics and Deep scan |
| 4 | Round leaderboard | `/play/:code/results` | Ranked rows and Presage receipts |
| 5 | Winner | `/play/:code/winner` | Champion, stats, Run it back / Touch grass |

Flow: Home → (Create → Lobby) or (Join → Lobby) → Round → Leaderboard → (next Round … ) → Winner → Lobby or Home.

---

## Step 1 — Scaffold the project

```bash
npm create vite@latest emotional-damage -- --template react-ts
cd emotional-damage
npm i react-router-dom
npm run dev
```

Suggested structure:

```
src/
  styles/
    tokens.css        # colours, radii, shadows, fonts
    global.css        # resets, overflow guards, dot backgrounds, .btn hover
  components/
    PageShell.tsx     # dotted background + max-width container
    Header.tsx        # back pill + wordmark
    ChunkyCard.tsx    # border + radius + hard shadow + optional tilt
    ChunkyButton.tsx  # the <a>/<button> styled button
    Sticker.tsx       # small rotated pill label
    Avatar.tsx        # coloured circle with initial
    Pill.tsx          # rounded tag (READY, HOST, via Presage…)
    MetricTile.tsx    # small number tile (Pulse, Breathing…)
    MeterBar.tsx      # horizontal % bar (Damage match, classifier)
    Waveform.tsx      # SVG line from a points array
    Countdown.tsx     # yellow circle timer
    Ticker.tsx        # black slogan strip
    Mascot.tsx        # crying blob SVG
    UncleDamage.tsx   # announcer face SVG
  screens/
    Home.tsx  Join.tsx  Lobby.tsx  Round.tsx  Leaderboard.tsx  Winner.tsx
  mock/
    data.ts           # players, round metrics, results, winner
  App.tsx             # routes
```

---

## Step 2 — Design tokens

Create `src/styles/tokens.css`. These values are lifted straight from the design.

```css
:root {
  /* colours */
  --ink: #111111;          /* all text, borders, shadows */
  --yellow: #FFE135;       /* Home, Leaderboard bg; primary buttons */
  --pink: #FF4FA3;         /* Lobby bg; Create card; highlights */
  --cyan: #3EC6FF;         /* Join, Winner bg; Join card */
  --lime: #9BF04B;         /* Round bg; Start / Next buttons */
  --white: #FFFFFF;
  --grey: #E8E8E8;         /* last place / "down bad" */

  /* tints used inside cards */
  --tint-pink: #FFE3F0;
  --tint-cyan: #DDF4FF;
  --tint-yellow: #FFF8D6;
  --tint-lime: #EEFCE0;
  --webcam: #1D1D24;

  /* shape */
  --border: 4px solid var(--ink);
  --border-thin: 3px solid var(--ink);
  --r-sm: 12px;  --r-md: 18px;  --r-lg: 24px;  --r-xl: 28px;  --r-pill: 999px;
  --shadow-sm: 4px 4px 0 var(--ink);
  --shadow-md: 6px 6px 0 var(--ink);
  --shadow-lg: 10px 10px 0 var(--ink);

  /* type */
  --font-display: 'Bagel Fat One', cursive;
  --font-body: 'Fredoka', sans-serif;
}
```

**Rules of the look:**
- Text is always `--ink`, including on pink, cyan, lime and yellow. Never use white text on a colour, because it fails contrast. The one exception is the black strips (ticker, aura box, AI vibe check), which use yellow, lime or white text.
- Every card has a thick black border and a **hard** offset shadow with no blur. There are no soft shadows and no gradients.
- Slight rotations (−4° to +8°) on stickers, big cards and badges give the goofy feel. Keep body text unrotated or nearly so (≤ 1°).

---

## Step 3 — Fonts

Add to `index.html` `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Bagel+Fat+One&family=Fredoka:wght@400;500;600;700&display=swap">
```

- **Bagel Fat One** (weight 400): titles, big numbers, button labels, rank numbers, avatar initials.
- **Fredoka** 500–700: everything else. Labels are 600–700, body copy 500.

Outlined hero title (Home, Leaderboard, Winner):

```css
.title-outline {
  font-family: var(--font-display);
  color: var(--white);
  -webkit-text-stroke: 4px var(--ink);
  text-shadow: 8px 8px 0 var(--ink);
  line-height: 0.9;
  font-size: clamp(56px, 9vw, 124px);
}
```

---

## Step 4 — Global CSS and **no side scroll**

`src/styles/global.css`:

```css
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; overflow-x: hidden; max-width: 100%; }
body { font-family: var(--font-body); color: var(--ink); }
a { color: var(--ink); }

/* polka-dot page backgrounds — one colour per screen */
.dots { background-image: radial-gradient(var(--ink) 1.4px, transparent 1.6px); background-size: 26px 26px; overflow-x: clip; }
.dots--yellow { background-color: var(--yellow); }
.dots--pink   { background-color: var(--pink); }
.dots--cyan   { background-color: var(--cyan); }
.dots--lime   { background-color: var(--lime); }

/* button wiggle */
.btn { transition: transform .12s; }
.btn:hover { transform: translate(-3px, -3px) rotate(-1deg); }
.btn:focus-visible { outline: 4px solid var(--ink); outline-offset: 4px; }

@media (prefers-reduced-motion: reduce) { .btn { transition: none; } }
```

**Anti-side-scroll checklist.** Apply these everywhere; the design already follows them.
1. `overflow-x: hidden` on `html, body` and `overflow-x: clip` on each page's root.
2. Every flex row that holds cards uses `flex-wrap: wrap`, and children use `flex: 1 1 <basis>` plus `min-width: 0`.
3. No fixed pixel widths on columns. Use `min-width` with `flex: 0 0 auto` (see the leaderboard numbers).
4. Big type uses `clamp()`: the hero title, the lobby code (`clamp(56px, 8vw, 96px)`) and the prompt text.
5. SVGs get `max-width: 100%; height: auto`, or `width="100%"` with `preserveAspectRatio="none"` for waveforms.
6. Decorative confetti on the Winner screen is absolutely positioned inside a root with `overflow: hidden`.

---

## Step 5 — Shared components

Build these first. Each one maps to a repeated pattern in the design.

**`PageShell`**: `<div className={`dots dots--${bg}`}>`, with `min-height: 100vh`, padding `32px 24px 48px`, and an inner container of `max-width: 1180px` (Round uses 1240, Leaderboard 1000, Join 1100), `margin: 0 auto`, a vertical flex column and a gap of 28–36px.

**`Header`**: the left side holds a white pill link with `--border-thin`, `--shadow-sm` and padding `10px 18px`. Its label is "← back to safety" (Join), "← rage quit" (Lobby) and so on. The right side holds the wordmark "EMOTIONAL DAMAGE" at 30px display, with a white fill, a 2px stroke and a 4px shadow. The row uses `flex-wrap: wrap` and `justify-content: space-between`.

**`ChunkyCard`**: props `bg`, `tilt`, `shadow` (`sm|md|lg`) and `radius`. It renders `border: var(--border)`, the shadow and `transform: rotate(tilt)`.

**`ChunkyButton`**: renders as `<a>` when it navigates, otherwise `<button>`. Spec: display font at 26–30px, `--border`, radius 18–20px, padding `14px 28px`, `--shadow-md` or a 7px shadow, and the `btn` class. Colour variants are yellow (default), lime (go/start) and white (secondary).

**`Sticker`**: a small rotated label with a coloured background, `--border-thin`, radius 12px, a 6×16 padding, 700 weight and `rotate(-4deg … 3deg)`.

**`Avatar`**: props `initial`, `color` and `size` (44, 50, 58 or 170). It's a circle with a 3–4px ink border and the initial in the display font.

**`Pill`**: radius 999px, a 2–3px border, padding `4px 12px` and 700 weight at 13–15px.

**`MetricTile`**: label (600, 14px), value (display, 34px) with a unit (Fredoka 700, 15px), and a caption (600, 13px). It has a tinted background, `--border-thin` and radius 16px.

**`MeterBar`**: a track 18–26px tall with `--border-thin`, a pill radius, a white background and `overflow: hidden`, filled to `value%` with a colour. Give it `role="meter"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-label`.

**`Waveform`**: props `points: number[]`, `height=60`, `dashed?`. It renders `<svg viewBox="0 0 260 60" width="100%" preserveAspectRatio="none">` containing a path with stroke `--ink` and width 3.5. Give it `role="img"` and an `aria-label` describing the trend.

**`Countdown`**: a 130px circle with a yellow background, a 5px border, `--shadow-md` and `rotate(-6deg)`. It shows the number (display, 76px) with "FACE NOW" underneath, and has `role="timer"` with an `aria-label`.

**`Ticker`**: a black strip with yellow text, 700 weight, 18px, `letter-spacing: 1px`, `white-space: nowrap`, `overflow: hidden` and `rotate(-1deg)`. An optional CSS marquee animation can be added if it is disabled under reduced motion.

**`Mascot` / `UncleDamage`**: copy the inline SVGs from the design's Home and Round artboards. Mark them `aria-hidden="true"`. Use SVG, never emoji.

---

## Step 6 — Mock data

`src/mock/data.ts` holds everything the screens render. Keep the shapes stable so that real data can replace them later.

```ts
export type Player = { id: string; name: string; initial: string; color: string;
  status?: string; tag?: 'HOST' | 'READY' | 'NOT READY'; };

export const lobby = { code: 'BRUH', maxPlayers: 5, rounds: 5, countdown: 3,
  vibe: 'Unhinged', players: [/* 3 players, see Lobby artboard */] as Player[] };

export const roundState = {
  round: 2, totalRounds: 5,
  prompt: 'Make the face of someone who just stepped on a LEGO… barefoot… at 3am.',
  secondsLeft: 2,
  live: { pulse: 112, breathing: 24, blinks: 7, talking: true, damageMatch: 87, aura: 420 },
  deepScan: {
    signalConfidence: 94, stability: 'stable',
    pulseWave: [/* numbers */], hrv: 29, hrvVsBaseline: -41,
    breathingUpper: [/* … */], breathingLower: [/* … */],
    bpWave: [/* … */], bpTrend: 'up',
    expressions: [{ label: 'Pain', pct: 71 }, { label: 'Shock', pct: 18 },
                  { label: 'Cringe', pct: 8 }, { label: 'Neutral', pct: 3 }],
    gaze: 'off-camera right', lookAways: 2, squints: 1, eyePenalty: -20,
    face: { mouthStretch: 92, browCrunch: 78, heldSeconds: 2.4, screamed: true,
            lighting: 'ok', inFrame: 82 },
    vibeCheck: 'Pulse jumped 34 bpm in under a second…',
  },
};

export const results = { rows: [/* rank, player, tag, delta, total, bg, tilt */],
  receipts: [/* label, who, value, sub, bg, tilt */] };

export const winner = { player: /* sigma_sam */, totalAura: 3420, peakPulse: 131,
  bestRound: 'LEGO', others: [/* #2–#5 */] };
```

Copy every string and number from the artboards so the build matches the design exactly.

---

## Step 7 — Routing

`App.tsx`:

```tsx
<Routes>
  <Route path="/" element={<Home />} />
  <Route path="/join" element={<Join />} />
  <Route path="/lobby/:code" element={<Lobby />} />
  <Route path="/play/:code" element={<Round />} />
  <Route path="/play/:code/results" element={<Leaderboard />} />
  <Route path="/play/:code/winner" element={<Winner />} />
</Routes>
```

Each button in the design that links to another artboard becomes a `<Link>` to the matching route. The "(prototype) skip to results" and "(prototype) final" links are for demoing only; put them behind a `?demo=1` flag.

---

## Step 8 — Build each screen

### 8.1 Home (`/`, yellow dots)
1. **Header row:** the version pill on the left ("v0.0.1 (unstable, like us)", black with yellow text) and a "How to play" pill on the right that anchors to `#how`.
2. **Hero:** a flex-wrap row, centred.
   - Left (`flex: 1 1 600px`): a pink Sticker "certified brain rot ™", the outlined title "EMOTIONAL / DAMAGE", and a 22px tagline with `max-width: 560px`.
   - Right: the Mascot SVG at 200px, `rotate(8deg)`.
3. **Two action cards** in a flex-wrap row with gap 28 and each card `flex: 1 1 420px`:
   - **Create game:** pink, `rotate(-1deg)`, a white "HOST MODE" pill, a 52px display title, the body copy, and a yellow button "Make a lobby →" that goes to `/lobby/BRUH` (mock).
   - **Join game:** cyan, `rotate(1deg)`, a "GOT A CODE?" pill, and "Enter code →" that goes to `/join`.
4. **How it works** (`id="how"`): a white card with three steps, each a 48px numbered circle (pink, cyan, lime) beside a line of copy.
5. **Ticker** strip at the bottom.

### 8.2 Join (`/join`, cyan dots)
1. Header with "← back to safety" linking to `/`.
2. A centred white card (`max-width: 760px`, `--shadow-lg` at 12px, radius 32): a pink sticker, the title "Join a lobby" and the helper copy.
3. **Code input:** a `<fieldset>` with `<legend>Lobby code</legend>` and four `<input maxlength="1">` boxes, each 92×112 with display font at 60px and uppercase text. Filled boxes are lime with a solid border; the empty box is white with a dashed border. Every box gets a visually hidden `<label>`. Behaviour: typing a letter moves focus to the next box, Backspace moves back, and pasting "BRUH" fills all four. A focused box turns yellow.
4. **Gamer tag:** a labelled text input, 22px, with `--border` and `--shadow-sm`.
5. "Let me in →" goes to `/lobby/:code`. It is disabled until all four letters are filled.
6. A black note about the webcam, then two rotated stickers below the card.

### 8.3 Lobby (`/lobby/:code`, pink dots)
Two columns in a flex-wrap row: left `flex: 1 1 340px`, right `flex: 2 1 520px`.
1. **Code card** (yellow, `rotate(-1.5deg)`): the label "your lobby code", the code in a white box at `clamp(56px, 8vw, 96px)`, a "Copy invite link" button (black with yellow text) that copies to the clipboard and briefly reads "copied!", and a roast line.
2. **House rules** card: segmented buttons for Rounds (3/5/10) and Countdown (3s/5s). The selected option is lime with `--shadow-sm` and carries `aria-pressed="true"`. Uncle Damage's vibe is shown as a pink pill.
3. **The victims** card: the title plus a "3 / 5" counter, then **always 5 slots**:
   - A filled slot is a tinted-yellow row: Avatar 58 + name (22px) + status (15px) + tag pill (HOST yellow / READY lime / NOT READY white).
   - An empty slot is a dashed row with a "?" avatar and "waiting for victim #N…".
4. Footer row: helper text and "Start the damage →" (lime) going to `/play/:code`. Only the host sees an enabled button; others see "waiting for host…".

### 8.4 Round (`/play/:code`, lime dots, container 1240px)
1. **Top bar:** the "ROUND 2 / 5" badge (white, display 26px), a black "lobby BRUH" pill, and 5 small Avatars (44px) on the right inside an `aria-label="Players in this round"` group.
2. **Announcer bar** (white card, flex-wrap):
   - The UncleDamage SVG at 96px.
   - Middle (`flex: 1 1 480px; min-width: 0`): the name, a yellow "ElevenLabs voice agent · speaking" pill, and an 8-bar waveform of black 6px bars with varying heights. Animate the bars' height when "speaking" and stop the animation under reduced motion. Below sits the prompt in display font at `clamp(26px, 3.4vw, 40px)`.
   - Right: `Countdown`, driven by a `setInterval` from `countdown` to 0. At 0 the screen switches to a "captured!" state; that state is a UI-only stub.
3. **Main row** (flex-wrap):
   - **Webcam panel** (`flex: 999 1 560px; min-width: 0; min-height: 460px`, dark background): a `<video autoPlay muted playsInline>` filling the panel with `object-fit: cover` and mirrored (`transform: scaleX(-1)`). Request the camera with `navigator.mediaDevices.getUserMedia({ video: true })`. If permission is denied, show the dark panel with a "camera said no" message. Overlays, all absolutely positioned: the pink "LIVE · you" pill top-left, "face locked ✓" top-right, the dashed lime face-guide SVG centred, and the yellow roast sticker bottom-left.
   - **Snitch-o-meter** aside (`flex: 1 1 300px`): the title plus a "via Presage" pill, a 2×2 `MetricTile` grid (Pulse pink tint, Breathing cyan tint, Blinks yellow tint, Talking lime tint), a "Damage match" `MeterBar` in pink, and a black "aura this round" box with a lime +420 in display 40px.
4. **Deep scan** section (white card, full width):
   - Header: "Deep scan (Presage is reading your soul)" plus a lime pill "signal confidence 94% · stable".
   - Six cards in a flex-wrap row (`flex: 1 1 300px; min-width: 0`):
     1. **Heart goes brr** (pink tint): `Waveform` for the pulse and "HRV 29 ms" with the change vs baseline.
     2. **Panic breathing** (cyan tint): two `Waveform`s overlaid, upper solid and lower dashed, with a legend.
     3. **Pressure check** (yellow tint): a relative BP `Waveform` and "trend ↑", captioned "relative, not a medical reading". Keep that caption.
     4. **Face classifier** (lime tint): four `MeterBar` rows for Pain, Shock, Cringe and Neutral, each with a 78px label column and a % column.
     5. **Eye snitch** (white): an eye SVG whose iris position reflects the gaze, the gaze text, look-aways, blinks and squints, and a yellow penalty pill.
     6. **Commitment** (white): a 2×2 grid of mouth stretch, brow crunch, held time and screamed, plus a quality footnote.
   - The **AI vibe check** strip: black with a yellow outline pill and white quote text.

### 8.5 Leaderboard (`/play/:code/results`, yellow dots, container 1000px)
1. Header: a black pill with the round and prompt name, then the outlined title "WHO GOT COOKED".
2. **Results card:** a column header row (RANK / PLAYER / THIS ROUND / TOTAL AURA), then 5 rows. Each row is `flex-wrap: wrap` with a rank in display 34px, an Avatar 50, the name, a roast tag pill, the delta, and the total in display 28px. Number columns use `flex: 0 0 auto; min-width: 84px`, never fixed widths. First place has a pink background and `rotate(-1deg)`; last place is grey with `rotate(1deg)`; the rest are tinted yellow.
3. **Presage receipts:** the title and a pill, then 5 award tiles (`flex: 1 1 210px`, each slightly rotated): Biggest pulse spike, Lowest HRV, Most panic breathing, Calmest (sus), and Eye contact crimes.
4. **Footer:** an Uncle Damage roast bubble (cyan), "(prototype) final →", and "Next round in 5…" (lime). The button counts down from 5 and then navigates back to the Round screen. On the last round it goes to `/winner` instead.

### 8.6 Winner (`/play/:code/winner`, cyan dots)
1. The root uses `position: relative; overflow: hidden` and holds an absolutely positioned confetti SVG (rectangles, circles and stars with ink outlines) with `pointer-events: none`.
2. A black "game over" pill.
3. **Champion stack:** the crown SVG (`rotate(-8deg)`, overlapping the avatar by −18px), then the 170px Avatar with a 6px border and `--shadow-lg`.
4. The name in the outlined title, then a pink "MOST EMOTIONALLY DAMAGED" badge rotated −2°.
5. **Three stat cards** (white, `flex: 1 1 200px; max-width: 240px`): Total aura, Peak pulse and Best round.
6. **Other placings** as pills; last place is grey and marked "(down bad)".
7. Buttons: "Run it back" (lime) goes to the lobby; "Touch grass" (white) goes to `/`.

---

## Step 9 — Responsive behaviour

The design is built at 1280px and must work down to roughly 360px.
- All rows already wrap, so at narrow widths the columns stack. Check the order: on the Round screen the webcam comes first, then the metrics, then Deep scan.
- Below 600px:
  - Shrink the Join code boxes to 64×80 with a 44px font.
  - Reduce the hero mascot to 140px.
  - Cap card rotations at ±1°, because large tilts collide when stacked.
- Keep touch targets at least 44px tall. The segmented buttons and pills already are.
- Test at 360, 768, 1024 and 1280 with DevTools. A horizontal scrollbar at any width is a bug.

---

## Step 10 — Accessibility checklist

- Use real `<button>`, `<a>`, `<input>` and `<label>` elements. Never put an `onClick` on a `<div>`.
- Icon-only controls need an `aria-label`. Decorative SVGs (mascot, confetti, crown, waveform bars) need `aria-hidden="true"`. Data SVGs need `role="img"` with an `aria-label`.
- The countdown is a `role="timer"` element. Announce "FACE NOW" via an `aria-live="assertive"` region at 0.
- Segmented controls use `aria-pressed`. Meters use `role="meter"`.
- Respect `prefers-reduced-motion` for the button wiggle, the speaking bars, the ticker and any confetti animation.
- Contrast: ink on every brand colour passes. Don't introduce grey text below `#555` on tinted backgrounds.

---

## Step 11 — Visual QA against the design

Open the design link next to the running app and check each screen for:
- [ ] The background colour and dot pattern
- [ ] Border thickness (3 or 4px) and shadow offsets (4, 6, 8 or 10px)
- [ ] Rotations on stickers and cards
- [ ] The font on each element (display vs body) and its sizes
- [ ] Copy, which should match the artboard word for word
- [ ] No horizontal scroll at 360 / 768 / 1280
- [ ] Every button routes to the same screen as in the prototype

**Design reference:** https://claude.ai/artifact/BwN4694vjhbntc9ogPLpdk
