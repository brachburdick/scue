# Bug Log — Frontend

Append-only log of bugs found and fixed in the frontend (React/TS/Vite/Tailwind).
Record every fix, no matter how small — patterns emerge over time.

**Format:**
```
### Short title
Date: YYYY-MM-DD
Milestone: FE-X (or N/A)
Symptom: What did the user see or what broke?
Root cause: Why did it happen?
Fix: What was changed and where?
File(s): path/to/file.tsx
```

---

### HTML entity strings rendered as literal text in sort indicators
Date: 2026-03-16
Milestone: FE-3
Symptom: The "Analyzed" column header displayed the raw string `&#X25BC;` instead of a ▼ symbol. Clicking toggled it to `&#X25B2;` instead of ▲. Other unsorted columns showed `&#x21C5;` as literal text on page reload.
Root cause: The `SortIndicator` component used HTML entity strings (`"&#x25B2;"`) as JSX text content. React renders string literals as-is — it does not interpret HTML entities inside `{}` expressions. Only entities written directly in JSX markup (outside `{}`) are parsed by the JSX compiler.
Fix: Replaced HTML entity strings with actual Unicode characters: `"⇅"`, `"▲"`, `"▼"`.
File(s): frontend/src/components/tracks/TrackTable.tsx
