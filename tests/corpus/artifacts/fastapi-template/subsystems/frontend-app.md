# frontend-app — routes, components, forms

**Covers:** `frontend/src/routes/**/*.tsx`, `frontend/src/components/**/*.tsx`, `frontend/src/hooks/**/*.ts`, `frontend/src/lib/**/*.ts`, `frontend/src/main.tsx`, `frontend/src/utils.ts`, `frontend/src/routeTree.gen.ts`, `frontend/src/vite-env.d.ts`
**Tier:** ui
**Service:** frontend
**Connects:** frontend-client via import

## Purpose

What a user sees. File-based routing over TanStack Router, Chakra UI components, and the forms that call
the generated SDK.

## Topology and components

Routing is by file path under `routes/`: `login.tsx`, `signup.tsx`, `recover-password.tsx` and
`reset-password.tsx` are public; everything under `_layout/` sits behind the authenticated shell
(`_layout.tsx`), including `items.tsx`, `settings.tsx` and `admin.tsx`. The leading underscore is
TanStack's pathless-layout convention, so `_layout/items.tsx` serves `/items` rather than
`/_layout/items`.

## Key abstractions

**Authentication state lives in one hook.** `hooks/useAuth.ts` owns login, logout and the current user;
route components consume it rather than reading tokens themselves.

**No component constructs a URL.** Every backend call goes through the generated SDK, so a route rename in
the backend produces a compile error here after regeneration rather than a 404 at runtime. That property
is the whole reason `frontend-client` exists as its own subsystem.

## State and tiering

Server state through TanStack Query, auth state in `useAuth`. Nothing persists beyond the token in
browser storage.

## Invariants

- APP-001 (proposed) — a component must not call `fetch` directly; all backend access goes through the
  generated client. True at `0.9.0`.
