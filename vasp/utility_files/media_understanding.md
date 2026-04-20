# Basic Knowledge
1. Each media item is represented as an `ELEMENT` with its own properties.
2. Elements are divided into several types, and each type has its own allowed properties and behavior.

# Caption Track
1. This element represents the caption track of the whole video.
2. It is the transcript divided into groups and synced with audio to appear at the correct time interval.
3. Captions should always be visible and placed where viewers can read them easily.
4. Caption color, size, and font should always prioritize readability.
5. If no visual media is present on screen, captions can be placed in the center instead of the bottom.
6. This element contains a `time_mapping` property that defines exactly which caption group appears at which time. This helps map related media to the same timing window.

# Image
1. It represents an image with a specific context.
2. An image should be placed where the captions or spoken content refer to that context.
3. It contains an `about` property that describes what the image represents and helps identify where it should appear in the timeline.
4. It can be resized based on usage, especially when multiple visuals are shown together.
5. The image should never be cropped incorrectly or placed outside screen bounds.
6. If no other visual media is present, the image can take the middle one-third of the screen, with captions in the lower third.
7. It may contain an optional `aim` property that describes preferred usage.

# Audio
1. It represents the main speech track, background music, or short sound effects.
2. Audio is timeline-based and has no screen position, so it should never use x, y, or size.
3. Main speech audio is the backbone of timing; caption timing should follow this audio.
4. Background music should stay low under speech, and should not reduce caption readability pacing.
5. SFX should be used only at important words, transitions, or impact moments.
6. If multiple audio elements exist, their role should be clear: speech, music, or sfx.
7. It may include an optional `aim` property to guide intended usage (for example: extract speech captions, background bed, impact hit).

# Sticker
1. It represents a small visual accent (emoji/icon/character sticker) used to increase engagement.
2. Sticker should appear only when context matches caption emotion or keyword.
3. Sticker should be short in duration and should not stay on screen for the whole segment.
4. Sticker should not overlap important caption words and should avoid blocking key visuals.
5. Sticker can use quick playful animations (pop, bounce, slide) but should remain readable with captions.
6. Sticker size should be moderate and always inside canvas bounds.
7. It may include optional `about` and `aim` properties to guide meaning and placement style.

# GIF
1. It represents a short looping animated visual for humor, reaction, emphasis, or context support.
2. GIF should be shown where spoken context or caption meaning matches its about/aim.
3. GIF should not run full timeline by default; use short windows around relevant caption groups.
4. GIF placement should preserve caption readability and avoid covering lower safe caption zone.
5. GIF may be full-screen only when it is the main visual of a segment; otherwise use side/top placement.
6. GIF should remain inside canvas and should not be stretched unnaturally.
7. It may include an optional `aim` property for preferred usage (reaction, transition accent, comic emphasis, etc.).

# No Audio Video Clips
1. It represents visual motion footage without usable speech audio for caption extraction.
2. These clips are used as background or foreground visuals aligned with transcript meaning, not as a caption timing source.
3. A clip should appear when caption context matches its `about` or `aim`.
4. Clip transitions should be smooth (fade/cut/slide/zoom) and should avoid abrupt empty frames.
5. If used as background, captions should remain clearly readable in the safe zone.
6. If used as foreground, size and placement should avoid covering critical caption words.
7. A no-audio clip can be trimmed for exact timing and must remain inside canvas bounds.
