#!/bin/bash
# Build the final demo video: burn in captions.srt, then mix in SFX at
# specific timestamps. No voice-over — captions only, per the decision to
# drop TTS in favor of ffmpeg-only captions + SFX.
#
# USAGE:
#   1. Put your raw screen recording in this folder (or edit RAW_VIDEO below
#      to point at it wherever it lives).
#   2. Put your SFX files in this folder (or edit their paths below).
#   3. Edit the SFX_TIMESTAMPS section to match where you actually want each
#      sound to hit — defaults below are guesses based on the BLOCKED moments
#      in the script (scenario 2 dedup block ~0:36, scenario 3 oversized
#      block ~0:39, scenario 4 loop first-block ~0:44, scenario 5 breaker
#      trip ~0:56, scenario 6 kill switch ~1:00). Adjust to match your
#      actual recording exactly.
#   4. chmod +x build_video.sh && ./build_video.sh

set -e  # stop on first error, don't silently produce a broken video

RAW_VIDEO="recording.mp4"          # <-- change to your actual filename
CAPTIONS="captions.srt"
OUTPUT_CAPTIONED="step1_captioned.mp4"
OUTPUT_FINAL="final_video.mp4"

# --- Step 1: burn in captions ---
# force_style tweaks: FontSize and PrimaryColour (white=&HFFFFFF&) are safe
# defaults; adjust if captions are hard to read against your background.
ffmpeg -i "$RAW_VIDEO" \
  -vf "subtitles=${CAPTIONS}:force_style='FontSize=22,PrimaryColour=&HFFFFFF&,BorderStyle=3,BackColour=&H80000000&'" \
  -c:a copy \
  -y "$OUTPUT_CAPTIONED"

echo "Step 1 done: captions burned into $OUTPUT_CAPTIONED"

# --- Step 2: mix in SFX at specific timestamps ---
# Each SFX file gets an `adelay` (in milliseconds, same value for both
# stereo channels) so it starts at the right moment, then all SFX tracks
# plus the original video audio get mixed together with amix.
#
# EDIT THESE to match your actual SFX filenames and real timestamps:
SFX_DEDUP="sfx_block.mp3"        # plays when scenario 2's duplicate is blocked
SFX_DEDUP_MS=36000                # 0:36 in milliseconds

SFX_OVERSIZED="sfx_block.mp3"     # scenario 3 oversized order blocked
SFX_OVERSIZED_MS=39000

SFX_LOOP="sfx_block.mp3"          # scenario 4, first loop order blocked
SFX_LOOP_MS=44000

SFX_BREAKER="sfx_alert.mp3"       # scenario 5 breaker trips
SFX_BREAKER_MS=56000

SFX_KILLSWITCH="sfx_alert.mp3"    # scenario 6 kill switch engaged
SFX_KILLSWITCH_MS=60000

ffmpeg -i "$OUTPUT_CAPTIONED" \
  -i "$SFX_DEDUP" -i "$SFX_OVERSIZED" -i "$SFX_LOOP" -i "$SFX_BREAKER" -i "$SFX_KILLSWITCH" \
  -filter_complex "
    [1]adelay=${SFX_DEDUP_MS}|${SFX_DEDUP_MS}[a1];
    [2]adelay=${SFX_OVERSIZED_MS}|${SFX_OVERSIZED_MS}[a2];
    [3]adelay=${SFX_LOOP_MS}|${SFX_LOOP_MS}[a3];
    [4]adelay=${SFX_BREAKER_MS}|${SFX_BREAKER_MS}[a4];
    [5]adelay=${SFX_KILLSWITCH_MS}|${SFX_KILLSWITCH_MS}[a5];
    [0:a][a1][a2][a3][a4][a5]amix=inputs=6:duration=first:dropout_transition=0[aout]
  " \
  -map 0:v -map "[aout]" \
  -c:v copy -c:a aac \
  -y "$OUTPUT_FINAL"

echo "Step 2 done: final video with captions + SFX is $OUTPUT_FINAL"
