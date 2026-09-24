# Prompt guide for the current Emoji Studio model

This guide describes the selected step-25 LoRA as it exists today. It is strongest on one centered object with explicit colors and a simple silhouette. It is not a dependable general-purpose emoji model.

The service automatically appends its locked 3D-emoji style suffix. Describe the subject and its important visible parts; do not rely on abbreviations such as `hi5`.

## Best-supported prompts

These prompts come from the concept-disjoint checkpoint evaluation or the held-out quality evaluation. Start with seed `17` or `29`; those seeds have already been rendered in the checkpoint study.

```text
A ripe golden pineapple with a leafy green crown, rendered as a polished 3D emoji illustration, centered on a plain white background.

A bright red ladybug with black spots and six small legs, rendered as a polished 3D emoji illustration, centered on a plain white background.

A compact teal instant camera with a round lens and a small rainbow stripe, rendered as a polished 3D emoji illustration, centered on a plain white background.

A round blue teapot with a curved spout, top lid, and yellow handle, rendered as a polished 3D emoji illustration, centered on a plain white background.

A compact pink backpack with a rounded front pocket and yellow zipper accents, rendered as a polished 3D emoji illustration, centered on a plain white background.

An open purple umbrella with curved canopy panels and a brown hooked handle, rendered as a polished 3D emoji illustration, centered on a plain white background.

A round pink alarm clock with two yellow bells and a pale face, rendered as a polished 3D emoji illustration, centered on a plain white background.
```

## Useful demonstrations, with evaluation caveats

These subjects appeared in the 16-image training split. They should demonstrate the learned visual language, but they are not evidence of generalization.

```text
A white rocket angled toward the upper right, with a pink nose and fins, a round blue window, and an orange exhaust flame.

A yellow light bulb with a visible curved filament, a bright white highlight, and a silver screw base.

A green seedling with two leaves growing from a small rounded mound of brown soil.

A yellow-orange square gift box with a red vertical ribbon and a red bow on top.

A pale lavender cup and saucer holding a dark brown drink, viewed from above at an angle, with its handle on the right.
```

## Prompt pattern

Use this structure:

```text
A single [specific object], [primary color], with [two or three defining visible parts], centered, no text, no extra objects.
```

Prefer concrete descriptions such as “two yellow bells” or “a brown hooked handle.” Asking for one subject is substantially safer than asking for multiple subjects that touch or overlap.

## Controls

- **Starting seed** is the deterministic random starting point. The same model, prompt, settings and seed reproduce the same image. A different seed samples a different composition; it does not repair a capability the model lacks.
- **Variations** is the number of images requested. Starting seed `17` with two variations uses seeds `17` and `18`.
- Use one or two variations while evaluating. Four variations consume four quota units and four sequential GPU generations.

## Known weak or unsupported requests

- Two hands interacting: high-five, handshake, pinky promise, clapping.
- Mechanical geometry: bicycles and scooters can have malformed frames or wheels.
- Reliable lettering or meme captions.
- Crowded scenes, multiple interacting characters, or precise counting beyond simple layouts.
- Fine details such as book-page edges may disappear after style adaptation.

Rate semantic failures with **No** even when the image looks polished. Visual quality is not task success.
