# Command-center sound assets

These WAV files are original short electronic cues generated specifically for
this project by `scripts/generate_command_center_sounds.py`. They do not copy
music, dialogue, logos, or warning sounds from any film, animation, game, or
other copyrighted production.

- format: mono PCM, 16-bit, 22050 Hz
- playback: transition-driven through `pc/sound_manager.py`
- automated/offscreen validation: playback suppressed
- playback failure: fail-soft; robot control and GUI continue
- regeneration: run the generator with the project Python environment

