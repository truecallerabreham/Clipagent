# Beats are anchored to word ids, not timestamps

Every animation Beat references the transcript word that triggers it (`"word": "w412"`), and the engine resolves it to an output time after the cuts. Anchoring to seconds would break whenever a retake or a pause is cut, and since edits are re-rendered often, re-timing must be automatic.
