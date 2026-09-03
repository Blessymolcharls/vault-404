import re

# index.html
with open("app/static/index.html", "r") as f:
    index = f.read()

# 1. Remove Phone Bio from Stepper
index = re.sub(
    r'\s*<div id="stepNodeFp" class="step-node">\s*<div class="step-circle">2</div>\s*<div class="step-label">PHONE BIO</div>\s*</div>',
    '',
    index
)
# Renumber Face
index = index.replace(
    '<div class="step-circle">3</div>\n          <div class="step-label">FACE BIOMETRICS</div>',
    '<div class="step-circle">2</div>\n          <div class="step-label">FACE BIOMETRICS</div>'
)
# Renumber Keypad
index = index.replace(
    '<div class="step-circle">4</div>\n          <div class="step-label">SECRET KEY</div>',
    '<div class="step-circle">3</div>\n          <div class="step-label">SECRET KEY</div>'
)
# Renumber Voice
index = index.replace(
    '<div class="step-circle">5</div>\n          <div class="step-label">VOICE PHRASE</div>',
    '<div class="step-circle">4</div>\n          <div class="step-label">VOICE PHRASE</div>'
)

# 2. Remove Stage 2 card
index = re.sub(
    r'\s*<!-- Stage 2: Phone Companion App Biometric -->[\s\S]*?(?=<!-- Stage 3: Facial Biometrics \(WebRTC \+ Synthetic\) -->)',
    '\n\n          ',
    index
)

# 3. Renumber Stage Cards
index = index.replace(
    '<h3>[3] Computer Vision Face Scanner</h3>',
    '<h3>[2] Computer Vision Face Scanner</h3>'
)
index = index.replace(
    '<span class="stage-badge">STAGE 3</span>',
    '<span class="stage-badge">STAGE 2</span>'
)

index = index.replace(
    '<h3>[4] Secret Password Keypad</h3>',
    '<h3>[3] Secret Password Keypad</h3>'
)
index = index.replace(
    '<span class="stage-badge">STAGE 4</span>',
    '<span class="stage-badge">STAGE 3</span>'
)

index = index.replace(
    '<h3>[5] Acoustic Voice Biometric Verifier</h3>',
    '<h3>[4] Acoustic Voice Biometric Verifier</h3>'
)
index = index.replace(
    '<span class="stage-badge">STAGE 5</span>',
    '<span class="stage-badge">STAGE 4</span>'
)
index = index.replace(
    '<div class="stage-card" style="grid-column: 1 / -1;">',
    '<div class="stage-card">'
)

with open("app/static/index.html", "w") as f:
    f.write(index)

# vault_client.js
with open("app/static/js/vault_client.js", "r") as f:
    js = f.read()

# 1. Remove DOM elements for Stage 2
js = re.sub(r'const btnScanAuthFp = document\.getElementById\("btnScanAuthFp"\);\n', '', js)
js = re.sub(r'const btnScanInvalidFp = document\.getElementById\("btnScanInvalidFp"\);\n', '', js)
js = re.sub(r'const stepNodeFp = document\.getElementById\("stepNodeFp"\);\n', '', js)

# 2. Update step nodes array
js = js.replace(
    "const allStepNodes = [stepNodeIdle, stepNodeRfid, stepNodeFp, stepNodeFace, stepNodePwd, stepNodeVoice, stepNodeUnlocked];",
    "const allStepNodes = [stepNodeIdle, stepNodeRfid, stepNodeFace, stepNodePwd, stepNodeVoice, stepNodeUnlocked];"
)

# 3. Update websocket handler
js = re.sub(r'\s*case "AWAITING_PHONE_BIOMETRIC":\s*activeNode = stepNodeFp;\s*break;', '', js)

# 4. Remove submitPhoneBiometric function and event listeners
js = re.sub(r'\s*async function submitPhoneBiometric\([\s\S]*?(?=async function startWebcam)', '\n\n', js)

js = re.sub(r'\s*if\s*\(btnScanAuthFp\)[\s\S]*?(?=if\s*\(btnStartCam\))', '\n\n  ', js)

with open("app/static/js/vault_client.js", "w") as f:
    f.write(js)

