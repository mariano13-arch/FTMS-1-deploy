# Where these files go in your leader's project

Copy each file to the matching path under `src/` in your leader's repo:

- `layouts/AuthLayout.tsx` → `src/layouts/AuthLayout.tsx` (new folder)
- `components/common/AuthImagePanel.tsx` → `src/components/common/AuthImagePanel.tsx` (new folder)
- `components/common/CartoonTruck.tsx` → `src/components/common/CartoonTruck.tsx`
- `components/common/Logo.tsx` → `src/components/common/Logo.tsx`
- `app/LoginPage.tsx` → `src/app/LoginPage.tsx` (replaces the existing file)

All import paths already match this folder structure — no path edits needed if you
keep this layout.

## Still needed: 4 image files

`AuthImagePanel.tsx` and `Logo.tsx` expect these under `src/assets/images/`
(a new folder — doesn't exist yet in your leader's repo):

- `oxford-signage.jpg`
- `oxford-room.jpg`
- `oxford-building.jpg`
- `oxford-suites-logo.png`

Copy them from your own project's `src/assets/images/` folder (not `dist/`, which
has hashed build filenames). Until these exist, the build will fail on the missing
imports in `AuthImagePanel.tsx` and `Logo.tsx`.

## What changed in LoginPage.tsx vs. the original

Backend/logic — untouched:
- `useAuth` from `../AuthContext`, `signIn(username, password)`
- Uncontrolled `FormData`-based submit
- `mounted` / `inFlight` refs
- `history.replace(safeInternalPath(...))`, react-router v5 `useHistory`/`useLocation`

Design — now matches `Login.tsx`'s approach:
- Wrapped in `<AuthLayout>` instead of the old `login-page`/`auth-card`/`login-brand` markup
- Icon positioning via Bootstrap utility classes instead of the `login-input-icon` class
- Eye-toggle button restyled to match `Login.tsx`'s button markup

Kept different on purpose:
- Field is still `Username` (not `Email`) since `signIn` expects a username, not an email
