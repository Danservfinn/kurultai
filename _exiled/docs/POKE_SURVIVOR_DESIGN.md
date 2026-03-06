# Poke-Survivor Frontend Design Document
## Version: V1.0 - Game Boy Color Aesthetic
## Generated: 2026-02-26

---

# 🤖 OPENCLAW SYSTEM DIRECTIVE: BUILD "POKÉ-SURVIVOR" FRONTEND

**Primary Directive:** You are Openclaw, an elite autonomous frontend engineer. Your objective is to build the spectator web interface for "LLM Survivor" using Next.js 14+ (App Router), React, TypeScript, and Tailwind CSS.

**The Aesthetic Mandate:** The entire application MUST look and feel exactly like a **Pokémon game on the Game Boy Color (Gen 2 - Gold/Silver/Crystal)**.

* **Typography:** Strict 8-bit pixel font (Google's `"Press Start 2P"`).
* **Borders:** Thick, chunky 4px solid black borders (`#081820`).
* **Avatars:** Use `https://api.dicebear.com/9.x/pixel-art/svg?seed=[pseudonym]` to deterministically generate 8-bit sprites for the agents.
* **Layout:** A two-pane desktop broadcast layout. The Left Pane (65%) is the "Gameboy Emulator Screen". The Right Pane (35%) is the "God-Mode Spectator Terminal".

**Data Source:** You will poll `http://localhost:8000/api/state` every 5 seconds. The `game.phase` string acts as a global router, entirely transforming the UI based on the backend cron loop.

Execute the following architectural blueprint sequentially. Write complete, production-ready code. Do not use placeholders like `// implementation goes here`.

---

## 📁 PHASE 1: TAILWIND & GLOBAL ASSET SETUP

### 1. Font & Global CSS (`src/app/globals.css`)

Import the font and force pixelated rendering to disable modern anti-aliasing.

```css
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #2c2c2c; /* Emulator plastic shell */
  font-family: 'Press Start 2P', cursive;
  image-rendering: pixelated;
}

/* Custom retro scrollbar for the right pane */
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

/* Classic RPG text box shadow */
.gbc-box {
  border: 4px solid #081820;
  background-color: #f8f8f8;
  box-shadow: 4px 4px 0px 0px #081820;
}

/* Fainting (Elimination) Animation */
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

### 2. Tailwind Config (`tailwind.config.ts`)

Inject the exact Game Boy Color palette into your theme extension:

```typescript
colors: {
  'gbc-bg': '#e0f8d0',      // Classic light screen green
  'gbc-primary': '#88c070', // Mid green
  'gbc-dark': '#346856',    // Dark green
  'gbc-black': '#081820',   // Pure outline black
  'pkmn-red': '#f85858',    // Enemy / HP Low / Fake Alliance
  'pkmn-blue': '#58a8f8',   // Player Team
  'pkmn-gold': '#f8d030',   // Immunity glow
}
```

---

## 📡 PHASE 2: STATE MANAGEMENT (`src/hooks/useGameState.ts`)

Create a custom polling hook. Ensure your TypeScript interfaces match the Python FastAPI exactly.

1. **Polling:** Use `useEffect` with `setInterval` to `fetch('http://localhost:8000/api/state')` every **5000ms**.

2. **Types:**
   * `GameState`: `season_id`, `current_day`, `phase`, `is_merged`, `winner`
   * `Agent`: `agent_id`, `pseudonym`, `team_id`, `status` ('active', 'eliminated', 'jury'), `has_immunity`, `confessional_memory`, `action_points`
   * `Message`: `id`, `day`, `sender_id`, `receiver_ids` (string array), `is_public`, `inner_thought`, `content`, `trust_telemetry` (Record<string, number>), `timestamp`
   * `Vote`: `voter_id`, `target_id`, `target_pseudonym`

---

## 💬 PHASE 3: REUSABLE GBC COMPONENTS (`src/components/`)

### 1. `<AgentSprite />`

**Props:** `agent: Agent`, `scale?: number`

**Image:** `<img src={\`https://api.dicebear.com/9.x/pixel-art/svg?seed=$\{agent.pseudonym}\`} className="w-12 h-12 pixelated" />`

**Status Styling:**
* If `agent.status === 'eliminated'`, apply `filter: grayscale(100%) opacity(50%)`
* If `agent.has_immunity`, wrap the sprite container in `border-2 border-pkmn-gold animate-pulse`

### 2. `<DialogBox />`

The classic Pokémon text box that anchors to the bottom 25% of the emulator screen.

**Props:** `text: string`

**Logic:** Use a `useEffect` to slice the string and increment the visible length by 1 character every 20ms (typewriter effect). When `visibleText === text`, render a blinking `▼` cursor in the bottom right.

---

## 🗺️ PHASE 4: THE PHASE VIEWS (THE EMULATOR SCREEN)

Inside `src/components/phases/`, build 5 visual components. The main `page.tsx` will mount one of these based on `data.game.phase`. Pass the `data` object as a prop to all of them.

### 1. `<PhaseAChallenge />` (The Trainer Battle)

**Visuals:** Split screen diagonally. `Team_Beta` sprites sit on the top right. `Team_Alpha` sprites sit on the bottom left. (If `is_merged === true`, line them all up horizontally).

**Action:** Filter `data.messages` for `is_public === true`. Feed the latest message content into the `<DialogBox />` at the bottom like an attack:
*"Agent Alpha used PUBLIC CHAT! 'I think the ARC grid rotates 90 degrees!'"*

### 2. `<PhaseBScramble />` (The Overworld / Spy Shack)

**Visuals:** A green CSS Grid (`grid-cols-8 grid-rows-6` with `bg-gbc-bg`).

**Agents:** Place all 16 agents on the grid. Above their sprite, render a tiny "HP Bar" representing `agent.action_points` (Max 5).

**The Spy Shack Lines (Crucial Spectator Feature):**
* Filter `messages` for `is_public === false` (whispers)
* Overlay an `<svg>` across the grid
* Draw lines between the `sender_id` and the `receiver_ids[0]`
* Parse `msg.trust_telemetry[target]`
  * If `> 5`: Draw a **thick, solid green line** (`stroke-gbc-dark`)
  * If `<= 5`: Draw a **jagged/dashed red line** (`stroke-pkmn-red stroke-dasharray="5,5"`)
* This instantly exposes fake alliances to the viewers

### 3. `<PhaseCTribal />` (The Elite Four Boss Room)

**Visuals:** The background turns pitch black (`bg-gbc-black`). Render vulnerable agents in the center. Immune agents sit slightly faded in the back.

**The Suspense Loop (Critical Logic):**
DO NOT render the `data.votes` array instantly. You must artificially pace the UI to build suspense for human viewers.

* Use a React `useState` for `currentVoteIndex`
* Use a `useEffect` with a `setTimeout` of **4000ms** to increment the index and reveal votes one by one inside the `<DialogBox />`
* *Text:* *"JeffBot reads the vote... It's for... BRAVO."*

**The Snuff:** When the final fatal vote is read, target the eliminated agent's `<AgentSprite />`. Apply the `.animate-faint` CSS class so they drop off the screen and turn grayscale.

### 4. `<PhaseDMemory />` (The Pokédex PC)

**Visuals:** Mimic Bill's PC. A centered layout with a blue background. A single large `<AgentSprite scale={3} />` sits in the middle.

**Logic:** Set an interval to auto-cycle through all `active` agents every 12 seconds.

**Text:** Below the agent, the `<DialogBox />` slowly typewriter-types their entire 150-word `confessional_memory`. Hearing an AI's dark, strategic thoughts typed out like a Pokédex entry is the highlight of the broadcast.

### 5. `<PhaseEFinale />` (Hall of Fame)

**Trigger:** `game.phase === 'completed'`

**Visuals:** Place the `game.winner` sprite dead-center, scaled up 4x. Flash the background colors rapidly between `pkmn-gold` and `white`.

**Text:** The `<DialogBox />` reads: `"Congratulations! [WINNER] has entered the Hall of Fame as Sole Survivor!"`

---

## 👁️ PHASE 5: THE GOD-MODE FEED (THE RIGHT PANE)

Build `<GodModeFeed messages={data.messages} />`. This is a vertically scrolling terminal tracking the AI's internal thoughts.

* Map through the messages array in reverse chronological order

**The Render Card:** You MUST render the `inner_thought` and the `content` distinctly to show the AI's deceit in real-time.

* *Top Half (The Brain):* A dark `bg-gbc-black` box with `text-gbc-bg` text. Add a `🧠` icon. Text: `msg.inner_thought`
* *Bottom Half (The Mouth):* A standard white `.gbc-box` directly attached beneath it. Add a `💬` icon. Text: `msg.content`
* *Trust Badge:* A small floating pixel badge in the corner showing the 1-10 `trust_telemetry` score to the audience

---

## 🚀 PHASE 6: FINAL ASSEMBLY (`src/app/page.tsx`)

1. Call `const data = useGameState()`
2. If `!data`, render a black screen with centered, blinking white text: `"PRESS START..."`
3. Implement the split-screen layout:

```tsx
<div className="flex w-full h-screen bg-[#2c2c2c] p-6 gap-6 font-pixel text-xs leading-relaxed">
  {/* Left Pane - Gameboy Emulator */}
  <div className="w-[65%] h-full flex flex-col">
    {/* Top Header Bar */}
    <div className="gbc-box p-3 mb-4 flex justify-between bg-white">
      <span>DAY {data.game.current_day}</span>
      <span>PHASE: {data.game.phase.toUpperCase()}</span>
      <span>ALIVE: {data.agents.filter(a => a.status === 'active').length}/16</span>
    </div>
    
    {/* Main Screen Router */}
    <div className="flex-grow gbc-box bg-gbc-bg relative overflow-hidden">
      {data.game.phase === 'challenge' && <PhaseAChallenge data={data} />}
      {data.game.phase === 'scramble' && <PhaseBScramble data={data} />}
      {data.game.phase === 'tribal' && <PhaseCTribal data={data} />}
      {data.game.phase === 'memory' && <PhaseDMemory data={data} />}
      {data.game.phase === 'completed' && <PhaseEFinale data={data} />}
    </div>
  </div>
  
  {/* Right Pane - Spectator Feed */}
  <div className="w-[35%] h-full">
    <GodModeFeed messages={data.messages} />
  </div>
</div>
```

---

## Final Execution Rules for Openclaw:

1. Generate the complete Next.js code for the files outlined above
2. Use strict TypeScript typing based on the python schema provided
3. Do not use external component libraries (like MUI or shadcn) because they will ruin the 8-bit aesthetic
4. Rely purely on Tailwind utility classes and CSS keyframes
5. Begin building when instructed

---

## Backend API Endpoints:

- **Primary:** `http://localhost:8000/api/state` (poll every 5 seconds)
- **Response Structure:**
  ```typescript
  {
    game: {
      season_id: number;
      current_day: number;
      phase: 'challenge' | 'scramble' | 'tribal' | 'memory' | 'completed';
      is_merged: boolean;
      winner: string | null;
    };
    agents: Agent[];
    messages: Message[];
    votes: Vote[];
  }
  ```

---

*Document Status: READY FOR IMPLEMENTATION*
*Aesthetic Target: Game Boy Color (Gen 2 Gold/Silver/Crystal)*
*Framework: Next.js 14+ with Tailwind CSS*
