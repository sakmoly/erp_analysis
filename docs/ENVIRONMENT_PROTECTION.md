# Environment Protection — Do Not Touch Live Users

This document supplements `Cursor_Backend_MultiTenant_ERP_Analysis_Upgrade.md` §3.

**Access Profile is for mobile app users only.** It does not control ERPNext Desk login or operations for users without a profile.

## Hard rules (mandatory for every phase)

1. **Do not modify existing Access Profile records** unless an administrator explicitly requests a specific change.
2. **Do not modify Frappe User, Role, Role Profile, or User Permission records.**
3. **Do not run patches that auto-update all Access Profiles** (for example `sync_access_profiles()` adding lines to every enabled profile) without explicit approval.
4. **Do not run `bench migrate` on a production site** until the same patch set passes on staging.
5. **Do not bulk-assign** Mobile App Profile or change territories/companies for existing users.
6. **No-op rule:** if a user has **no** Access Profile, all code paths must behave exactly as they do today (no new restrictions from `erp_analysis`).
7. **Additive-only migrations:** new DocTypes and fixtures may be created; existing Desk users and non-profile mobile flows must not change by default.
8. **OAuth client name** (`Printechs Mobile`) must not be renamed until the mobile app is updated.

## Who is affected by Access Profile

| User type | Access Profile used? | Desk login affected? |
|-----------|----------------------|----------------------|
| Mobile app user with Access Profile | Yes — API scope/modules | No |
| ERPNext Desk user without Access Profile | No | No |
| Guest | No (blocked from sensitive APIs) | N/A |

## Patches that modify live data — review before migrate

| Patch | Risk |
|-------|------|
| `sync_mobile_access_registry` | Adds API lines to **every** enabled Access Profile |
| `enable_all_phase3_modules` | Toggles Mobile App Settings module flags |
| `sync_warehouse_desk_dn_permissions` | Changes Custom DocPerm for warehouse roles |

New patches must **not** follow these patterns without an explicit opt-in flag.

## Phase J migration (Printechs default profile)

- Create a **new** `PRINTECHS-B2B` Mobile App Profile fixture if needed.
- **Do not** reassign or rewrite the two existing Access Profiles automatically.
- **Do not** link the new profile to users unless done manually in Desk.

## Deployment checklist

- [ ] Work on feature branch; record `git rev-parse HEAD` before changes.
- [ ] Code-only phases (e.g. Phase A security) need **no** `bench migrate`.
- [ ] Staging migrate + smoke test before production.
- [ ] Confirm Desk login with a user **without** an Access Profile.
- [ ] Confirm mobile OAuth login still works for existing profile users.

## Phase A baseline (feature branch)

- Branch: `feature/multi-tenant-mobile-platform`
- Base commit: `6148f76541a22e4eb71a020dea5f9d36981b6510`
- **No** `bench migrate` required for Phase A (code-only security hardening).
