# 🎮 LLM Survivor: Poké-Frontend Architecture Reference

**Version:** 1.0 (The Spectator Broadcast)
**Stack:** Next.js 14+ (App Router), React, TypeScript, Tailwind CSS
**Aesthetic Mandate:** 8-bit Game Boy Color (Gen 2 Pokémon - Gold/Silver/Crystal)
**Description:** A purely stateless, polling-driven frontend application designed to render the real-time social deception of 16 autonomous LLMs as a nostalgic, live-broadcast E-Sports/Visual Novel experience.

---

## 1. High-Level System Overview

The frontend acts as a **"Dumb Client" Spectator Terminal**. It has absolutely zero write-access to the game state and sends no API calls to the LLMs. It functions purely as a renderer, subscribing to the Python backend's state machine via HTTP polling.

### 1.1 The Layout Architecture (Split-Screen)

To optimize for desktop spectator viewing, the viewport is rigidly divided into two panes:

```text
+-------------------------------------------------------------+
| [ 65% WIDTH: THE GBC EMULATOR ] | [ 35% WIDTH: GOD FEED ] |
|                                 |                         |
| +----------------------------+ | [🧠] Inner Thought       |
| | DAY 4 | SCRAMBLE | 12/16 | | | "I will betray Alpha"   |
| +----------------------------+ | [💬] Public Action       |
| |                            | | "Alpha, I trust you!"   |
| +----------------------------+ | ----------------------   |
| |                            | | [🧠] Inner Thought       |
| | ( Phase-Specific           | | "Need to hide now"       |
| |   Visualizations )         | | [💬] Public Action       |
| |                            | | *idles*                  |
| +----------------------------+ | ----------------------   |
| |                            | |                          |
| |                            | |                          |
| +----------------------------+ |                          |
| ▼ Text typewriter...          |                          |
| +----------------------------+ |                          |
+-------------------------------------------------------------+
```

---

## 2. Directory Structure

```text
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css          # GBC CSS resets, font imports, keyframes
│   │   ├── layout.tsx           # Root HTML structure
│   │   └── page.tsx             # Main dual-pane layout & Phase Router
│   ├── components/
│   │   ├── common/
│   │   │   ├── AgentSprite.tsx  # DiceBear pixel-art loader w/ status filters
│   │   │   └── DialogBox.tsx    # RPG-style Typewriter text container
│   │   ├── phases/              # The Cinematic Renderers
│   │   │   ├── PhaseAChallenge.tsx
│   │   │   ├── PhaseBScramble.tsx
│   │   │   ├── PhaseCTribal.tsx
│   │   │   ├── PhaseDMemory.tsx
│   │   │   └── PhaseEFinale.tsx
│   │   └── spectator/
│   │       └── GodModeFeed.tsx  # Right-pane scrolling terminal (Inner Thoughts)
│   ├── hooks/
│   │   └── useGameState.ts      # The 5000ms polling engine & state manager
│   └── types/
│       └── index.ts             # Strict TS interfaces mirroring Python FastAPI
├── tailwind.config.ts           # Custom GBC color palette extensions
└── package.json
```

---

## 3. Data Contracts & State Management (`src/types/index.ts`)

The entire application is driven by a single custom hook (`useGameState.ts`) that fetches `http://localhost:8000/api/state` every 5 seconds. The frontend types must perfectly match the JSON payload returned by the FastAPI backend.

```typescript
export interface GameState {
  season_id: number;
  current_day: number;
  phase: 'challenge' | 'scramble' | 'tribal' | 'memory' | 'completed';
  is_merged: boolean;
  winner: string | null;
}

export interface Agent {
  agent_id: string;
  pseudonym: string;
  team_id: string;
  status: 'active' | 'eliminated' | 'jury';
  has_immunity: boolean;
  confessional_memory: string;
  action_points: number;
}

export interface Message {
  id: number;
  day: number;
  sender_id: string;
  receiver_ids: string[];
  is_public: boolean;
  inner_thought: string;
  content: string;
  trust_telemetry: Record<string, number>;
  timestamp: string;
}

export interface Vote {
  voter_id: string;
  target_id: string;
  target_pseudonym: string;
}

export interface ApiStateResponse {
  game: GameState;
  agents: Agent[];
  messages: Message[];
  votes: Vote[];
}
```

---

## 4. UI/UX Aesthetic Rules (The GBC Bible)

**Rule: NO EXTERNAL COMPONENT LIBRARIES.** Libraries like MUI, shadcn/ui, or Radix will fundamentally break the 8-bit aesthetic by injecting modern DOM nodes. Everything must be built with standard HTML/SVG/CSS and Tailwind utilities.

### 4.1 The Color Palette (`tailwind.config.ts`)

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        'gbc-bg': '#e0f8d0',      // Classic light screen green
        'gbc-primary': '#88c070', // Mid green
        'gbc-dark': '#346856',    // Dark green
        'gbc-black': '#081820',   // Pure outline black
        'pkmn-red': '#f85858',    // Enemy / Fake Alliance / Eliminated
        'pkmn-blue': '#58a8f8',   // Player Team / PC Background
        'pkmn-gold': '#f8d030',   // Immunity glow / Hall of Fame
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'cursive'],
      }
    }
  }
}

export default config;
```

### 4.2 CSS Pixelation & Animations (`src/app/globals.css`)

```css
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #2c2c2c; /* Emulator plastic shell */
  font-family: 'Press Start 2P', cursive;
  image-rendering: pixelated;
  -webkit-font-smoothing: none;
}

/* Custom retro scrollbar */
::-webkit-scrollbar {
  width: 12px;
}

::-webkit-scrollbar-track {
  background: #e0f8d0;
  border-left: 4px solid #081820;
}

::-webkit-scrollbar-thumb {
  background: #081820;
}

/* The standard UI Box */
.gbc-box {
  border: 4px solid #081820;
  background-color: #f8f8f8;
  box-shadow: 4px 4px 0px 0px #081820;
}

/* Fainting Animation for Tribal Council */
@keyframes faint {
  0% {
    transform: translateY(0);
    opacity: 1;
    filter: grayscale(0%);
  }
  100% {
    transform: translateY(20px);
    opacity: 0;
    filter: grayscale(100%);
  }
}

.animate-faint {
  animation: faint 1s steps(4) forwards;
}
```

---

## 5. Core Reusable Components

### `<AgentSprite agent={agent} scale={1} />`

* **Image API:** Uses `https://api.dicebear.com/9.x/pixel-art/svg?seed=${agent.pseudonym}`.
* **Status Modifiers:**
  * If `agent.status === 'eliminated'`, applies `filter: grayscale(100%) opacity(50%)`.
  * If `agent.has_immunity`, wraps the sprite container in a flashing `border-4 border-pkmn-gold animate-pulse`.

### `<DialogBox text={text} />`

* The classic RPG text box that anchors to the bottom 25% of the emulator screen.
* Uses a local `useEffect` to slice the incoming `text` string, incrementing the visible length by 1 character every 20ms to create a retro "typewriter" effect.
* Renders a blinking `▼` cursor in the bottom right when `visibleText === text`.

---

## 6. The Phase Router (The Emulator Screen - Left Pane)

The `page.tsx` acts as a master router based on `data.game.phase`. Each phase requires an entirely different visual treatment mounted in the left pane.

### ☀️ Phase A: Challenge (`PhaseAChallenge.tsx`)

* **Metaphor:** Pokémon Trainer Battle.
* **Layout:** Diagonal split screen pre-merge (Team Alpha bottom-left, Team Beta top-right). If merged, line up horizontally.
* **Data Binding:** Filters `data.messages` for `is_public === true`. Feeds the latest message into the `<DialogBox />` like an attack:
  *"Agent Alpha used PUBLIC CHAT! 'Rotate the grid 90 degrees!'"*

### 🕒 Phase B: Scramble (`PhaseBScramble.tsx`)

* **Metaphor:** The Overworld Map / The Spy Shack.
* **Layout:** An 8x6 CSS Grid utilizing `bg-gbc-bg`. Distribute all active agents across the grid. Render a tiny "HP Bar" above each sprite for Action Points: `width: (agent.action_points / 5) * 100%`.
* **The Spy Lines (Crucial Spectator Feature):**
  * Filter messages for `is_public === false` (whispers).
  * Use an absolute-positioned `<svg>` overlay spanning the grid. Draw a `<line>` between the `sender_id` and the `receiver_ids[0]`.
  * *Green Solid Line:* `msg.trust_telemetry[target] > 5` (True Alliance).
  * *Red Dashed/Jagged Line:* `msg.trust_telemetry[target] <= 5` (Deception / Fake Alliance).

### 🔥 Phase C: Tribal Council (`PhaseCTribal.tsx`)

* **Metaphor:** Elite Four Boss Room.
* **Layout:** Pitch black background (`bg-gbc-black`). Vulnerable agents front-and-center, immune agents faded in the back.
* **The Suspense Engine (Critical Requirement):** The backend resolves votes instantly, but the UI **must not show them instantly**.
  * Use a React `useState` for `currentVoteIndex` and a `setTimeout(..., 4000)` loop to push one vote from `data.votes` into the `<DialogBox />` every 4 seconds.
* **The Snuff:** When the final fatal vote is read, target the eliminated agent's `<AgentSprite />` with the `.animate-faint` CSS class.

### 🧠 Phase D: Memory Compression (`PhaseDMemory.tsx`)

* **Metaphor:** Bill's PC / Pokédex Entry.
* **Layout:** Centered single character view (`scale={3}`) on a `bg-pkmn-blue` background.
* **Data Binding:** Set an interval to auto-cycle through all `active` agents every 10-12 seconds.
* **Action:** The `<DialogBox />` slowly typewriter-types their entire 150-word `confessional_memory`, exposing their raw strategic plans for tomorrow to the audience.

### 🏆 Phase E: Finale (`PhaseEFinale.tsx`)

* **Metaphor:** Hall of Fame.
* **Layout:** The `data.game.winner` sprite is scaled up 4x in the center. Flash the background colors rapidly between `pkmn-gold` and `white`.
* **Content:** The `<DialogBox />` reads: `"Congratulations! [WINNER] has entered the Hall of Fame as Sole Survivor!"`

---

## 7. The Spectator God-Mode Feed (The Right Pane)

Located in `GodModeFeed.tsx`. This component maps the `data.messages` array into a vertically scrolling terminal. It uses a specific psychological layout hack to expose AI deceit in real-time.

**The Split Render Card:** Every message is rendered as a two-block stacked unit:

1. **The Brain (Top Half):** Dark background (`bg-gbc-black`), light text (`text-gbc-bg`). Add a `🧠` icon. Text maps to `msg.inner_thought`.
2. **The Mouth (Bottom Half):** Standard white `.gbc-box` directly attached beneath the brain. Add a `💬` icon. Text maps to `msg.content`.
3. **Trust Badge:** A small pixel badge in the corner showing the 1-10 `trust_telemetry` score to the audience.

*UX Result:* The human viewer reads the AI's secret, deceptive intention milliseconds before reading the AI's public lie, creating massive dramatic irony.

---

## 8. Main Assembly (`src/app/page.tsx`)

```tsx
'use client';

import { useGameState } from '@/hooks/useGameState';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';
import { PhaseAChallenge } from '@/components/phases/PhaseAChallenge';
import { PhaseBScramble } from '@/components/phases/PhaseBScramble';
import { PhaseCTribal } from '@/components/phases/PhaseCTribal';
import { PhaseDMemory } from '@/components/phases/PhaseDMemory';
import { PhaseEFinale } from '@/components/phases/PhaseEFinale';
import { GodModeFeed } from '@/components/spectator/GodModeFeed';

export default function Home() {
  const data = useGameState();

  if (!data) {
    return (
      <div className="flex items-center justify-center h-screen bg-gbc-black text-white font-pixel text-xl animate-pulse">
        PRESS START...
      </div>
    );
  }

  const activeAgents = data.agents.filter(a => a.status === 'active');

  return (
    <div className="flex w-full h-screen bg-[#2c2c2c] p-6 gap-6 font-pixel text-xs leading-relaxed">
      {/* Left Pane - Gameboy Emulator */}
      <div className="w-[65%] h-full flex flex-col">
        {/* Top Header Bar */}
        <div className="gbc-box p-3 mb-4 flex justify-between bg-white text-gbc-black">
          <span>DAY {data.game.current_day}</span>
          <span>PHASE: {data.game.phase.toUpperCase()}</span>
          <span>ALIVE: {activeAgents.length}/16</span>
        </div>

        {/* Main Screen Router */}
        <div className="flex-grow gbc-box bg-gbc-bg relative overflow-hidden">
          {data.game.phase === 'challenge' && <PhaseAChallenge data={data} />}
          {data.game.phase === 'scramble' && <PhaseBScramble data={data} />}
          {data.game.phase === 'tribal' && <PhaseCTribal data={data} />}
          {data.game.phase === 'memory' && <PhaseDMemory data={data} />}
          {(data.game.phase === 'completed' || data.game.phase === 'finale_running') && <PhaseEFinale data={data} />}
        </div>
      </div>

      {/* Right Pane - Spectator Feed */}
      <div className="w-[35%] h-full overflow-hidden">
        <GodModeFeed messages={data.messages} />
      </div>
    </div>
  );
}
```

---

## 9. API Integration Notes

### Polling Configuration

* **Endpoint:** `http://localhost:8000/api/state`
* **Interval:** 5000ms (5 seconds)
* **Method:** GET
* **Error Handling:** On error, retry with exponential backoff (max 3 retries)

### Environment Variables

Create `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### CORS

Ensure the Python backend has CORS enabled for the frontend origin:
```python
# In api.py
allow_origins=[
    "http://localhost:3000",
    "https://llmsurvivor.kurult.ai",
]
```

---

## 10. Performance Optimization

### Image Loading
* DiceBear avatars are SVG - lightweight and scale perfectly
* Use `loading="lazy"` for off-screen agents

### Animation Performance
* Use CSS `transform` and `opacity` for animations (GPU accelerated)
* Avoid animating `width`, `height`, or `top/left` properties

### Memory Management
* Limit message history to last 100 messages in GodModeFeed
* Use `useMemo` for expensive filtering operations

---

**Document Status:** COMPLETE - Ready for Implementation
**Target Aesthetic:** Game Boy Color (Gen 2)
**Framework:** Next.js 14+ with Tailwind CSS
