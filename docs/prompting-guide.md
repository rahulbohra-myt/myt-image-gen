# Prompting Guide

Reference checklist for writing `--prompt` text that generates confidently and
on-brand on the first try — fewer clarifying questions from the refiner, less
ambiguity for the image model to guess at. Written from a creative-director
lens: name things explicitly rather than leaving them for the model to infer.

## 1. Medium — always state this first, explicitly
The single biggest source of confused output is an unstated medium. Lead
every prompt with one of:
- `photorealistic photograph` / `documentary-style photo` / `candid lifestyle photography`
- `flat vector illustration` / `flat design, vector art`
- `isometric illustration`
- `line art` / `hand-drawn sketch`
- `3D render` / `claymation style`
- `infographic layout` (then specify panel count — see #7)

Don't say "yoga pose image" — say "photorealistic lifestyle photograph of...".
The model shouldn't have to infer medium from context.

## 2. Composition & framing
- Shot type: `close-up`, `medium shot`, `full-body shot`, `wide establishing shot`
- Camera angle: `eye-level`, `three-quarter view`, `overhead/top-down view`, `low angle`
- `centered composition` / `rule of thirds` / `negative space on the left for text overlay`
- State aspect ratio in the prompt text too, even though it's also passed via
  `--aspect-ratio` — redundancy here measurably helps: `square 1:1 composition`
  / `vertical 9:16 composition`

## 3. Lighting (photorealistic only — skip for vector/flat)
- `natural window light`, `soft diffused daylight`, `golden hour lighting`,
  `studio softbox lighting`, `backlit with rim light`
- Vague lighting is a top cause of flat, AI-generic-looking photos. Always
  name one.

## 4. Camera/lens realism cues (photorealistic only)
These push the model away from the "airbrushed AI" look:
- `shot on a 50mm lens`, `shallow depth of field`, `soft bokeh background`,
  `sharp focus on subject`, `natural skin texture`, `unretouched, realistic skin`

## 5. Color control
- Reference actual hex codes when brand color matters:
  `mat in #06A778`, `accent wall in #EE731B` — the model follows hex codes
  more reliably than color names like "teal" or "orange"
- State dominance explicitly: `orange as a small accent only, not a dominant
  fill` — matches the brand-guide.md color policy; restate it per-prompt too,
  not just rely on the injected guide

## 6. Subject specificity — kill ambiguity before it starts
- Exact pose name, both languages if relevant: `Bhujangasana (Cobra Pose)`
- For lesser-known poses (especially in multi-pose grids/infographics), the
  pose name alone isn't always enough — the model can render an
  anatomically inaccurate version. Spell out the key body mechanic, e.g.
  for Supta Matsyendrasana: "lying on her back, one knee bent and crossed
  over her body to the opposite side, both shoulders flat on the ground,
  arms extended in a T-shape, head turned opposite the twisted legs."
- Age/body/ethnicity explicitly per the representation policy:
  `a woman in her 50s, medium build, South Asian`
- Clothing color tied to brand palette, not left open:
  `wearing a teal athletic top`
- Setting named concretely, not left to inference: `in a sunlit home living
  room` — never leave setting blank if there's a preference, the model
  defaults to generic gym/studio

## 7. Quantity precision (critical for infographics)
State exact counts — this is where the model hesitates most:
- `exactly 4 poses in a 2x2 grid` not "a few poses"
- `one single subject, no additional figures`
- `4-panel infographic, each panel labeled`

## 8. Text-in-image control
Nano Banana Pro's text rendering is strong — lean on it, but be exact:
- Quote the literal text: `render the text "Cobra Pose" in bold sans-serif at the top`
- Specify font feel: `serif title font`, `bold sans-serif label`, `hand-lettered style`
- State placement: `title banner at top`, `caption pill below subject`

## 9. Explicit negatives — say what NOT to include
This is the one category most people skip:
- `no logos, no icons, no brand marks — plain text only` (see the
  fabricated-logo finding in decisions.md, 2026-07-10)
- `no watermark, no signature`
- `no stock-photo clichés (no beach sunsets, no mountain-peak poses)`
- `no unsafe or contortion-level poses`

## 10. Reference image usage instructions
When passing reference images, say what to take from them — the model won't
guess correctly on its own:
- `match the pose accuracy of the reference image, but use your own color palette`
  (relevant for `yoga-excercises-infographics`, where color/style shouldn't be copied)
- `use the reference image only for layout/composition, not color`

---

## Applying this by campaign type

- **`individual-yoga-poses`** (photorealistic lifestyle): medium + lighting +
  camera/lens + subject specificity + hex-code color accents + setting
- **`yoga-excercises-infographics`** (flat/vector composite): medium + exact
  panel count + text rendering + explicit "no logo" + reference-usage
  instructions (pose accuracy only, not style)
