# HarborLens UI prototype (SPEC-006 design input)

**State:** static prototype with fictional example data. It is **not** an implementation of FR-017 or FR-018. It reads no AIS file, calls no API and validates nothing. NOT FOR NAVIGATION.

`HarborLensPrototype.jsx` is one React function component (default export). It uses React hooks, Tailwind CSS utility classes, `lucide-react` icons and Recharts. User-facing copy is Brazilian Portuguese (pt-BR) by product decision. Code and comments are in English.

## Linked requirements

| ID | How the prototype reflects it |
| --- | --- |
| FR-018 (Proposed) | Reference map mock-up with a UTC clock, a timeline, a hatched data gap and the not-for-navigation banner. Design input only. |
| NFR-001 | A fixed banner on every tab: "Somente para pesquisa histórica — não use para navegação (NOT FOR NAVIGATION). As paradas mostradas não são atracações, fundeios ou escalas confirmadas." |
| NFR-016 | WCAG 2.2 AA target: visible `focus-visible` rings, shape + colour + label for every state, token contrast shown in the "Guia visual" tab, `prefers-reduced-motion` turns off the selected-marker pulse and the transitions. The map triangle is light violet `#c4b5fd`, at least 3:1 against the map land and water. |
| NFR-020 | Detected, censored and unknown stop boundaries have separate shapes, colours and labels. |
| BR-001 | A stop is shown as "Parada detectada" with the "Não validada" badge (tooltip "Ainda sem confirmação independente"). |
| BR-007, BR-019 | The data gap is never filled. Stops at a window edge or next to the gap show a duration lower bound ("≥") and are stacked separately in the duration histogram. |
| BR-008 | The MMSI tooltip says the number does not guarantee permanent vessel identity. |
| BR-012 | Record counts show the received total and every exclusion. |
| BR-016 | Vessel ids are synthetic, unassigned MID 199 (`199000101`–`199000112`). |

## Tabs

1. **Visão geral**: analysis header, four KPIs, stops in progress per hour (gap hatched), duration histogram, sortable stop table that opens the stop detail.
2. **Mapa histórico**: illustrative dark SVG map of the Houston Ship Channel and Galveston Bay, circle / diamond / triangle markers, glass UTC clock, timeline with a draggable scrubber, synced filterable stop list and legend.
3. **Detalhe da parada**: stop picker, summary, the method v0.2 criterion card, mini-map of the track and the position cluster, speed over ground chart, provenance and CSV / GeoJSON / JSON export of the example stop.
4. **Origem e qualidade**: "Uso dos dados em revisão" banner, record counts, quality checklist (Aprovado / Atenção / Falha), collapsed "Detalhes técnicos" with the README command `harborlens --input tests/fixtures/synthetic_ais.csv --out results` and a copy button. The page says the prototype numbers are illustrative and are not that command's output.
5. **Guia visual**: colour tokens for both themes with contrast ratios, Inter type hierarchy, 8px spacing, components, focus-ring demo and the term glossary.

## Acceptance tests

`tests/test_ui_prototype_copy.py` reads the source text and checks the banner, the forbidden words outside the negated banner, the unvalidated badge and tooltip, the MID 199 ids, reduced-motion handling, the map triangle contrast, and that the command matches the README.

```bash
python -m unittest tests.test_ui_prototype_copy -v
```

Manual evidence for this change (headless Chromium, 1440 px and 390 px wide): all five tabs render with no console error; no horizontal page scroll at 390 px; the copy button writes the command to the clipboard and shows "Copiado!"; the JSON export starts a download; clicking a map marker selects the matching list card; the "Não validada" tooltip appears on hover; with reduced motion the pulse element and the tab transition are absent.

## Previewing

Drop the file into any React 18 project with Tailwind CSS 3, `recharts` 2 and `lucide-react` installed, and render the default export. The Tailwind `content` glob must include this file. The Inter font loads from Google Fonts at runtime.

## Non-goals

No live data, live vessel tracking, navigation use, facility assignment, validation claim, or redistribution of licensed AIS.
