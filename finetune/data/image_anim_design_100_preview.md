# Image Animation/Design Dataset Preview

## Pair 1: `planner_image_anim_design_062` / `refiner_image_anim_design_062`

### Planner Input (excerpt)
```text
Task: Generate a structured language edit plan for a short-form video. User Instruction: Create a clean high-retention image-caption reel. When caption text is about an image, that image must appear at that moment, and it must be removed as soon as the next caption topic starts. Do not make the video messy. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: - Start from an empty video canvas. - Use the main audio as the full timeline backbone. - Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. - Segments may be caption-focused, visual-focused, transition-focused, or mixed. - Keep captions readable at all times. - Never let visuals cover important captions. - Keep one consistent style across the full video unless a strong moment needs extra emphasis. - Highlight the currently spoken caption word. - Correct a caption word only if it is clearly wrong and the intended word is obvious from context. - Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. - Prefer showing media exactly when the related topic, object, person, or event is mentioned. - Each element may contain: - about = what the element contains or represents - aim = preferred use of the element - Prefer aim over about if both exist. Either may be empty. - If aim exists, try to satisfy it unless it strongly harms the ed
```

### Planner Output
```text
EDIT PLAN
Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.
Audio Decision: No music element is provided; caption timing map is the timeline backbone.
Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.
Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.
Background Style: morning_energy with tasteful design layers; avoid clutter.
Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.
Segment 1
Time: 0.013-7.130
Purpose: Present the image topic: A person flipping upside down
Elements Used: image_1, caption_track_1
Caption Decision: Show groups from related caption text; important word is 'person'.
Visual Decision: Keep image_1 visible only during this topic window.
Animation Decision: Apply Use bounce entrance with smooth hold; keep image only while related caption is active and remove at next topic..
Placement Decision: Caption layout=mid_lower, image around x=720, y=460, avoid overlap.
Timing Events:
- time: 0.013 event: show image_1
- time: 0.263 event: emphasize 'person'
- time: 7.130 event: hide image_1
Transition Out: Cut cleanly to next caption topic.
Engagement Note: Keep scene simple and readable, never messy.
Segment 2
Time
```

### Refiner Output (excerpt)
```json
{"version":"1.1","video":{"size":{"width":1080,"height":1920},"fps":30,"bg_color":[0,0,0],"output_path":"output/a2v_video.mp4","background_style":"morning_energy","metadata":{"design_events":[{"type":"panel","t_start":0.0,"t_end":25.561,"x":"90","y":"1460","w":"iw-180","h":"330","color":"#000000","opacity":0.16},{"type":"frame","t_start":0.0,"t_end":25.561,"color":"#8EF0D2","opacity":0.06,"thickness":10}]}},"properties_path":null,"elements":[{"element_id":"image_1","type":"image","timing":{"start":0.013,"duration":7.117},"properties":{"type":"image","source_uri":"assets/inputs/images/888425986_e4b6c12324.jpg","timing":{"start":0.013,"duration":7.117},"transform":{"x":720.0,"y":460.0}},"actions":[{"t_start":0.013,"t_end":0.463,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":460.0,"scale":1.05,"motion_ease":"bounce","round_corners":20,"fade_in_s":0.18,"fade_out_s":0.16,"crop_w":0.82,"crop_h":0.76,"crop_x":0.1,"crop_y":0.1}},{"t_start":0.463,"t_end":7.13,"op":"show","params":{"x":720.0,"y":460.0,"to_x":720.0,"to_y":442.0,"scale":1.11,"motion_ease":"smooth","round_corners":20,"fade_in_s":0.12,"fade_out_s":0.2,"crop_w":0.82,"crop_h":0.76,"crop_x":0.1,"crop_y":0.1}}]},{"element_id":"image_2","type":"image","timing":{"start":7.308,"duration":8.8},"properties":{"type":"image","source_uri":"assets/inputs/images/894928353_002a3d5f06.jpg","timing":{"start":7.308,"duration":8.8},"transform":{"x":540.0,"y":460.0}},"actions":[{"t_start":7.308,"t_end":7.758,"op":"show","params":{"from_x":540.0,"from_y":2250.0,"x":540.0,"y":460.0,"scale":1.15,"motion_ease":"smooth","roun
```

## Pair 2: `planner_image_anim_design_086` / `refiner_image_anim_design_086`

### Planner Input (excerpt)
```text
Task: Generate a structured language edit plan for a short-form video. User Instruction: Create a clean high-retention image-caption reel. When caption text is about an image, that image must appear at that moment, and it must be removed as soon as the next caption topic starts. Do not make the video messy. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: - Start from an empty video canvas. - Use the main audio as the full timeline backbone. - Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. - Segments may be caption-focused, visual-focused, transition-focused, or mixed. - Keep captions readable at all times. - Never let visuals cover important captions. - Keep one consistent style across the full video unless a strong moment needs extra emphasis. - Highlight the currently spoken caption word. - Correct a caption word only if it is clearly wrong and the intended word is obvious from context. - Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. - Prefer showing media exactly when the related topic, object, person, or event is mentioned. - Each element may contain: - about = what the element contains or represents - aim = preferred use of the element - Prefer aim over about if both exist. Either may be empty. - If aim exists, try to satisfy it unless it strongly harms the ed
```

### Planner Output
```text
EDIT PLAN
Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.
Audio Decision: No music element is provided; caption timing map is the timeline backbone.
Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.
Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.
Background Style: grain_vignette with tasteful design layers; avoid clutter.
Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.
Segment 1
Time: 0.111-7.923
Purpose: Present the image topic: A cross-country skier going through the woods.
Elements Used: image_1, caption_track_1
Caption Decision: Show groups from related caption text; important word is 'cross-country'.
Visual Decision: Keep image_1 visible only during this topic window.
Animation Decision: Apply Use bounce entrance with smooth hold; keep image only while related caption is active and remove at next topic..
Placement Decision: Caption layout=bottom_center, image around x=720, y=760, avoid overlap.
Timing Events:
- time: 0.111 event: show image_1
- time: 0.361 event: emphasize 'cross-country'
- time: 7.923 event: hide image_1
Transition Out: Cut cleanly to next caption topic.
Engagement Note: Keep scene simple and re
```

### Refiner Output (excerpt)
```json
{"version":"1.1","video":{"size":{"width":1080,"height":1920},"fps":30,"bg_color":[0,0,0],"output_path":"output/a2v_video.mp4","background_style":"grain_vignette","metadata":{"design_events":[{"type":"panel","t_start":0.0,"t_end":35.194,"x":"90","y":"1460","w":"iw-180","h":"330","color":"#f3f3f3","opacity":0.16},{"type":"frame","t_start":0.0,"t_end":35.194,"color":"#FFB07C","opacity":0.06,"thickness":10}]}},"properties_path":null,"elements":[{"element_id":"image_1","type":"image","timing":{"start":0.111,"duration":7.812},"properties":{"type":"image","source_uri":"assets/inputs/images/938162709_21443d352f.jpg","timing":{"start":0.111,"duration":7.812},"transform":{"x":720.0,"y":760.0}},"actions":[{"t_start":0.111,"t_end":0.561,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":760.0,"scale":1.25,"motion_ease":"bounce","round_corners":20,"fade_in_s":0.18,"fade_out_s":0.16,"crop_w":0.82,"crop_h":0.9,"crop_x":0.06,"crop_y":0.03}},{"t_start":0.561,"t_end":7.923,"op":"show","params":{"x":720.0,"y":760.0,"to_x":720.0,"to_y":742.0,"scale":1.31,"motion_ease":"smooth","round_corners":20,"fade_in_s":0.12,"fade_out_s":0.2,"crop_w":0.82,"crop_h":0.9,"crop_x":0.06,"crop_y":0.03}}]},{"element_id":"image_2","type":"image","timing":{"start":8.026,"duration":8.188},"properties":{"type":"image","source_uri":"assets/inputs/images/95734036_bef6d1a871.jpg","timing":{"start":8.026,"duration":8.188},"transform":{"x":720.0,"y":560.0}},"actions":[{"t_start":8.026,"t_end":8.476,"op":"show","params":{"from_x":1400.0,"from_y":560.0,"x":720.0,"y":560.0,"scale":1.6,"motion_ease":"elastic"
```

## Pair 3: `planner_image_anim_design_006` / `refiner_image_anim_design_006`

### Planner Input (excerpt)
```text
Task: Generate a structured language edit plan for a short-form video. User Instruction: Create a clean high-retention image-caption reel. When caption text is about an image, that image must appear at that moment, and it must be removed as soon as the next caption topic starts. Do not make the video messy. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: - Start from an empty video canvas. - Use the main audio as the full timeline backbone. - Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. - Segments may be caption-focused, visual-focused, transition-focused, or mixed. - Keep captions readable at all times. - Never let visuals cover important captions. - Keep one consistent style across the full video unless a strong moment needs extra emphasis. - Highlight the currently spoken caption word. - Correct a caption word only if it is clearly wrong and the intended word is obvious from context. - Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. - Prefer showing media exactly when the related topic, object, person, or event is mentioned. - Each element may contain: - about = what the element contains or represents - aim = preferred use of the element - Prefer aim over about if both exist. Either may be empty. - If aim exists, try to satisfy it unless it strongly harms the ed
```

### Planner Output
```text
EDIT PLAN
Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.
Audio Decision: No music element is provided; caption timing map is the timeline backbone.
Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.
Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.
Background Style: map_blue with tasteful design layers; avoid clutter.
Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.
Segment 1
Time: 0.107-11.998
Purpose: Present the image topic: Girls in swimsuits, holding hands and leaping into water.
Elements Used: image_1, caption_track_1
Caption Decision: Show groups from related caption text; important word is 'girls'.
Visual Decision: Keep image_1 visible only during this topic window.
Animation Decision: Apply Use stomp entrance with stable hold; keep image only while related caption is active and remove at next topic..
Placement Decision: Caption layout=mid_lower, image around x=720, y=760, avoid overlap.
Timing Events:
- time: 0.107 event: show image_1
- time: 0.357 event: emphasize 'girls'
- time: 11.998 event: hide image_1
Transition Out: Cut cleanly to next caption topic.
Engagement Note: Keep scene simple and readable, never 
```

### Refiner Output (excerpt)
```json
{"version":"1.1","video":{"size":{"width":1080,"height":1920},"fps":30,"bg_color":[0,0,0],"output_path":"output/a2v_video.mp4","background_style":"map_blue","metadata":{"design_events":[{"type":"panel","t_start":0.0,"t_end":78.131,"x":"90","y":"1460","w":"iw-180","h":"330","color":"#000000","opacity":0.16},{"type":"frame","t_start":0.0,"t_end":78.131,"color":"#FFD84D","opacity":0.06,"thickness":6},{"type":"grid","t_start":0.0,"t_end":78.131,"cell_w":180,"cell_h":180,"thickness":1,"color":"#84a8ff","opacity":0.08}]}},"properties_path":null,"elements":[{"element_id":"image_1","type":"image","timing":{"start":0.107,"duration":11.891},"properties":{"type":"image","source_uri":"assets/inputs/images/946051430_8db7e4ce09.jpg","timing":{"start":0.107,"duration":11.891},"transform":{"x":720.0,"y":760.0}},"actions":[{"t_start":0.107,"t_end":0.557,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":760.0,"scale":1.6,"motion_ease":"pop","round_corners":20,"fade_in_s":0.18,"fade_out_s":0.16}},{"t_start":0.557,"t_end":11.998,"op":"show","params":{"x":720.0,"y":760.0,"to_x":720.0,"to_y":742.0,"scale":1.6600000000000001,"motion_ease":"smooth","round_corners":20,"fade_in_s":0.12,"fade_out_s":0.2}}]},{"element_id":"image_2","type":"image","timing":{"start":12.168,"duration":12.86},"properties":{"type":"image","source_uri":"assets/inputs/images/967719295_3257695095.jpg","timing":{"start":12.168,"duration":12.86},"transform":{"x":720.0,"y":760.0}},"actions":[{"t_start":12.168,"t_end":12.618,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":760.0,"scale":1.8,"mot
```

## Pair 4: `planner_image_anim_design_003` / `refiner_image_anim_design_003`

### Planner Input (excerpt)
```text
Task: Generate a structured language edit plan for a short-form video. User Instruction: Create a clean high-retention image-caption reel. When caption text is about an image, that image must appear at that moment, and it must be removed as soon as the next caption topic starts. Do not make the video messy. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: - Start from an empty video canvas. - Use the main audio as the full timeline backbone. - Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. - Segments may be caption-focused, visual-focused, transition-focused, or mixed. - Keep captions readable at all times. - Never let visuals cover important captions. - Keep one consistent style across the full video unless a strong moment needs extra emphasis. - Highlight the currently spoken caption word. - Correct a caption word only if it is clearly wrong and the intended word is obvious from context. - Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. - Prefer showing media exactly when the related topic, object, person, or event is mentioned. - Each element may contain: - about = what the element contains or represents - aim = preferred use of the element - Prefer aim over about if both exist. Either may be empty. - If aim exists, try to satisfy it unless it strongly harms the ed
```

### Planner Output
```text
EDIT PLAN
Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.
Audio Decision: No music element is provided; caption timing map is the timeline backbone.
Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.
Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.
Background Style: neutral_dark with tasteful design layers; avoid clutter.
Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.
Segment 1
Time: 0.002-12.700
Purpose: Present the image topic: A child plays with a toy in the grass.
Elements Used: image_1, caption_track_1
Caption Decision: Show groups from related caption text; important word is 'child'.
Visual Decision: Keep image_1 visible only during this topic window.
Animation Decision: Apply Use wiggle entrance then settle; keep image only while related caption is active and remove at next topic..
Placement Decision: Caption layout=lower_right, image around x=260, y=860, avoid overlap.
Timing Events:
- time: 0.002 event: show image_1
- time: 0.252 event: emphasize 'child'
- time: 12.700 event: hide image_1
Transition Out: Cut cleanly to next caption topic.
Engagement Note: Keep scene simple and readable, never messy.
Segment 2

```

### Refiner Output (excerpt)
```json
{"version":"1.1","video":{"size":{"width":1080,"height":1920},"fps":30,"bg_color":[0,0,0],"output_path":"output/a2v_video.mp4","background_style":"neutral_dark","metadata":{"design_events":[{"type":"panel","t_start":0.0,"t_end":65.455,"x":"90","y":"1460","w":"iw-180","h":"330","color":"#111111","opacity":0.16},{"type":"frame","t_start":0.0,"t_end":65.455,"color":"#8EC5FF","opacity":0.06,"thickness":6}]}},"properties_path":null,"elements":[{"element_id":"image_1","type":"image","timing":{"start":0.002,"duration":12.698},"properties":{"type":"image","source_uri":"assets/inputs/images/964197865_0133acaeb4.jpg","timing":{"start":0.002,"duration":12.698},"transform":{"x":260.0,"y":860.0}},"actions":[{"t_start":0.002,"t_end":0.452,"op":"show","params":{"from_x":260.0,"from_y":2250.0,"x":260.0,"y":860.0,"scale":1.4,"motion_ease":"pop","round_corners":20,"fade_in_s":0.18,"fade_out_s":0.16,"crop_w":0.76,"crop_h":0.76,"crop_x":0.1,"crop_y":0.06}},{"t_start":0.452,"t_end":12.7,"op":"show","params":{"x":260.0,"y":860.0,"to_x":260.0,"to_y":842.0,"scale":1.46,"motion_ease":"smooth","round_corners":20,"fade_in_s":0.12,"fade_out_s":0.2,"crop_w":0.76,"crop_h":0.76,"crop_x":0.1,"crop_y":0.06}}]},{"element_id":"image_2","type":"image","timing":{"start":12.848,"duration":12.78},"properties":{"type":"image","source_uri":"assets/inputs/images/956164675_9ee084364e.jpg","timing":{"start":12.848,"duration":12.78},"transform":{"x":260.0,"y":760.0}},"actions":[{"t_start":12.848,"t_end":13.298,"op":"show","params":{"from_x":260.0,"from_y":2250.0,"x":260.0,"y":760.0,"scale":1.6,"motion_ease":"bounce","
```

## Pair 5: `planner_image_anim_design_068` / `refiner_image_anim_design_068`

### Planner Input (excerpt)
```text
Task: Generate a structured language edit plan for a short-form video. User Instruction: Create a clean high-retention image-caption reel. When caption text is about an image, that image must appear at that moment, and it must be removed as soon as the next caption topic starts. Do not make the video messy. Goal: Create a smooth, engaging, high-retention edit using the provided elements. Priority Order: [Audio, Caption, Image, Video, Sfx, Gif] Rules: - Start from an empty video canvas. - Use the main audio as the full timeline backbone. - Divide the video into meaningful segments using caption timing, topic changes, silence, emphasis, and pacing. - Segments may be caption-focused, visual-focused, transition-focused, or mixed. - Keep captions readable at all times. - Never let visuals cover important captions. - Keep one consistent style across the full video unless a strong moment needs extra emphasis. - Highlight the currently spoken caption word. - Correct a caption word only if it is clearly wrong and the intended word is obvious from context. - Use images, videos, gifs, SFX, and music only when they match the spoken topic or improve the edit. - Prefer showing media exactly when the related topic, object, person, or event is mentioned. - Each element may contain: - about = what the element contains or represents - aim = preferred use of the element - Prefer aim over about if both exist. Either may be empty. - If aim exists, try to satisfy it unless it strongly harms the ed
```

### Planner Output
```text
EDIT PLAN
Global Style: Clean cinematic visual storytelling with strong image-caption synchronization and non-messy layout.
Audio Decision: No music element is provided; caption timing map is the timeline backbone.
Caption Style: Group captions adaptively 1-5 words, keep text inside 9:16 safe area, highlight only important words.
Visual Style: Show each image exactly when its related caption appears and remove it before next unrelated caption starts.
Background Style: map_blue with tasteful design layers; avoid clutter.
Segmentation Rule: New segment whenever caption focus changes to a new image topic or sentence boundary.
Segment 1
Time: 0.089-7.510
Purpose: Present the image topic: a horse driven carriage running through a rainstorm.
Elements Used: image_1, caption_track_1
Caption Decision: Show groups from related caption text; important word is 'horse'.
Visual Decision: Keep image_1 visible only during this topic window.
Animation Decision: Apply Use stomp entrance with stable hold; keep image only while related caption is active and remove at next topic..
Placement Decision: Caption layout=bottom_center, image around x=720, y=560, avoid overlap.
Timing Events:
- time: 0.089 event: show image_1
- time: 0.339 event: emphasize 'horse'
- time: 7.510 event: hide image_1
Transition Out: Cut cleanly to next caption topic.
Engagement Note: Keep scene simple and readable, never mes
```

### Refiner Output (excerpt)
```json
{"version":"1.1","video":{"size":{"width":1080,"height":1920},"fps":30,"bg_color":[0,0,0],"output_path":"output/a2v_video.mp4","background_style":"map_blue","metadata":{"design_events":[{"type":"panel","t_start":0.0,"t_end":56.041,"x":"90","y":"1460","w":"iw-180","h":"330","color":"#111111","opacity":0.16},{"type":"frame","t_start":0.0,"t_end":56.041,"color":"#FFB07C","opacity":0.06,"thickness":10},{"type":"grid","t_start":0.0,"t_end":56.041,"cell_w":180,"cell_h":180,"thickness":1,"color":"#84a8ff","opacity":0.08}]}},"properties_path":null,"elements":[{"element_id":"image_1","type":"image","timing":{"start":0.089,"duration":7.421},"properties":{"type":"image","source_uri":"assets/inputs/images/97731718_eb7ba71fd3.jpg","timing":{"start":0.089,"duration":7.421},"transform":{"x":720.0,"y":560.0}},"actions":[{"t_start":0.089,"t_end":0.539,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":560.0,"scale":1.6,"motion_ease":"pop","round_corners":20,"fade_in_s":0.18,"fade_out_s":0.16}},{"t_start":0.539,"t_end":7.51,"op":"show","params":{"x":720.0,"y":560.0,"to_x":720.0,"to_y":542.0,"scale":1.6600000000000001,"motion_ease":"smooth","round_corners":20,"fade_in_s":0.12,"fade_out_s":0.2}}]},{"element_id":"image_2","type":"image","timing":{"start":7.699,"duration":8.845},"properties":{"type":"image","source_uri":"assets/inputs/images/97577988_65e2eae14a.jpg","timing":{"start":7.699,"duration":8.845},"transform":{"x":720.0,"y":560.0}},"actions":[{"t_start":7.699,"t_end":8.149,"op":"show","params":{"from_x":720.0,"from_y":2250.0,"x":720.0,"y":560.0,"scale":1.4,"motion_ease"
```
