# =====================================================
# BRIDGE FIX — dex-bridge.py
# =====================================================
# File: C:\Users\dexjr\dex-rag\dex-bridge.py
# Function: generate()
#
# PROBLEM:
# The bridge passes num_ctx: 16384 in the Ollama request
# options. This OVERRIDES whatever the Modelfile sets.
# v4.1 Modelfile specifies num_ctx: 8192. But the bridge
# was forcing 16K on every query, which is likely why
# Test 2 timed out — the model was processing a 16K
# attention window regardless of Modelfile settings.
#
# FIX:
# Change num_ctx from 16384 to 8192 in the generate()
# function's options dict.
#
# FIND THIS BLOCK in dex-bridge.py:
# =====================================================

# BEFORE (current):
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 16384,        # <-- OVERRIDE: forces 16K regardless of Modelfile
                },
            },

# AFTER (v4.1 aligned):
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 8192,         # <-- Matches Modelfile v4.1
                },
            },

# =====================================================
# OPTIONAL: Remove num_ctx entirely to let Modelfile own it.
# This is cleaner long-term — the Modelfile is the
# constitution, the scripts are briefings. Briefings
# shouldn't override the constitution.
#
# If removed, the Modelfile's PARAMETER num_ctx 8192
# controls context window for all bridge queries.
# =====================================================
