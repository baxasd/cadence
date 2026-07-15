# Capture & Validation Setup Guide

**Cadence · University of Roehampton**

## Filming for good keypoints

Sports2D does not read markers off the skin, it *infers* the position of each body landmark from how the person looks in the video. Everything that makes the body clearer to a human eye makes it clearer to the model. 

**Film from the side** 
Running happens almost entirely in the side-on (sagittal) plane, and Sports2D measures angles in the flat plane of the image. The camera should look straight across the direction of travel, with the lens pointed perpendicular to the runner's path. If the camera is angled even a little off square, distances along the running direction get squashed in the image and every angle drifts by a consistent amount

![Plan view: the camera on the perpendicular to the direction of travel, with an oblique camera for contrast](figures/camera-plan.svg)

**Stand back and zoom in.** A camera placed close with a wide lens exaggerates perspective: the near leg looks bigger than the far leg, and the angle maths assumes they are the same size. Moving the camera further away and zooming in flattens this distortion and gives more trustworthy numbers

**Keep the lens level with the hips.** A camera raised up and tilted down compresses the lower body unevenly, and the legs suffer the worst of it. Level with the hips keeps the region of interest on the straightest part of the lens.

![Elevation view: a camera level with the hips versus a raised, tilted camera](figures/camera-elevation.svg)


**The middle of the frame is the most reliable part of the pass.** Lens distortion and
perspective are both worst at the edges, so the measurements to trust are the ones taken
while the runner is near the centre of the image.

**A side-on view is not symmetric.** The leg nearest the camera is larger, clearer and never hidden; the far leg is periodically blocked behind the near one and rendered at a slightly different scale. The near leg is the more reliable of the two, and the two sides should be looked at separately rather than averaged together.

![Framing: whole body in shot, near leg unoccluded, far leg periodically hidden](figures/camera-framing.svg)

**Clothing.** Close-fitting clothing measurably improves lower-limb accuracy — loose garments drape over the very joints they hide. The model is essentially finding the edges of the body.

**Speed.** Frame rate sets how finely motion is sampled in time. Separately, shutter speed controls blur: a slow shutter smears a fast-moving foot across the pixels, and the model cannot pin down a landmark that is not sharp. A fast foot can be blurry even at a high frame rate, so both settings matter.

> **One quiet failure mode worth knowing about.** Sports2D works out which way the runner is facing from the **feet**. When the feet are unclear the facing decision can flip, and that inverts the sign of every angle for those frames. Clear, sharp feet are worth the effort.

---

##  Keypoint Topology

The default model gives **22 body landmarks**. The figure below shows how they connect. The ringed points are the ones the leg angles depend on.

![Kinematic topology of the 22 Sports2D keypoints](figures/topology.svg)

For validation against Vicon, each keypoint needs a marker that means the same thing. Most line up cleanly; a few need care, and those are the ones worth briefing the mocap team on before a session.

**These line up directly** — hip centre, knee, ankle, shoulder, and the heel. Expect close agreement with no special handling.

**The hip joint has a small, expected offset.** The pose model tends to place the hip a
little toward the bony bump on the side of the thigh, whereas Vicon regresses the hip centre
from pelvis markers. A small, consistent difference here is normal, not an error.

---

## 3. How the angles are computed

Every angle Sports2D reports is built from the geometry between a few keypoints. There are two kinds, and they read differently.

### Joint angles

These describe a joint bending: one body segment measured against a neighbouring one. They are arranged so that a person standing still, upright, reads **0°**, and the numbers grow as the joint moves away from that neutral pose.

| Knee flexion | Ankle dorsiflexion |
|---|---|
| ![Knee flexion](figures/angle-knee.svg) | ![Ankle dorsiflexion](figures/angle-ankle.svg) |
| The bend at the knee itself — thigh against shank, measured right at the joint. | The shank against the foot. |

| Hip flexion | Shoulder flexion |
|---|---|
| ![Hip flexion](figures/angle-hip.svg) | ![Shoulder flexion](figures/angle-shoulder.svg) |
| The thigh measured **against the trunk line**, not against vertical. | The arm measured **against the same trunk line**. |

**The hip and shoulder are measured against the trunk** 
The hip is the thigh compared to the *trunk line* and the shoulder is the arm compared to that same line. So if the runner leans their torso forward without moving their thigh at all, the reported hip angle still changes; it follows the lean almost exactly. Every runner leans forward, and the lean grows with speed and fatigue, so the Sports2D hip angle is really a blend of true hip motion and trunk lean.

### Segment angles

The other kind is simpler: the orientation of a single body part measured against the horizontal. The **trunk** is the clearest example.

![Trunk segment angle: orientation of the pelvis-to-neck line, measured from horizontal](figures/angle-trunk.svg)

These do **not** read 0° when the body is upright. Because they are measured up from the horizontal, a part standing vertically reads **+90°** (or −90° pointing down), and a part lying flat and forward reads 0°. So a trunk held upright shows about +90°, and forward lean pulls it below that. The same convention applies to the thigh, shank, foot, pelvis and head segments.