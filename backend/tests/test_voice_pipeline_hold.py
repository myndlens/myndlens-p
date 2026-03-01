"""Test voice pipeline HOLD command, router logic, and state machine.

Tests for:
- router.py: 'myndlens hold' / 'mind lens hold' / 'mindlens wait' → HOLD command
- router.py: bare 'hold' / 'wait' / 'pause' / 'hold on' should NOT trigger HOLD (must be intent_fragment)
- router.py: 'cancel' / 'stop' / 'kill' still work as commands
- router.py: noise words ('um', 'uh', 'hmm') still detected as noise
- ws_messages.py: TTSAudioPayload has skip_chat field
- ws_server.py: _process_fragment sends 'held' status when HOLD detected
- ws_server.py: _process_fragment sends TTS when checklist_progress >= 85 (intent_ready)
- state-machine.ts: HOLDING state exists with valid transitions
"""
import pytest
import asyncio
import sys
import os

# Add backend to path for imports
sys.path.insert(0, '/app/myndlens-git/backend')

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio(loop_scope="function")


# Helper function to run async code
def run_async(coro):
    """Run async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# MODULE: router.py - Route Fragment tests
# ============================================================================

class TestRouterHoldCommand:
    """Test HOLD command routing - requires 'myndlens' prefix to avoid false positives."""

    def test_myndlens_hold_triggers_hold(self):
        """'myndlens hold' should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "myndlens hold"))
        assert result.route == "command", f"Expected 'command', got '{result.route}'"
        assert result.normalized_command == "HOLD", f"Expected 'HOLD', got '{result.normalized_command}'"
        print("PASS: 'myndlens hold' → HOLD command")

    def test_mind_lens_hold_triggers_hold(self):
        """'mind lens hold' (STT transcription variant) should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "mind lens hold"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'mind lens hold' → HOLD command")

    def test_mindlens_wait_triggers_hold(self):
        """'mindlens wait' should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "mindlens wait"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'mindlens wait' → HOLD command")

    def test_myndlens_pause_triggers_hold(self):
        """'myndlens pause' should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "myndlens pause"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'myndlens pause' → HOLD command")

    def test_mynd_lens_hold_triggers_hold(self):
        """'mynd lens hold' (another STT variant) should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "mynd lens hold"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'mynd lens hold' → HOLD command")

    def test_mind_lens_wait_triggers_hold(self):
        """'mind lens wait' should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "mind lens wait"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'mind lens wait' → HOLD command")

    def test_mindlens_pause_triggers_hold(self):
        """'mindlens pause' should route to HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "mindlens pause"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'mindlens pause' → HOLD command")


class TestRouterBareHoldNotCommand:
    """Test that bare 'hold' / 'wait' / 'pause' does NOT trigger HOLD command.
    
    Without 'myndlens' prefix, these should be treated as intent_fragment
    to avoid false positives like 'wait for the bus'.
    """

    def test_bare_hold_not_command(self):
        """'hold' alone should NOT be a HOLD command (could be 'hold the package')."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "hold"))
        # Bare 'hold' should NOT trigger HOLD command - it should be intent_fragment or noise
        assert not (result.route == "command" and result.normalized_command == "HOLD"), \
            f"Bare 'hold' should NOT trigger HOLD command. Got route={result.route}, cmd={result.normalized_command}"
        print(f"PASS: bare 'hold' → {result.route} (not HOLD command)")

    def test_bare_wait_not_command(self):
        """'wait' alone should NOT be a HOLD command (could be 'wait for me')."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "wait"))
        assert not (result.route == "command" and result.normalized_command == "HOLD"), \
            f"Bare 'wait' should NOT trigger HOLD command"
        print(f"PASS: bare 'wait' → {result.route} (not HOLD command)")

    def test_bare_pause_not_command(self):
        """'pause' alone should NOT be a HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "pause"))
        assert not (result.route == "command" and result.normalized_command == "HOLD"), \
            f"Bare 'pause' should NOT trigger HOLD command"
        print(f"PASS: bare 'pause' → {result.route} (not HOLD command)")

    def test_hold_on_not_command(self):
        """'hold on' should NOT be a HOLD command (common speech pattern)."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "hold on"))
        assert not (result.route == "command" and result.normalized_command == "HOLD"), \
            f"'hold on' should NOT trigger HOLD command"
        print(f"PASS: 'hold on' → {result.route} (not HOLD command)")

    def test_wait_for_intent_fragment(self):
        """'wait for the bus' should be intent_fragment, not command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "wait for the bus"))
        assert result.route == "intent_fragment", \
            f"'wait for the bus' should be intent_fragment, got {result.route}"
        print("PASS: 'wait for the bus' → intent_fragment")

    def test_hold_my_beer_intent_fragment(self):
        """'hold my beer' should be intent_fragment, not command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "hold my beer"))
        assert result.route == "intent_fragment", \
            f"'hold my beer' should be intent_fragment, got {result.route}"
        print("PASS: 'hold my beer' → intent_fragment")


class TestRouterCancelKillCommands:
    """Test that cancel/stop/kill commands still work."""

    def test_cancel_command(self):
        """'cancel' should route to CANCEL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "cancel"))
        assert result.route == "command"
        assert result.normalized_command == "CANCEL"
        print("PASS: 'cancel' → CANCEL command")

    def test_stop_command(self):
        """'stop' should route to CANCEL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "stop"))
        assert result.route == "command"
        assert result.normalized_command == "CANCEL"
        print("PASS: 'stop' → CANCEL command")

    def test_kill_command(self):
        """'kill' should route to KILL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "kill"))
        assert result.route == "command"
        assert result.normalized_command == "KILL"
        print("PASS: 'kill' → KILL command")

    def test_abort_command(self):
        """'abort' should route to KILL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "abort"))
        assert result.route == "command"
        assert result.normalized_command == "KILL"
        print("PASS: 'abort' → KILL command")

    def test_forget_it_command(self):
        """'forget it' should route to CANCEL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "forget it"))
        assert result.route == "command"
        assert result.normalized_command == "CANCEL"
        print("PASS: 'forget it' → CANCEL command")

    def test_never_mind_command(self):
        """'never mind' should route to CANCEL command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "never mind"))
        assert result.route == "command"
        assert result.normalized_command == "CANCEL"
        print("PASS: 'never mind' → CANCEL command")


class TestRouterNoiseDetection:
    """Test that noise words are properly detected."""

    def test_um_is_noise(self):
        """'um' should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "um"))
        assert result.route == "noise", f"Expected 'noise', got '{result.route}'"
        print("PASS: 'um' → noise")

    def test_uh_is_noise(self):
        """'uh' should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "uh"))
        assert result.route == "noise"
        print("PASS: 'uh' → noise")

    def test_hmm_is_noise(self):
        """'hmm' should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "hmm"))
        assert result.route == "noise"
        print("PASS: 'hmm' → noise")

    def test_ah_is_noise(self):
        """'ah' should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "ah"))
        assert result.route == "noise"
        print("PASS: 'ah' → noise")

    def test_ok_is_noise(self):
        """'ok' (single word) should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "ok"))
        assert result.route == "noise"
        print("PASS: 'ok' → noise")

    def test_two_word_noise(self):
        """'um uh' (two-word noise) should be detected as noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "um uh"))
        assert result.route == "noise"
        print("PASS: 'um uh' → noise")

    def test_empty_is_noise(self):
        """Empty string should be noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", ""))
        assert result.route == "noise"
        print("PASS: '' (empty) → noise")

    def test_whitespace_is_noise(self):
        """Whitespace-only should be noise."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "   "))
        assert result.route == "noise"
        print("PASS: '   ' (whitespace) → noise")


class TestRouterInterruptionPatterns:
    """Test interruption pattern detection."""

    def test_excuse_me_interruption(self):
        """'excuse me' should be detected as interruption."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "excuse me"))
        assert result.route == "interruption"
        print("PASS: 'excuse me' → interruption")

    def test_sorry_interruption(self):
        """'sorry' should be detected as interruption."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "sorry"))
        assert result.route == "interruption"
        print("PASS: 'sorry' → interruption")

    def test_wait_wait_interruption(self):
        """'wait wait' should be detected as interruption."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "wait wait"))
        assert result.route == "interruption"
        print("PASS: 'wait wait' → interruption")


class TestRouterIntentFragment:
    """Test that normal speech becomes intent_fragment."""

    def test_book_flight_is_intent(self):
        """'book a flight to london' should be intent_fragment."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "book a flight to london"))
        assert result.route == "intent_fragment"
        print("PASS: 'book a flight to london' → intent_fragment")

    def test_send_email_is_intent(self):
        """'send an email to john' should be intent_fragment."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "send an email to john"))
        assert result.route == "intent_fragment"
        print("PASS: 'send an email to john' → intent_fragment")


# ============================================================================
# MODULE: ws_messages.py - TTSAudioPayload tests
# ============================================================================

class TestTTSAudioPayloadSkipChat:
    """Test that TTSAudioPayload has skip_chat field."""

    def test_tts_payload_has_skip_chat_field(self):
        """TTSAudioPayload should have skip_chat field."""
        from schemas.ws_messages import TTSAudioPayload
        
        # Check field exists in model fields
        fields = TTSAudioPayload.model_fields
        assert 'skip_chat' in fields, f"TTSAudioPayload missing 'skip_chat' field. Fields: {list(fields.keys())}"
        print("PASS: TTSAudioPayload has 'skip_chat' field")

    def test_tts_payload_skip_chat_default_false(self):
        """TTSAudioPayload.skip_chat should default to False."""
        from schemas.ws_messages import TTSAudioPayload
        
        payload = TTSAudioPayload(text="test", session_id="sess1")
        assert payload.skip_chat == False, f"Expected skip_chat=False, got {payload.skip_chat}"
        print("PASS: TTSAudioPayload.skip_chat defaults to False")

    def test_tts_payload_skip_chat_can_be_true(self):
        """TTSAudioPayload should accept skip_chat=True."""
        from schemas.ws_messages import TTSAudioPayload
        
        payload = TTSAudioPayload(text="test", session_id="sess1", skip_chat=True)
        assert payload.skip_chat == True, f"Expected skip_chat=True, got {payload.skip_chat}"
        print("PASS: TTSAudioPayload accepts skip_chat=True")

    def test_tts_payload_serialization_includes_skip_chat(self):
        """TTSAudioPayload.model_dump() should include skip_chat."""
        from schemas.ws_messages import TTSAudioPayload
        
        payload = TTSAudioPayload(text="test", session_id="sess1", skip_chat=True)
        data = payload.model_dump()
        assert 'skip_chat' in data, f"skip_chat not in serialized data: {list(data.keys())}"
        assert data['skip_chat'] == True
        print("PASS: TTSAudioPayload serialization includes skip_chat")


# ============================================================================
# MODULE: ws_server.py - _process_fragment tests (code review / static analysis)
# ============================================================================

class TestWSServerHeldStatus:
    """Test that _process_fragment sends 'held' status when HOLD command detected.
    
    Since _process_fragment requires WebSocket context, we validate by code inspection.
    """

    def test_process_fragment_sends_held_status_code_check(self):
        """Verify _process_fragment code sends 'held' status for HOLD command."""
        ws_server_path = '/app/myndlens-git/backend/gateway/ws_server.py'
        
        with open(ws_server_path, 'r') as f:
            content = f.read()
        
        # Check that HOLD command handling exists with 'held' status
        assert 'cmd == "HOLD"' in content or "cmd == 'HOLD'" in content, \
            "_process_fragment should check for HOLD command"
        assert '"status": "held"' in content or "'status': 'held'" in content, \
            "_process_fragment should send status='held' for HOLD command"
        
        print("PASS: ws_server.py _process_fragment sends 'held' status for HOLD command")

    def test_process_fragment_has_intent_ready_logic(self):
        """Verify _process_fragment has intent_ready TTS logic for checklist >= 85%."""
        ws_server_path = '/app/myndlens-git/backend/gateway/ws_server.py'
        
        with open(ws_server_path, 'r') as f:
            content = f.read()
        
        # Check for checklist progress >= 85 threshold
        assert 'progress >= 85' in content or 'checklist_progress >= 85' in content, \
            "_process_fragment should check for checklist progress >= 85%"
        
        # Check for intent_ready_sent flag
        assert '_intent_ready_sent' in content, \
            "_process_fragment should track _intent_ready_sent to avoid duplicate TTS"
        
        # Check for TTS message about intent ready
        assert 'clear picture' in content.lower() or 'ready' in content.lower(), \
            "_process_fragment should send TTS when intent is ready"
        
        print("PASS: ws_server.py _process_fragment has intent_ready logic at >=85%")

    def test_process_fragment_tts_uses_skip_chat(self):
        """Verify intent_ready TTS uses skip_chat=True."""
        ws_server_path = '/app/myndlens-git/backend/gateway/ws_server.py'
        
        with open(ws_server_path, 'r') as f:
            content = f.read()
        
        # Find the intent_ready TTS section (around line 1228-1240 per review request)
        # Should have skip_chat=True to avoid polluting chat history
        # Look for the pattern near progress >= 85
        lines = content.split('\n')
        found_intent_ready_block = False
        found_skip_chat = False
        
        for i, line in enumerate(lines):
            if 'progress >= 85' in line:
                found_intent_ready_block = True
                # Check next 15 lines for skip_chat
                for j in range(i, min(i + 20, len(lines))):
                    if 'skip_chat=True' in lines[j] or 'skip_chat = True' in lines[j]:
                        found_skip_chat = True
                        break
                break
        
        assert found_intent_ready_block, "Could not find progress >= 85 check"
        assert found_skip_chat, "intent_ready TTS should use skip_chat=True"
        print("PASS: ws_server.py intent_ready TTS uses skip_chat=True")


# ============================================================================
# MODULE: state-machine.ts - HOLDING state validation (TypeScript code inspection)
# ============================================================================

class TestStateMachineHoldingState:
    """Test that state-machine.ts has HOLDING state with correct transitions."""

    def test_holding_state_exists_in_audio_state_type(self):
        """Verify HOLDING is defined in AudioState type."""
        ts_path = '/app/myndlens-git/frontend/src/audio/state-machine.ts'
        
        with open(ts_path, 'r') as f:
            content = f.read()
        
        # Check AudioState type includes HOLDING
        assert "'HOLDING'" in content or '"HOLDING"' in content, \
            "AudioState type should include 'HOLDING'"
        print("PASS: state-machine.ts AudioState includes HOLDING")

    def test_holding_state_has_valid_transitions(self):
        """Verify HOLDING state has transitions to CAPTURING and IDLE."""
        ts_path = '/app/myndlens-git/frontend/src/audio/state-machine.ts'
        
        with open(ts_path, 'r') as f:
            content = f.read()
        
        # Check VALID_TRANSITIONS includes HOLDING with correct targets
        # Expected: HOLDING: ['CAPTURING', 'IDLE']
        assert 'HOLDING:' in content or 'HOLDING :' in content, \
            "VALID_TRANSITIONS should have HOLDING key"
        
        # Check transitions from HOLDING
        lines = content.split('\n')
        holding_line = None
        for i, line in enumerate(lines):
            if 'HOLDING:' in line or 'HOLDING :' in line:
                holding_line = line
                # May span multiple lines, get next line too
                if i + 1 < len(lines) and '[' in line and ']' not in line:
                    holding_line += lines[i + 1]
                break
        
        assert holding_line, "Could not find HOLDING transitions"
        assert 'CAPTURING' in holding_line or "'CAPTURING'" in content[content.find('HOLDING:'):content.find('HOLDING:')+100], \
            "HOLDING should transition to CAPTURING"
        assert 'IDLE' in holding_line or "'IDLE'" in content[content.find('HOLDING:'):content.find('HOLDING:')+100], \
            "HOLDING should transition to IDLE"
        print("PASS: state-machine.ts HOLDING transitions to CAPTURING and IDLE")

    def test_capturing_can_transition_to_holding(self):
        """Verify CAPTURING state can transition to HOLDING."""
        ts_path = '/app/myndlens-git/frontend/src/audio/state-machine.ts'
        
        with open(ts_path, 'r') as f:
            content = f.read()
        
        # Find CAPTURING transitions
        lines = content.split('\n')
        capturing_section = ""
        in_capturing = False
        for line in lines:
            if 'CAPTURING:' in line or 'CAPTURING :' in line:
                in_capturing = True
            if in_capturing:
                capturing_section += line
                if ']' in line:
                    break
        
        assert 'HOLDING' in capturing_section, \
            "CAPTURING should be able to transition to HOLDING"
        print("PASS: state-machine.ts CAPTURING can transition to HOLDING")

    def test_accumulating_can_transition_to_holding(self):
        """Verify ACCUMULATING state can transition to HOLDING."""
        ts_path = '/app/myndlens-git/frontend/src/audio/state-machine.ts'
        
        with open(ts_path, 'r') as f:
            content = f.read()
        
        # Find ACCUMULATING transitions
        lines = content.split('\n')
        accumulating_section = ""
        in_accumulating = False
        for line in lines:
            if 'ACCUMULATING:' in line or 'ACCUMULATING :' in line:
                in_accumulating = True
            if in_accumulating:
                accumulating_section += line
                if ']' in line:
                    break
        
        assert 'HOLDING' in accumulating_section, \
            "ACCUMULATING should be able to transition to HOLDING"
        print("PASS: state-machine.ts ACCUMULATING can transition to HOLDING")


# ============================================================================
# MODULE: router.py - _COMMANDS dict validation
# ============================================================================

class TestRouterCommandsDict:
    """Verify _COMMANDS dict structure in router.py."""

    def test_commands_dict_has_myndlens_hold_variants(self):
        """_COMMANDS should have all myndlens HOLD variants."""
        router_path = '/app/myndlens-git/backend/intent/router.py'
        
        with open(router_path, 'r') as f:
            content = f.read()
        
        # Check all required HOLD variants exist
        hold_variants = [
            "myndlens hold",
            "myndlens wait", 
            "myndlens pause",
            "mind lens hold",
            "mind lens wait",
            "mind lens pause",
            "mindlens hold",
            "mindlens wait",
            "mindlens pause",
            "mynd lens hold",
            "mynd lens wait",
            "mynd lens pause",
        ]
        
        missing = []
        for variant in hold_variants:
            if f'"{variant}"' not in content and f"'{variant}'" not in content:
                missing.append(variant)
        
        assert not missing, f"_COMMANDS missing HOLD variants: {missing}"
        print(f"PASS: _COMMANDS has all {len(hold_variants)} myndlens HOLD variants")

    def test_commands_dict_no_bare_hold(self):
        """_COMMANDS should NOT have bare 'hold', 'wait', 'pause' as commands."""
        router_path = '/app/myndlens-git/backend/intent/router.py'
        
        with open(router_path, 'r') as f:
            content = f.read()
        
        # Extract _COMMANDS section
        start = content.find('_COMMANDS = {')
        end = content.find('}', start) + 1
        commands_section = content[start:end]
        
        # Check that bare words are NOT keys in _COMMANDS
        # They should only appear as parts of longer phrases
        lines = commands_section.split('\n')
        for line in lines:
            if ':' in line and '"HOLD"' in line:
                # Get the key (phrase before the colon)
                key_part = line.split(':')[0].strip().strip('"').strip("'").strip(',')
                assert 'myndlens' in key_part.lower() or 'mind lens' in key_part.lower() or 'mindlens' in key_part.lower() or 'mynd lens' in key_part.lower(), \
                    f"HOLD command '{key_part}' should have myndlens prefix"
        
        print("PASS: _COMMANDS has no bare hold/wait/pause for HOLD")


# ============================================================================
# INTEGRATION: Full route_fragment behavior test
# ============================================================================

class TestRouteFragmentIntegration:
    """Integration tests for complete route_fragment behavior."""

    def test_case_insensitivity(self):
        """Commands should be case-insensitive."""
        from intent.router import route_fragment
        
        # Test uppercase
        result1 = asyncio.run(route_fragment("sess1", "user1", "MYNDLENS HOLD"))
        assert result1.route == "command" and result1.normalized_command == "HOLD"
        
        # Test mixed case
        result2 = asyncio.run(route_fragment("sess1", "user1", "MyndLens Hold"))
        assert result2.route == "command" and result2.normalized_command == "HOLD"
        
        print("PASS: route_fragment is case-insensitive")

    def test_hold_with_trailing_text(self):
        """'myndlens hold please' should still trigger HOLD."""
        from intent.router import route_fragment
        
        result = asyncio.run(route_fragment("sess1", "user1", "myndlens hold please"))
        assert result.route == "command"
        assert result.normalized_command == "HOLD"
        print("PASS: 'myndlens hold please' → HOLD command")

    def test_route_decision_fields(self):
        """RouteDecision should have all required fields."""
        from intent.router import route_fragment, RouteDecision
        
        result = asyncio.run(route_fragment("sess1", "user1", "book a flight"))
        
        assert hasattr(result, 'route')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'normalized_command')
        assert hasattr(result, 'sub_intents')
        assert hasattr(result, 'dimensions')
        
        print("PASS: RouteDecision has all required fields")


# ============================================================================
# EXTRA: Verify no false positives for common speech with "hold/wait/pause"
# ============================================================================

class TestRouterFalsePositivePrevention:
    """Test that natural speech with hold/wait/pause words doesn't trigger HOLD."""

    def test_please_hold_not_command(self):
        """'please hold' should not trigger HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "please hold"))
        assert not (result.route == "command" and result.normalized_command == "HOLD")
        print(f"PASS: 'please hold' → {result.route}")

    def test_wait_a_minute_not_command(self):
        """'wait a minute' should not trigger HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "wait a minute"))
        assert not (result.route == "command" and result.normalized_command == "HOLD")
        print(f"PASS: 'wait a minute' → {result.route}")

    def test_hold_the_door_not_command(self):
        """'hold the door' should not trigger HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "hold the door"))
        assert not (result.route == "command" and result.normalized_command == "HOLD")
        print(f"PASS: 'hold the door' → {result.route}")

    def test_pause_the_video_not_command(self):
        """'pause the video' should not trigger HOLD command."""
        from intent.router import route_fragment
        result = asyncio.run(route_fragment("sess1", "user1", "pause the video"))
        assert not (result.route == "command" and result.normalized_command == "HOLD")
        print(f"PASS: 'pause the video' → {result.route}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
