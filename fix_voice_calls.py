import re
import glob

# Replace submit_voice_audio(..., spoken_phrase=...) with submit_voice(..., audio_data=...)
# Or just handle the arguments.

def process_file(filepath):
    with open(filepath, 'r') as f:
        code = f.read()

    # In routes.py
    code = code.replace("submit_voice_audio(utterance, spoken_phrase=phrase)", "submit_voice(phrase=phrase, audio_data=utterance)")
    
    # In test_step6.py
    code = code.replace("submit_voice_audio(live_voice, spoken_phrase=", "submit_voice(audio_data=live_voice, phrase=")
    code = code.replace("submit_voice_audio(intruder_voice)", "submit_voice(phrase=None, audio_data=intruder_voice)")
    code = code.replace("submit_voice_audio(intruder_voice, spoken_phrase=", "submit_voice(audio_data=intruder_voice, phrase=")
    
    # In test_step7.py
    code = code.replace("submit_voice_audio(live_voice, spoken_phrase=", "submit_voice(audio_data=live_voice, phrase=")

    with open(filepath, 'w') as f:
        f.write(code)

for f in ["app/api/routes.py", "test_step6.py", "test_step7.py"]:
    process_file(f)

