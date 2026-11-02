# Look specifications (from the product owner)

These five specifications define the production quality bar for ClipAgent's Looks. Each Look implements its spec in full.

## math-vector: Programmatic Vector & Architectural Motion Graphics (Manim style)

**Canvas & Layering:** Render on a pure black (#000000) background, or a dark semi-transparent overlay with a subtle vignette when composited over a speaker. Maintain a minimalist 2D/3D Cartesian coordinate grid in muted cyan (#29ABCA, 40% opacity) when illustrating spatial or structural concepts.

**Typography:** Use LaTeX Computer Modern serif fonts for all labels, callouts, matrices and equations.

**Color Semantics:** Assign a strict, persistent hex color to each variable or concept introduced in the transcript (e.g. Primary Input = #FFFF00 Yellow, Horizontal/Component A = #83C167 Green, Vertical/Component B = #FC6255 Coral Red, Resultant Output = #FF862F Orange/Pink). Color-match text substrings to their corresponding geometric shapes.

**Motion & Easing:** Use smooth cubic-bezier easing (smooth or ease-in-out) for all movements. Introduce new shapes and text with progressive SVG stroke-drawing (draw-on) rather than simple opacity fades. Transition between ideas with direct path interpolation (morphing text directly into diagrams or equations) rather than hard cuts.

**Dynamic Annotations:** Use animated curly braces ({ }), dashed projection lines, and real-time number counters that track moving geometric tips. Lock every drawing, scaling and morphing keyframe to the exact timestamp of the corresponding spoken keyword in the audio track.

## whiteboard-saas: Whiteboard Sketch & Annotated SaaS Explainer

**Canvas & Chapter Structure:** Use a pure white (#FFFFFF) primary background for explanations and illustrations. Insert 2-second pitch-black (#000000) chapter cards between major topics, with centered, all-caps sans-serif text with wide letter-spacing (0.3em tracking) and a slow 1.0x to 1.08x scale-up.

**Whiteboard Hand-Drawing Engine:** Convert 2D vector illustrations, diagrams and sketch text into progressive stroke-reveal animations. Attach a foreground cutout hand layer (holding a marker or pencil) locked to the leading edge of the active stroke path, followed by an angled color-fill wipe pass. Allow an alternative "hand-place" entrance, where a hand slides in from off-screen to drop an asset into place.

**Kinetic Typography & Emphasis:** Render key takeaway sentences on clean white frames in bold geometric sans-serif typography (#111111), highlighting the primary operative keyword in electric purple (#5E17EB) or semantic red/green.

**Screen Recording & UI Annotation Layer:** Automatically detect cursor actions and spoken UI references on screen recordings, and composite:
- Smooth camera zoom-ins (1.2x–1.6x) centered on the active UI region.
- Animated dashed bounding boxes ("marching ants") around highlighted panels or pricing cards.
- Hand-drawn curved dashed arrows (--->) and pulsing chevron pointers (>>>) directing attention to buttons, sliders and menus.
- Oversized vector pointer hands that trigger a scale-down click bounce (0.85x scale) synchronized with mouse clicks.
- Floating dark pill badges (#1E1E1E background, white text) with bi-directional arrows labeling interface zones.

**Scene Transitions:** Separate workflow steps and B-roll cuts with fast (0.4s) angled diagonal multi-band color wipes.

## neon-telestrator: Dark-Mode Technical Telestrator & 3D Data Storytelling

**Canvas & Brush Engine:** Use a pure black (#000000) infinite canvas. Render all diagrams, icons (neural nets, server stacks, user avatars) and handwritten labels with a pressure-sensitive, slightly textured stylus stroke (3px–5px width) and no visible hand cutout.

**Semantic Neon Ink Rules:**
- Base diagrams & text = Pure White (#FFFFFF)
- Positive metrics, price drops & money flows = Neon Green (#2ECC71)
- Price cross-outs (X), inefficiency zones (diagonal hatch fill) & attention pointers = Bright Red (#FF2A2A)
- Grouping loops, brackets & conceptual trade-offs = Neon Purple/Pink (#D946EF) and Cyan/Blue (#3B82F6)
- High-level category brackets & cross-panel connectors = Warm Yellow (#FACC15)

**Screenshot & Chart Telestration:** When displaying external benchmark charts or news graphs, either show them full-screen and draw neon pink loops, underlines and handwritten notes ("new model", "yay") directly over the image, or dock the screenshot in the lower half of the black canvas and draw live connecting arrows between the screenshot and hand-drawn graphs above it.

**3D Spatial Data Visualization Module:** For multi-variable comparisons, render a 3D dark-mode wireframe coordinate grid (#222222 grid lines, white axis labels). Animate data series as glowing colored 3D polylines with spherical/cross vertex markers. Support smooth 3D camera orbits (azimuth/elevation interpolation) and seamless transitions from 3D perspective to 2D orthographic top-down or side projections.

**Synchronized Red Pointer Callouts:** Automatically spawn a bold, solid red vector arrow (#FF2A2A) pointing at the exact (x, y) or (x, y, z) screen coordinate of any metric, axis or UI button at the exact timestamp the narrator mentions it, holding for 0.8s–1.5s before disappearing.

## architecture-flow: Dark-Mode System Architecture & Packet-Flow Explainer

**Canvas & Spatial Layout:** Use a pure black (#000000) canvas (supports 9:16 vertical or 16:9 widescreen). Anchor client devices (e.g. an interactive smartphone wireframe) in the left third, core servers/gateways in the right third, and data stores/caches in the lower-left or lower-right. Reserve the top margin for an all-caps marker-font section title, and the bottom margin for word-by-word blur-revealed hook questions.

**Node & Card Styling:** Render backend services as dark charcoal rounded cards (#161618 fill, 12px border radius) with a header icon, an uppercase marker-style title, and internal rows for key-value state or server blades. When comparing workflows, dim unused architecture nodes to 25% opacity rather than deleting them.

**Network & Packet Primitives:** Connect nodes with thin gray lines (#4B5563). Animate bulk traffic as continuous streams of 4px glowing dots traveling along the paths, and animate specific API calls/tokens as color-coded rounded pill badges (Orange #F59E0B = Session ID, Cyan #38BDF8 = Access Token/JWT, Purple #A855F7 = Refresh Token) that interpolate smoothly from the source node (x1, y1) to the destination node (x2, y2).

**State Verification & Micro-Animations:**
- Active Highlight: Wrap the currently executing server card or database row in an animated dashed bounding box (#FFFFFF for normal operations, #F43F5E red for security alerts/breaches).
- Lookup & Validation: Animate incoming token pills sliding beside stored database records with an = operator, resolving into a green circle checkmark (#22C55E) on match.
- Latency & Failure States: When the transcript mentions bottlenecks, delays or high load, tint server outlines red (#F43F5E), slow packet dot velocity by 70%, and spawn rotating circular loading spinners inside dependent service cards.
- Security & Threat Actors: Represent attacks with a neon red hooded-hacker-with-laptop icon (#F43F5E), connected by dashed red interception lines that duplicate or replay token pills.

## stickman-story: Minimalist Monochrome Stickman Storytelling & Clean UI Walkthrough

**Character & Prop Rig (Stickman Mode):** Render on a pure #FFFFFF background with uniform 5px black ink outlines (#000000) and no shading or color fill. Keep the character strictly consistent across all scenes: round head, three top hair strands, expressive cartoon eyes/mouth, and a simple tubular torso. Anchor each scene around 1–2 functional line-art props (desk, laptop, wall clock, checklist, timer).

**Localized Micro-Animation Rules:** Keep furniture and the character's base posture stationary within each shot; animate only isolated expressive layers:
- Facial & Head State: blinking eyelids, shifting pupil direction, eyebrow arches (stressed vs. confident), and subtle head nods/tilts.
- Limb Loops: forearm/finger typing loops on keyboards, thumb scrolling on phones, single-finger pointing/button pressing, and dual-arm victory raises.
- Ambient Comic Symbols: floating thought bubbles, rotating clock hands, scribble stress clouds, sweat droplets, and pop-in completion checkmarks (✓).

**Scene Pacing & Cutting:** Split voiceover into 4s–6s emotional beats (1–2 sentences per scene). Use direct hard cuts between stickman scenes, synced to sentence boundaries.

**Tutorial Screen-Recording Framing (Walkthrough Mode):** Frame 16:9 browser captures inside a rounded macOS-style window (16px radius) centered over a #000000 background canvas. Overlay a 40px translucent grey circular ripple animation at (x, y) cursor click coordinates, use smooth 1.8x pan-and-zoom keyframes on active UI text/stats, and bridge tab switches with a 0.25s radial zoom-blur transition.
