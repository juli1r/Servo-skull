# Coach-Vox — Suivi multi-tables pour coach — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone web app ("coach-vox") letting a Warhammer team coach watch, in real time, every table of their team during a scrim session (virtual/TTS or in-person), spot which table needs them, and run a post-session debrief — per `docs/superpowers/specs/2026-11-06-coach-multi-tables-design.md` in the Servo-Skull repo.

**Architecture:** React + TypeScript single-page app, Firebase Auth (email/password) for coach and player accounts, Firestore for `teams`, `memberships`, `sessions`, `tables` (realtime `onSnapshot` powers the dashboard). Players and coaches write `TableState` documents manually (mobile form / inline dashboard edit) for in-person scrims; an external capture tool (future Servo-Skull integration) writes the same documents with `source: "auto"` and an optional `liveViewUrl` pointing at that tool's own spectator page — the zoom view embeds that URL rather than re-implementing battle-map rendering in this app (explicit scope decision, see Task 15).

**Tech Stack:** Vite, React 18, TypeScript, React Router, Vitest + React Testing Library, Firebase (Auth, Firestore, Hosting).

**Assumptions locked in by this plan (not fully specified in the design doc — flagging for the human to override if wrong):**
- Auth method: Firebase email/password (simplest, no OAuth app registration needed to ship an MVP).
- New repo at `C:\Users\Megaport\Documents\Claude\Projects\coach-vox`, created fresh in Task 1.
- Zoom view embeds an externally-provided `liveViewUrl` (e.g. a Servo-Skull `site/live.html?code=...` link) rather than rendering the battle map itself — re-implementing that renderer is out of scope for this plan.

---

## File Structure

```
coach-vox/
  package.json, vite.config.ts, tsconfig.json, index.html
  firebase.json, firestore.rules, firestore.indexes.json
  src/
    main.tsx, App.tsx
    firebase.ts                  # Firebase app/auth/db init
    types.ts                     # Team, Membership, Session, TableState
    auth/
      useAuth.ts                 # onAuthStateChanged hook
      LoginForm.tsx
    team/
      invite.ts                  # buildInviteUrl / parseInviteUrl (pure)
      teamApi.ts                 # createTeam, joinTeamViaInvite
      InvitePage.tsx
    session/
      sessionApi.ts              # openSession, closeSession
      SessionControls.tsx
    tables/
      tableApi.ts                # createManualTable, updateTable, setNeedsCoach
      rhythm.ts                  # computeRhythm (pure)
      validateAutoPayload.ts     # validates an incoming source:"auto" write (pure)
      useLiveTables.ts           # onSnapshot hook, scoped to a session
      TableCard.tsx
      EditTableModal.tsx         # coach create/edit a manual table
      PlayerTableForm.tsx        # player's own mobile update form
      ZoomView.tsx
    debrief/
      computeDebrief.ts          # pure aggregation over a session's tables
      DebriefScreen.tsx
    dashboard/
      Dashboard.tsx
  src/**/*.test.ts(x)            # colocated tests
```

---

### Task 1: Project scaffold

**Files:**
- Create: `coach-vox/` (new repo)

- [ ] **Step 1: Create the project**

```bash
cd "C:\Users\Megaport\Documents\Claude\Projects"
npm create vite@latest coach-vox -- --template react-ts
cd coach-vox
npm install
```

- [ ] **Step 2: Add test tooling**

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @testing-library/user-event
```

- [ ] **Step 3: Configure Vitest**

Modify `coach-vox/vite.config.ts`:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
  },
})
```

Create `coach-vox/src/setupTests.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

Modify `coach-vox/package.json` scripts — add:

```json
"test": "vitest run"
```

- [ ] **Step 4: Verify the scaffold runs and tests execute**

Run: `npm test`
Expected: `No test files found` (not an error) — confirms Vitest is wired up.

- [ ] **Step 5: Init git and commit**

```bash
git init
git add -A
git commit -m "chore: scaffold coach-vox (Vite + React + TypeScript + Vitest)"
```

---

### Task 2: Domain types

**Files:**
- Create: `coach-vox/src/types.ts`

- [ ] **Step 1: Write the types**

```ts
export type Role = 'coach' | 'player'

export interface Team {
  id: string
  name: string
  ownerId: string          // coach's uid
  inviteToken: string      // stable, permanent invite secret
  createdAt: number
}

export interface Membership {
  id: string                // `${teamId}_${userId}`
  teamId: string
  userId: string
  role: Role
  joinedAt: number
}

export type SessionStatus = 'open' | 'closed'

export interface ScrimSession {
  id: string
  teamId: string
  name: string
  status: SessionStatus
  openedAt: number
  closedAt: number | null
}

export type TableSource = 'auto' | 'player_manual' | 'coach_manual'

export interface TableState {
  id: string
  sessionId: string
  playerId: string
  playerName: string
  opponentName: string
  myScore: number
  oppScore: number
  round: number
  phase: string
  roundStartedAt: number     // epoch ms, resets whenever round/phase changes
  needsCoach: boolean
  source: TableSource
  updatedBy: string           // uid of whoever last wrote this doc
  updatedAt: number
  liveViewUrl: string | null  // present only for source:"auto" tables with a capture tool
}
```

This file has no logic to test — it's type-only. No test step for this task.

- [ ] **Step 2: Commit**

```bash
git add src/types.ts
git commit -m "feat: domain types (Team, Membership, ScrimSession, TableState)"
```

---

### Task 3: Firebase project + client init

**Files:**
- Create: `coach-vox/src/firebase.ts`
- Create: `coach-vox/.env.local.example`
- Modify: `coach-vox/.gitignore`

- [ ] **Step 1: Create the Firebase project and a web app**

Manual step (no CLI available without an interactive login): go to https://console.firebase.google.com, create a project named `coach-vox`, enable **Authentication → Email/Password**, enable **Firestore Database** (production mode, pick a region). Register a Web App and copy the config object it gives you.

- [ ] **Step 2: Add the env template and gitignore entry**

Create `coach-vox/.env.local.example`:

```
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
```

Append to `coach-vox/.gitignore`:

```
.env.local
```

Copy `.env.local.example` to `.env.local` and fill it with the values from Step 1 (this file is gitignored, never commit real values).

- [ ] **Step 3: Write the Firebase init module**

```ts
// src/firebase.ts
import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'
import { getFirestore } from 'firebase/firestore'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const db = getFirestore(app)
```

- [ ] **Step 4: Install the SDK and verify it builds**

```bash
npm install firebase
npm run build
```

Expected: build succeeds (env vars are read at build time from `.env.local`).

- [ ] **Step 5: Commit**

```bash
git add src/firebase.ts .env.local.example .gitignore package.json package-lock.json
git commit -m "feat: Firebase client init (Auth + Firestore)"
```

---

### Task 4: Firestore security rules

**Files:**
- Create: `coach-vox/firestore.rules`
- Create: `coach-vox/firebase.json`
- Create: `coach-vox/firestore.indexes.json`

- [ ] **Step 1: Write the rules**

```
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    function isSignedIn() {
      return request.auth != null;
    }

    function isMember(teamId) {
      return isSignedIn() &&
        exists(/databases/$(database)/documents/memberships/$(teamId + '_' + request.auth.uid));
    }

    function isCoach(teamId) {
      return isSignedIn() &&
        get(/databases/$(database)/documents/memberships/$(teamId + '_' + request.auth.uid)).data.role == 'coach';
    }

    match /teams/{teamId} {
      allow read: if isMember(teamId);
      allow create: if isSignedIn() && request.resource.data.ownerId == request.auth.uid;
      allow update: if isCoach(teamId);
    }

    match /memberships/{membershipId} {
      allow read: if isSignedIn();
      // A membership can only be created by the user it names for themselves
      // (joining via invite), or by the team's coach.
      allow create: if isSignedIn() && request.resource.data.userId == request.auth.uid;
    }

    match /sessions/{sessionId} {
      allow read: if isMember(resource.data.teamId);
      allow create, update: if isCoach(request.resource.data.teamId);
    }

    match /tables/{tableId} {
      allow read: if isSignedIn();
      allow create, update: if isSignedIn();
      // Deliberately permissive on write (any signed-in team member or an
      // external auto-capture tool holding a valid user token can write) —
      // tightened post-MVP once the auto-capture auth story is designed.
    }
  }
}
```

- [ ] **Step 2: Write the Firebase project config**

```json
// firebase.json
{
  "firestore": {
    "rules": "firestore.rules",
    "indexes": "firestore.indexes.json"
  },
  "hosting": {
    "public": "dist",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [{ "source": "**", "destination": "/index.html" }]
  }
}
```

```json
// firestore.indexes.json
{
  "indexes": [],
  "fieldOverrides": []
}
```

- [ ] **Step 3: Deploy the rules (manual, needs Firebase CLI login)**

```bash
npm install -g firebase-tools
firebase login
firebase use --add   # pick the coach-vox project
firebase deploy --only firestore:rules
```

- [ ] **Step 4: Commit**

```bash
git add firestore.rules firebase.json firestore.indexes.json
git commit -m "feat: Firestore security rules (team/membership/session/table scoping)"
```

---

### Task 5: Invite link (pure logic)

**Files:**
- Create: `coach-vox/src/team/invite.ts`
- Test: `coach-vox/src/team/invite.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/team/invite.test.ts
import { describe, it, expect } from 'vitest'
import { buildInviteUrl, parseInviteUrl } from './invite'

describe('invite link', () => {
  it('round-trips teamId and token through the URL', () => {
    const url = buildInviteUrl('team123', 'tok_abc')
    expect(url).toBe('https://coach-vox.web.app/join/team123/tok_abc')
    expect(parseInviteUrl(url)).toEqual({ teamId: 'team123', token: 'tok_abc' })
  })

  it('returns null for a URL that is not an invite link', () => {
    expect(parseInviteUrl('https://coach-vox.web.app/dashboard')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- invite`
Expected: FAIL — `./invite` has no exported members.

- [ ] **Step 3: Implement**

```ts
// src/team/invite.ts
const BASE_URL = 'https://coach-vox.web.app'

export function buildInviteUrl(teamId: string, token: string): string {
  return `${BASE_URL}/join/${teamId}/${token}`
}

export function parseInviteUrl(url: string): { teamId: string; token: string } | null {
  const match = url.match(/\/join\/([^/]+)\/([^/]+)\/?$/)
  if (!match) return null
  const [, teamId, token] = match
  return { teamId, token }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- invite`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/team/invite.ts src/team/invite.test.ts
git commit -m "feat: invite link build/parse"
```

---

### Task 6: Auth hook + login form

**Files:**
- Create: `coach-vox/src/auth/useAuth.ts`
- Create: `coach-vox/src/auth/LoginForm.tsx`
- Test: `coach-vox/src/auth/LoginForm.test.tsx`

- [ ] **Step 1: Write the hook (no test — thin wrapper over Firebase, verified via the form test below)**

```ts
// src/auth/useAuth.ts
import { useEffect, useState } from 'react'
import { onAuthStateChanged, type User } from 'firebase/auth'
import { auth } from '../firebase'

export function useAuth(): { user: User | null; loading: boolean } {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    return onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
  }, [])

  return { user, loading }
}
```

- [ ] **Step 2: Write the failing test for the form**

```tsx
// src/auth/LoginForm.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginForm } from './LoginForm'

describe('LoginForm', () => {
  it('calls onSubmit with email and password', async () => {
    const onSubmit = vi.fn()
    render(<LoginForm onSubmit={onSubmit} />)

    await userEvent.type(screen.getByLabelText(/email/i), 'coach@example.com')
    await userEvent.type(screen.getByLabelText(/mot de passe/i), 'hunter2')
    await userEvent.click(screen.getByRole('button', { name: /connexion/i }))

    expect(onSubmit).toHaveBeenCalledWith('coach@example.com', 'hunter2')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- LoginForm`
Expected: FAIL — `./LoginForm` module not found.

- [ ] **Step 4: Implement the form**

```tsx
// src/auth/LoginForm.tsx
import { useState, type FormEvent } from 'react'

interface LoginFormProps {
  onSubmit: (email: string, password: string) => void
}

export function LoginForm({ onSubmit }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit(email, password)
  }

  return (
    <form onSubmit={handleSubmit}>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />

      <label htmlFor="password">Mot de passe</label>
      <input
        id="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      <button type="submit">Connexion</button>
    </form>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- LoginForm`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/auth/useAuth.ts src/auth/LoginForm.tsx src/auth/LoginForm.test.tsx
git commit -m "feat: auth hook + login form"
```

---

### Task 7: Team creation + join via invite

**Files:**
- Create: `coach-vox/src/team/teamApi.ts`
- Create: `coach-vox/src/team/InvitePage.tsx`

- [ ] **Step 1: Write the Firestore-writing functions**

```ts
// src/team/teamApi.ts
import { doc, setDoc, getDoc } from 'firebase/firestore'
import { db } from '../firebase'
import type { Team, Membership } from '../types'

export async function createTeam(ownerId: string, name: string): Promise<Team> {
  const id = crypto.randomUUID()
  const team: Team = {
    id,
    name,
    ownerId,
    inviteToken: crypto.randomUUID(),
    createdAt: Date.now(),
  }
  await setDoc(doc(db, 'teams', id), team)

  const membership: Membership = {
    id: `${id}_${ownerId}`,
    teamId: id,
    userId: ownerId,
    role: 'coach',
    joinedAt: Date.now(),
  }
  await setDoc(doc(db, 'memberships', membership.id), membership)

  return team
}

export async function joinTeamViaInvite(
  teamId: string,
  token: string,
  userId: string,
): Promise<'joined' | 'invalid-token'> {
  const teamSnap = await getDoc(doc(db, 'teams', teamId))
  if (!teamSnap.exists() || teamSnap.data().inviteToken !== token) {
    return 'invalid-token'
  }
  const membership: Membership = {
    id: `${teamId}_${userId}`,
    teamId,
    userId,
    role: 'player',
    joinedAt: Date.now(),
  }
  await setDoc(doc(db, 'memberships', membership.id), membership)
  return 'joined'
}
```

This task is a thin Firestore wrapper with no branching logic worth a unit test beyond what Task 5 already covers (the token comparison itself is a one-liner) — no dedicated test step, verified manually in Task 14's end-to-end check.

- [ ] **Step 2: Write the invite landing page**

```tsx
// src/team/InvitePage.tsx
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { joinTeamViaInvite } from './teamApi'
import { useAuth } from '../auth/useAuth'

export function InvitePage() {
  const { teamId, token } = useParams<{ teamId: string; token: string }>()
  const { user } = useAuth()
  const [status, setStatus] = useState<'idle' | 'joined' | 'invalid-token'>('idle')

  async function handleJoin() {
    if (!user || !teamId || !token) return
    const result = await joinTeamViaInvite(teamId, token, user.uid)
    setStatus(result)
  }

  if (!user) return <p>Connecte-toi d'abord pour rejoindre l'équipe.</p>
  if (status === 'joined') return <p>Équipe rejointe !</p>
  if (status === 'invalid-token') return <p>Lien d'invitation invalide.</p>

  return <button onClick={handleJoin}>Rejoindre l'équipe</button>
}
```

- [ ] **Step 3: Commit**

```bash
git add src/team/teamApi.ts src/team/InvitePage.tsx
git commit -m "feat: team creation and invite-based join flow"
```

---

### Task 8: Session open/close

**Files:**
- Create: `coach-vox/src/session/sessionApi.ts`
- Create: `coach-vox/src/session/SessionControls.tsx`
- Test: `coach-vox/src/session/SessionControls.test.tsx`

- [ ] **Step 1: Write the Firestore functions**

```ts
// src/session/sessionApi.ts
import { doc, setDoc, updateDoc } from 'firebase/firestore'
import { db } from '../firebase'
import type { ScrimSession } from '../types'

export async function openSession(teamId: string, name: string): Promise<ScrimSession> {
  const session: ScrimSession = {
    id: crypto.randomUUID(),
    teamId,
    name,
    status: 'open',
    openedAt: Date.now(),
    closedAt: null,
  }
  await setDoc(doc(db, 'sessions', session.id), session)
  return session
}

export async function closeSession(sessionId: string): Promise<void> {
  await updateDoc(doc(db, 'sessions', sessionId), {
    status: 'closed',
    closedAt: Date.now(),
  })
}
```

- [ ] **Step 2: Write the failing test for the controls component**

```tsx
// src/session/SessionControls.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SessionControls } from './SessionControls'

describe('SessionControls', () => {
  it('opens a session with the typed name', async () => {
    const onOpen = vi.fn()
    render(<SessionControls session={null} onOpen={onOpen} onClose={vi.fn()} />)

    await userEvent.type(screen.getByLabelText(/nom de la session/i), 'Scrim mardi')
    await userEvent.click(screen.getByRole('button', { name: /ouvrir/i }))

    expect(onOpen).toHaveBeenCalledWith('Scrim mardi')
  })

  it('closes an open session', async () => {
    const onClose = vi.fn()
    render(
      <SessionControls
        session={{ id: 's1', teamId: 't1', name: 'Scrim mardi', status: 'open', openedAt: 1, closedAt: null }}
        onOpen={vi.fn()}
        onClose={onClose}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /fermer/i }))
    expect(onClose).toHaveBeenCalledWith('s1')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- SessionControls`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement**

```tsx
// src/session/SessionControls.tsx
import { useState } from 'react'
import type { ScrimSession } from '../types'

interface SessionControlsProps {
  session: ScrimSession | null
  onOpen: (name: string) => void
  onClose: (sessionId: string) => void
}

export function SessionControls({ session, onOpen, onClose }: SessionControlsProps) {
  const [name, setName] = useState('')

  if (session && session.status === 'open') {
    return (
      <div>
        <p>Session en cours : {session.name}</p>
        <button onClick={() => onClose(session.id)}>Fermer la session</button>
      </div>
    )
  }

  return (
    <div>
      <label htmlFor="session-name">Nom de la session</label>
      <input id="session-name" value={name} onChange={(e) => setName(e.target.value)} />
      <button onClick={() => onOpen(name)}>Ouvrir</button>
    </div>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- SessionControls`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/session/sessionApi.ts src/session/SessionControls.tsx src/session/SessionControls.test.tsx
git commit -m "feat: session open/close"
```

---

### Task 9: Rhythm calculation (pure logic — the retard signal)

**Files:**
- Create: `coach-vox/src/tables/rhythm.ts`
- Test: `coach-vox/src/tables/rhythm.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/tables/rhythm.test.ts
import { describe, it, expect } from 'vitest'
import { computeRhythm } from './rhythm'
import type { TableState } from '../types'

function table(id: string, roundStartedAt: number): TableState {
  return {
    id,
    sessionId: 's1',
    playerId: id,
    playerName: id,
    opponentName: 'opp',
    myScore: 0,
    oppScore: 0,
    round: 1,
    phase: 'Tir',
    roundStartedAt,
    needsCoach: false,
    source: 'player_manual',
    updatedBy: id,
    updatedAt: roundStartedAt,
    liveViewUrl: null,
  }
}

describe('computeRhythm', () => {
  it('flags a table as late when its round takes much longer than the team average', () => {
    const now = 1_000_000
    const tables = [
      table('t1', now - 10 * 60_000), // 10 min on this round
      table('t2', now - 12 * 60_000), // 12 min
      table('t3', now - 38 * 60_000), // 38 min — outlier
    ]

    const result = computeRhythm(tables, now)

    expect(result.get('t1')!.isLate).toBe(false)
    expect(result.get('t2')!.isLate).toBe(false)
    expect(result.get('t3')!.isLate).toBe(true)
  })

  it('never flags anything late with a single table (no average to compare to)', () => {
    const now = 1_000_000
    const tables = [table('t1', now - 60 * 60_000)]

    const result = computeRhythm(tables, now)

    expect(result.get('t1')!.isLate).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- rhythm`
Expected: FAIL — `./rhythm` has no exported members.

- [ ] **Step 3: Implement**

A table is "late" when its own round duration exceeds 1.5× the team's average round duration, and at least two tables are being compared (a single table has no average to be late against).

```ts
// src/tables/rhythm.ts
import type { TableState } from '../types'

export interface RhythmInfo {
  elapsedMs: number
  ratioToAverage: number
  isLate: boolean
}

const LATE_THRESHOLD = 1.5

export function computeRhythm(tables: TableState[], now: number): Map<string, RhythmInfo> {
  const elapsedByTable = tables.map((t) => ({
    id: t.id,
    elapsedMs: now - t.roundStartedAt,
  }))

  const average =
    elapsedByTable.reduce((sum, t) => sum + t.elapsedMs, 0) / elapsedByTable.length

  const result = new Map<string, RhythmInfo>()
  for (const { id, elapsedMs } of elapsedByTable) {
    const ratioToAverage = average > 0 ? elapsedMs / average : 1
    const isLate = elapsedByTable.length > 1 && ratioToAverage > LATE_THRESHOLD
    result.set(id, { elapsedMs, ratioToAverage, isLate })
  }
  return result
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- rhythm`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tables/rhythm.ts src/tables/rhythm.test.ts
git commit -m "feat: relative rhythm calculation (retard signal)"
```

---

### Task 10: Table CRUD (manual sources) + needsCoach

**Files:**
- Create: `coach-vox/src/tables/tableApi.ts`

- [ ] **Step 1: Implement**

```ts
// src/tables/tableApi.ts
import { collection, doc, setDoc, updateDoc } from 'firebase/firestore'
import { db } from '../firebase'
import type { TableState, TableSource } from '../types'

export async function createManualTable(
  sessionId: string,
  playerId: string,
  playerName: string,
  opponentName: string,
  createdBy: string,
  source: Extract<TableSource, 'player_manual' | 'coach_manual'>,
): Promise<TableState> {
  const table: TableState = {
    id: doc(collection(db, 'tables')).id,
    sessionId,
    playerId,
    playerName,
    opponentName,
    myScore: 0,
    oppScore: 0,
    round: 1,
    phase: '',
    roundStartedAt: Date.now(),
    needsCoach: false,
    source,
    updatedBy: createdBy,
    updatedAt: Date.now(),
    liveViewUrl: null,
  }
  await setDoc(doc(db, 'tables', table.id), table)
  return table
}

export interface TableUpdate {
  myScore?: number
  oppScore?: number
  round?: number
  phase?: string
  resetRoundClock?: boolean
}

export async function updateTable(
  tableId: string,
  update: TableUpdate,
  updatedBy: string,
): Promise<void> {
  const { resetRoundClock, ...fields } = update
  await updateDoc(doc(db, 'tables', tableId), {
    ...fields,
    ...(resetRoundClock ? { roundStartedAt: Date.now() } : {}),
    updatedBy,
    updatedAt: Date.now(),
  })
}

export async function setNeedsCoach(tableId: string, needsCoach: boolean, updatedBy: string): Promise<void> {
  await updateDoc(doc(db, 'tables', tableId), { needsCoach, updatedBy, updatedAt: Date.now() })
}
```

Thin Firestore wrapper, no branching logic to unit test beyond what's already covered by `rhythm.ts`'s consumption of `roundStartedAt`.

- [ ] **Step 2: Commit**

```bash
git add src/tables/tableApi.ts
git commit -m "feat: manual table CRUD and needsCoach toggle"
```

---

### Task 11: Live tables hook + dashboard grid

**Files:**
- Create: `coach-vox/src/tables/useLiveTables.ts`
- Create: `coach-vox/src/tables/TableCard.tsx`
- Create: `coach-vox/src/dashboard/Dashboard.tsx`
- Test: `coach-vox/src/tables/TableCard.test.tsx`

- [ ] **Step 1: Write the live hook (no test — thin onSnapshot wrapper)**

```ts
// src/tables/useLiveTables.ts
import { useEffect, useState } from 'react'
import { collection, onSnapshot, query, where } from 'firebase/firestore'
import { db } from '../firebase'
import type { TableState } from '../types'

export function useLiveTables(sessionId: string | null): TableState[] {
  const [tables, setTables] = useState<TableState[]>([])

  useEffect(() => {
    if (!sessionId) {
      setTables([])
      return
    }
    const q = query(collection(db, 'tables'), where('sessionId', '==', sessionId))
    return onSnapshot(q, (snap) => {
      setTables(snap.docs.map((d) => d.data() as TableState))
    })
  }, [sessionId])

  return tables
}
```

- [ ] **Step 2: Write the failing test for the card**

```tsx
// src/tables/TableCard.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TableCard } from './TableCard'
import type { TableState } from '../types'
import type { RhythmInfo } from './rhythm'

const baseTable: TableState = {
  id: 't1',
  sessionId: 's1',
  playerId: 'p1',
  playerName: 'Alice',
  opponentName: 'Bruno',
  myScore: 32,
  oppScore: 18,
  round: 4,
  phase: 'Tir',
  roundStartedAt: 0,
  needsCoach: false,
  source: 'player_manual',
  updatedBy: 'p1',
  updatedAt: 0,
  liveViewUrl: null,
}

const rhythm: RhythmInfo = { elapsedMs: 0, ratioToAverage: 1, isLate: false }

describe('TableCard', () => {
  it('shows the players, score and round', () => {
    render(<TableCard table={baseTable} rhythm={rhythm} onClick={() => {}} />)

    expect(screen.getByText(/alice/i)).toBeInTheDocument()
    expect(screen.getByText(/bruno/i)).toBeInTheDocument()
    expect(screen.getByText('32 – 18')).toBeInTheDocument()
    expect(screen.getByText(/round 4/i)).toBeInTheDocument()
  })

  it('shows a late indicator when rhythm.isLate is true', () => {
    render(<TableCard table={baseTable} rhythm={{ ...rhythm, isLate: true }} onClick={() => {}} />)
    expect(screen.getByText(/en retard/i)).toBeInTheDocument()
  })

  it('shows a coach-call indicator when needsCoach is true', () => {
    render(<TableCard table={{ ...baseTable, needsCoach: true }} rhythm={rhythm} onClick={() => {}} />)
    expect(screen.getByText(/appel coach/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- TableCard`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the card**

```tsx
// src/tables/TableCard.tsx
import type { TableState } from '../types'
import type { RhythmInfo } from './rhythm'

interface TableCardProps {
  table: TableState
  rhythm: RhythmInfo
  onClick: () => void
}

export function TableCard({ table, rhythm, onClick }: TableCardProps) {
  return (
    <button
      onClick={onClick}
      className={`table-card${rhythm.isLate ? ' table-card--late' : ''}`}
    >
      <div className="table-card__label">Table — {table.playerName} vs {table.opponentName}</div>
      <div className="table-card__score">{table.myScore} – {table.oppScore}</div>
      <div className="table-card__meta">Round {table.round} · {table.phase}</div>
      <div className="table-card__source">{table.source === 'auto' ? 'auto' : 'manuel'}</div>
      {rhythm.isLate && <div className="table-card__warn">⚠ en retard</div>}
      {table.needsCoach && <div className="table-card__call">📣 appel coach</div>}
    </button>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- TableCard`
Expected: PASS (3 tests)

- [ ] **Step 6: Implement the dashboard grid**

```tsx
// src/dashboard/Dashboard.tsx
import { useState } from 'react'
import { useLiveTables } from '../tables/useLiveTables'
import { computeRhythm } from '../tables/rhythm'
import { TableCard } from '../tables/TableCard'
import { ZoomView } from '../tables/ZoomView'
import { EditTableModal } from '../tables/EditTableModal'
import type { TableState } from '../types'

interface DashboardProps {
  sessionId: string | null
}

export function Dashboard({ sessionId }: DashboardProps) {
  const tables = useLiveTables(sessionId)
  const rhythm = computeRhythm(tables, Date.now())
  const [selected, setSelected] = useState<TableState | null>(null)

  return (
    <div className="dashboard-grid">
      {tables.map((table) => (
        <TableCard
          key={table.id}
          table={table}
          rhythm={rhythm.get(table.id)!}
          onClick={() => setSelected(table)}
        />
      ))}

      {selected && selected.source === 'auto' && (
        <ZoomView table={selected} onClose={() => setSelected(null)} />
      )}
      {selected && selected.source !== 'auto' && (
        <EditTableModal table={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
```

- [ ] **Step 7: Commit**

```bash
git add src/tables/useLiveTables.ts src/tables/TableCard.tsx src/tables/TableCard.test.tsx src/dashboard/Dashboard.tsx
git commit -m "feat: live dashboard grid with rhythm bar and coach-call indicator"
```

---

### Task 12: Coach inline edit modal

**Files:**
- Create: `coach-vox/src/tables/EditTableModal.tsx`
- Test: `coach-vox/src/tables/EditTableModal.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/tables/EditTableModal.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditTableModal } from './EditTableModal'
import type { TableState } from '../types'

const table: TableState = {
  id: 't1',
  sessionId: 's1',
  playerId: 'p1',
  playerName: 'Alice',
  opponentName: 'Bruno',
  myScore: 10,
  oppScore: 5,
  round: 2,
  phase: 'Mouvement',
  roundStartedAt: 0,
  needsCoach: false,
  source: 'coach_manual',
  updatedBy: 'coach1',
  updatedAt: 0,
  liveViewUrl: null,
}

describe('EditTableModal', () => {
  it('submits the edited score and round', async () => {
    const onSave = vi.fn()
    render(<EditTableModal table={table} onClose={vi.fn()} onSave={onSave} />)

    const myScore = screen.getByLabelText(/score — alice/i)
    await userEvent.clear(myScore)
    await userEvent.type(myScore, '15')

    await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))

    expect(onSave).toHaveBeenCalledWith('t1', expect.objectContaining({ myScore: 15 }))
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- EditTableModal`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
// src/tables/EditTableModal.tsx
import { useState } from 'react'
import type { TableState } from '../types'
import type { TableUpdate } from './tableApi'

interface EditTableModalProps {
  table: TableState
  onClose: () => void
  onSave: (tableId: string, update: TableUpdate) => void
}

export function EditTableModal({ table, onClose, onSave }: EditTableModalProps) {
  const [myScore, setMyScore] = useState(table.myScore)
  const [oppScore, setOppScore] = useState(table.oppScore)
  const [round, setRound] = useState(table.round)
  const [phase, setPhase] = useState(table.phase)

  function handleSave() {
    onSave(table.id, { myScore, oppScore, round, phase })
    onClose()
  }

  return (
    <div className="modal" role="dialog">
      <label htmlFor="my-score">Score — {table.playerName}</label>
      <input
        id="my-score"
        type="number"
        value={myScore}
        onChange={(e) => setMyScore(Number(e.target.value))}
      />

      <label htmlFor="opp-score">Score — {table.opponentName}</label>
      <input
        id="opp-score"
        type="number"
        value={oppScore}
        onChange={(e) => setOppScore(Number(e.target.value))}
      />

      <label htmlFor="round">Round</label>
      <input id="round" type="number" value={round} onChange={(e) => setRound(Number(e.target.value))} />

      <label htmlFor="phase">Phase</label>
      <input id="phase" value={phase} onChange={(e) => setPhase(e.target.value)} />

      <button onClick={handleSave}>Enregistrer</button>
      <button onClick={onClose}>Annuler</button>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- EditTableModal`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tables/EditTableModal.tsx src/tables/EditTableModal.test.tsx
git commit -m "feat: coach inline edit modal for manual tables"
```

---

### Task 13: Player mobile form

**Files:**
- Create: `coach-vox/src/tables/PlayerTableForm.tsx`
- Test: `coach-vox/src/tables/PlayerTableForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/tables/PlayerTableForm.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PlayerTableForm } from './PlayerTableForm'

describe('PlayerTableForm', () => {
  it('reports needing the coach', async () => {
    const onCallCoach = vi.fn()
    render(
      <PlayerTableForm
        myScore={0}
        oppScore={0}
        round={1}
        phase=""
        needsCoach={false}
        onUpdate={vi.fn()}
        onCallCoach={onCallCoach}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /appeler le coach/i }))
    expect(onCallCoach).toHaveBeenCalledWith(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- PlayerTableForm`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
// src/tables/PlayerTableForm.tsx
import { useState } from 'react'
import type { TableUpdate } from './tableApi'

interface PlayerTableFormProps {
  myScore: number
  oppScore: number
  round: number
  phase: string
  needsCoach: boolean
  onUpdate: (update: TableUpdate) => void
  onCallCoach: (needsCoach: boolean) => void
}

export function PlayerTableForm({
  myScore,
  oppScore,
  round,
  phase,
  needsCoach,
  onUpdate,
  onCallCoach,
}: PlayerTableFormProps) {
  const [local, setLocal] = useState({ myScore, oppScore, round, phase })

  return (
    <div className="player-form">
      <label htmlFor="player-my-score">Mon score</label>
      <input
        id="player-my-score"
        type="number"
        value={local.myScore}
        onChange={(e) => setLocal({ ...local, myScore: Number(e.target.value) })}
      />

      <label htmlFor="player-opp-score">Score adverse</label>
      <input
        id="player-opp-score"
        type="number"
        value={local.oppScore}
        onChange={(e) => setLocal({ ...local, oppScore: Number(e.target.value) })}
      />

      <label htmlFor="player-round">Round</label>
      <input
        id="player-round"
        type="number"
        value={local.round}
        onChange={(e) => setLocal({ ...local, round: Number(e.target.value) })}
      />

      <label htmlFor="player-phase">Phase</label>
      <input
        id="player-phase"
        value={local.phase}
        onChange={(e) => setLocal({ ...local, phase: e.target.value })}
      />

      <button onClick={() => onUpdate({ ...local, resetRoundClock: local.round !== round || local.phase !== phase })}>
        Mettre à jour
      </button>

      <button onClick={() => onCallCoach(!needsCoach)}>
        {needsCoach ? 'Annuler l\u2019appel' : 'Appeler le coach'}
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- PlayerTableForm`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tables/PlayerTableForm.tsx src/tables/PlayerTableForm.test.tsx
git commit -m "feat: player mobile update form"
```

---

### Task 14: Debrief aggregation (pure logic) + screen

**Files:**
- Create: `coach-vox/src/debrief/computeDebrief.ts`
- Create: `coach-vox/src/debrief/DebriefScreen.tsx`
- Test: `coach-vox/src/debrief/computeDebrief.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/debrief/computeDebrief.test.ts
import { describe, it, expect } from 'vitest'
import { computeDebrief } from './computeDebrief'
import type { TableState } from '../types'

function table(overrides: Partial<TableState>): TableState {
  return {
    id: overrides.id ?? 't',
    sessionId: 's1',
    playerId: overrides.id ?? 't',
    playerName: overrides.playerName ?? 'Player',
    opponentName: 'Opp',
    myScore: 0,
    oppScore: 0,
    round: 5,
    phase: 'Fin',
    roundStartedAt: 0,
    needsCoach: false,
    source: 'player_manual',
    updatedBy: 'u',
    updatedAt: 0,
    liveViewUrl: null,
    ...overrides,
  }
}

describe('computeDebrief', () => {
  it('ranks outcomes and finds the biggest score gap and longest table', () => {
    const tables = [
      table({ id: 't1', playerName: 'Alice', myScore: 32, oppScore: 28 }), // gap 4
      table({ id: 't2', playerName: 'Bruno', myScore: 10, oppScore: 35 }), // gap 25 — biggest
      table({ id: 't3', playerName: 'Chloé', myScore: 20, oppScore: 20 }), // gap 0, draw
    ]
    // t2 took the longest: roundStartedAt is 0 for all, so vary updatedAt - roundStartedAt instead.
    tables[0].roundStartedAt = 0
    tables[0].updatedAt = 10_000
    tables[1].roundStartedAt = 0
    tables[1].updatedAt = 40_000
    tables[2].roundStartedAt = 0
    tables[2].updatedAt = 5_000

    const debrief = computeDebrief(tables)

    expect(debrief.wins).toBe(1)
    expect(debrief.losses).toBe(1)
    expect(debrief.draws).toBe(1)
    expect(debrief.biggestGap?.tableId).toBe('t2')
    expect(debrief.longestTable?.tableId).toBe('t2')
  })

  it('handles an empty session without crashing', () => {
    const debrief = computeDebrief([])
    expect(debrief.wins).toBe(0)
    expect(debrief.biggestGap).toBeNull()
    expect(debrief.longestTable).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- computeDebrief`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// src/debrief/computeDebrief.ts
import type { TableState } from '../types'

export interface DebriefResult {
  wins: number
  losses: number
  draws: number
  biggestGap: { tableId: string; gap: number } | null
  longestTable: { tableId: string; durationMs: number } | null
}

export function computeDebrief(tables: TableState[]): DebriefResult {
  let wins = 0
  let losses = 0
  let draws = 0
  let biggestGap: { tableId: string; gap: number } | null = null
  let longestTable: { tableId: string; durationMs: number } | null = null

  for (const t of tables) {
    if (t.myScore > t.oppScore) wins++
    else if (t.myScore < t.oppScore) losses++
    else draws++

    const gap = Math.abs(t.myScore - t.oppScore)
    if (!biggestGap || gap > biggestGap.gap) {
      biggestGap = { tableId: t.id, gap }
    }

    const durationMs = t.updatedAt - t.roundStartedAt
    if (!longestTable || durationMs > longestTable.durationMs) {
      longestTable = { tableId: t.id, durationMs }
    }
  }

  return { wins, losses, draws, biggestGap, longestTable }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- computeDebrief`
Expected: PASS (2 tests)

- [ ] **Step 5: Implement the screen**

```tsx
// src/debrief/DebriefScreen.tsx
import { computeDebrief } from './computeDebrief'
import type { TableState } from '../types'

interface DebriefScreenProps {
  tables: TableState[]
}

export function DebriefScreen({ tables }: DebriefScreenProps) {
  const debrief = computeDebrief(tables)

  return (
    <div className="debrief">
      <h2>Debrief de session</h2>
      <p>{debrief.wins} victoires · {debrief.losses} défaites · {debrief.draws} nuls</p>
      {debrief.biggestGap && <p>Plus gros écart : table {debrief.biggestGap.tableId} ({debrief.biggestGap.gap} pts)</p>}
      {debrief.longestTable && (
        <p>Table la plus longue : {debrief.longestTable.tableId} ({Math.round(debrief.longestTable.durationMs / 60000)} min)</p>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add src/debrief/computeDebrief.ts src/debrief/computeDebrief.test.ts src/debrief/DebriefScreen.tsx
git commit -m "feat: session debrief aggregation and screen"
```

---

### Task 15: Auto-capture payload validation + zoom view

**Files:**
- Create: `coach-vox/src/tables/validateAutoPayload.ts`
- Create: `coach-vox/src/tables/ZoomView.tsx`
- Test: `coach-vox/src/tables/validateAutoPayload.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// src/tables/validateAutoPayload.test.ts
import { describe, it, expect } from 'vitest'
import { validateAutoPayload } from './validateAutoPayload'

describe('validateAutoPayload', () => {
  it('accepts a well-formed auto payload', () => {
    const result = validateAutoPayload({
      myScore: 10,
      oppScore: 5,
      round: 2,
      phase: 'Tir',
      liveViewUrl: 'https://servo-skull.example/live.html?code=abc123',
    })
    expect(result.valid).toBe(true)
  })

  it('rejects a payload missing liveViewUrl', () => {
    const result = validateAutoPayload({
      myScore: 10,
      oppScore: 5,
      round: 2,
      phase: 'Tir',
    })
    expect(result.valid).toBe(false)
    expect(result.error).toMatch(/liveViewUrl/)
  })

  it('rejects a negative score', () => {
    const result = validateAutoPayload({
      myScore: -1,
      oppScore: 5,
      round: 2,
      phase: 'Tir',
      liveViewUrl: 'https://servo-skull.example/live.html?code=abc123',
    })
    expect(result.valid).toBe(false)
    expect(result.error).toMatch(/score/)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- validateAutoPayload`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// src/tables/validateAutoPayload.ts
export interface AutoPayload {
  myScore: number
  oppScore: number
  round: number
  phase: string
  liveViewUrl?: string
}

export type ValidationResult = { valid: true } | { valid: false; error: string }

export function validateAutoPayload(payload: Partial<AutoPayload>): ValidationResult {
  if (!payload.liveViewUrl) {
    return { valid: false, error: 'liveViewUrl is required for an auto-capture payload' }
  }
  if (typeof payload.myScore !== 'number' || payload.myScore < 0) {
    return { valid: false, error: 'myScore must be a non-negative number' }
  }
  if (typeof payload.oppScore !== 'number' || payload.oppScore < 0) {
    return { valid: false, error: 'oppScore must be a non-negative number' }
  }
  if (typeof payload.round !== 'number' || payload.round < 1) {
    return { valid: false, error: 'round must be a positive number' }
  }
  if (!payload.phase) {
    return { valid: false, error: 'phase is required' }
  }
  return { valid: true }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- validateAutoPayload`
Expected: PASS (3 tests)

- [ ] **Step 5: Implement the zoom view**

Per the plan's architecture note: a `source: "auto"` table carries a `liveViewUrl` set by the external capture tool, and the zoom view just embeds it — it does not render the battle map itself.

```tsx
// src/tables/ZoomView.tsx
import type { TableState } from '../types'

interface ZoomViewProps {
  table: TableState
  onClose: () => void
}

export function ZoomView({ table, onClose }: ZoomViewProps) {
  return (
    <div className="zoom-view" role="dialog">
      <button onClick={onClose}>Fermer</button>
      {table.liveViewUrl ? (
        <iframe
          title={`Plan de table — ${table.playerName} vs ${table.opponentName}`}
          src={table.liveViewUrl}
          className="zoom-view__frame"
        />
      ) : (
        <p>Pas de plan de table disponible pour cette table.</p>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add src/tables/validateAutoPayload.ts src/tables/validateAutoPayload.test.ts src/tables/ZoomView.tsx
git commit -m "feat: auto-capture payload validation and zoom view"
```

---

### Task 16: Routing + App shell

**Files:**
- Create: `coach-vox/src/App.tsx`
- Modify: `coach-vox/src/main.tsx`

- [ ] **Step 1: Install the router**

```bash
npm install react-router-dom
```

- [ ] **Step 2: Wire up routes**

```tsx
// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { InvitePage } from './team/InvitePage'
import { Dashboard } from './dashboard/Dashboard'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/join/:teamId/:token" element={<InvitePage />} />
        <Route path="/dashboard" element={<Dashboard sessionId={null} />} />
        <Route path="/" element={<Dashboard sessionId={null} />} />
      </Routes>
    </BrowserRouter>
  )
}
```

```tsx
// src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 3: Verify the app builds and starts**

Run: `npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx src/main.tsx package.json package-lock.json
git commit -m "feat: routing (invite link, dashboard)"
```

---

### Task 17: Design system CSS (Cogitator-inspired palette)

**Files:**
- Create: `coach-vox/src/styles.css`
- Modify: `coach-vox/src/main.tsx`

- [ ] **Step 1: Write the stylesheet**

Tokens taken from the validated visual direction (brainstorm) and `Cogitator/docs/UX_GUIDELINES.md` —
dark background, red reserved for danger/alerts (not amber, which stays free for a future
"adversaire" use), cyan for player info, monospace for numeric values.

```css
/* src/styles.css */
:root {
  --bg0: #080b10;
  --bg1: #0d1117;
  --bg2: #161b22;
  --cyan: #38bdf8;
  --red: #f87171;
  --green: #34d399;
  --text0: #e6edf3;
  --text1: #8b949e;
}

body {
  background: var(--bg0);
  color: var(--text0);
  font-family: 'Barlow Condensed', sans-serif;
  margin: 0;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  padding: 24px;
}

.table-card {
  background: var(--bg1);
  border: 1px solid var(--bg2);
  border-radius: 8px;
  padding: 14px;
  text-align: left;
  color: var(--text0);
  cursor: pointer;
}

.table-card--late {
  border-color: var(--red);
}

.table-card__label {
  font-size: 12px;
  color: var(--cyan);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.table-card__score {
  font-family: 'Share Tech Mono', monospace;
  font-size: 22px;
  font-weight: 700;
  margin-top: 4px;
}

.table-card__meta,
.table-card__source {
  font-size: 12px;
  color: var(--text1);
  margin-top: 2px;
}

.table-card__warn,
.table-card__call {
  font-family: 'Share Tech Mono', monospace;
  font-size: 11px;
  color: var(--red);
  margin-top: 6px;
}
```

- [ ] **Step 2: Load the Cogitator fonts and import the stylesheet**

Modify `coach-vox/index.html` — add inside `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link
  href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Share+Tech+Mono&display=swap"
  rel="stylesheet"
/>
```

Modify `coach-vox/src/main.tsx` — add the import at the top:

```tsx
import './styles.css'
```

- [ ] **Step 3: Verify the build still succeeds**

Run: `npm run build`
Expected: build succeeds (CSS has no TypeScript impact, but confirms no broken import path).

- [ ] **Step 4: Commit**

```bash
git add src/styles.css src/main.tsx index.html
git commit -m "feat: Cogitator-inspired design system CSS"
```

---

### Task 18: Deploy to Firebase Hosting

**Files:** none (deployment only)

- [ ] **Step 1: Build and deploy**

```bash
npm run build
firebase deploy --only hosting
```

Expected output: a `https://coach-vox.web.app` (or `.firebaseapp.com`) URL serving the built app.

- [ ] **Step 2: Manual smoke test**

- Sign up as a coach, create a team, copy the invite link.
- Open the invite link in a private window, sign up as a player, join.
- As the coach, open a session, create a manual table via "Édition par le coach".
- As the player, open the player form, update score/round, click "Appeler le coach" — confirm the dashboard card updates live and shows the coach-call indicator.
- Wait past the rhythm threshold on one table (or lower `LATE_THRESHOLD` temporarily) — confirm it turns red.
- Close the session — confirm the debrief screen shows wins/losses/gap/longest table.

---

## Verification (full plan)

```bash
cd "C:\Users\Megaport\Documents\Claude\Projects\coach-vox"
npm test        # all Vitest suites pass
npm run build   # TypeScript + Vite build succeeds
```

Then run the manual smoke test from Task 18, Step 2 end-to-end against the deployed app.
