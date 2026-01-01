# Parsing Debug & Monitoring Guide

## Overview

The Cline Telegram Bot now includes comprehensive **character-level diffing** and **output parsing insights** to help debug and understand how subprocess output is being processed and filtered.

This debugging tooling is specifically designed to track:
- What input comes from the subprocess
- What filtering rules are applied
- What final output is sent to the user
- Visual character-level differences at each stage

## Quick Start

### Enable Parsing Debug Mode

Run the bot with the `PARSING_DEBUG` environment variable set to enable detailed parsing output:

```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py
```

### What You'll See

When parsing debug mode is enabled, you'll see output like this in the terminal:

```
╔════════════════════════════════════════════════════════════════════════════╗
║ PARSING DEBUG #1    | 13:50:32.145   CMD: /start                          ║
╚════════════════════════════════════════════════════════════════════════════╝

📥 RAW OUTPUT (156 chars):
   Preview: '╭─────────────────────────────╮\ncline cli preview\n╰─────────────────╯'
   '╭─────────────────────────────╮'
   'cline cli preview'
   '╰─────────────────────────────╯'

📤 FINAL OUTPUT (0 chars):
   Preview: ''

🔍 CHARACTER-LEVEL DIFF:
   ──────────────────────────────────────────────────────────────────────────
   - '╭─────────────────────────────╮'
   - 'cline cli preview'
   - '╰─────────────────────────────╯'
   ──────────────────────────────────────────────────────────────────────────

📊 ANALYSIS:
   Characters removed: 156 (100.0%)
   Output queue size: 0
   Filters matched:
      ✓ is_ui_heavy

```

## Understanding the Output

### Section 1: Header
```
╔════════════════════════════════════════════════════════════════════════════╗
║ PARSING DEBUG #1    | 13:50:32.145   CMD: /start                          ║
╚════════════════════════════════════════════════════════════════════════════╝
```
- **#1** - Sequential number of parsed outputs
- **13:50:32.145** - Timestamp (milliseconds)
- **CMD: /start** - The command that triggered this output (if applicable)

### Section 2: Raw Output
```
📥 RAW OUTPUT (156 chars):
   Preview: '...'
```
- Shows the output **BEFORE** any filtering
- Displays character count
- Shows a preview (first 80 chars)
- Full lines shown if ≤5 lines

### Section 3: Final Output
```
📤 FINAL OUTPUT (0 chars):
   Preview: ''
```
- Shows the output **AFTER** all filtering
- Shows what actually gets queued for Telegram
- Character count shows how much remains

### Section 4: Character-Level Diff
```
🔍 CHARACTER-LEVEL DIFF:
   - 'removed line here'
   + 'added line here'
   ? 'changed line'
```
- **`-`** (red) = Content that was **removed** by filters
- **`+`** (green) = Content that was **added** (rare)
- **`?`** (yellow) = Highlighted changes
- Shows first 10 diff lines to avoid spam

### Section 5: Analysis
```
📊 ANALYSIS:
   Characters removed: 156 (100.0%)
   Output queue size: 0
   Filters matched:
      ✓ is_ui_heavy
      ✓ is_box_char
      ✓ is_command_echo
```
- **Characters removed** - How many chars the filters removed
- **Output queue size** - Current output queue at time of processing
- **Filters matched** - Which specific rules triggered

## Pass-Through Mode

When output passes through **without any filtering**, you'll see:

```
╔════════════════════════════════════════════════════════════════════════════╗
║ PARSING PASS-THROUGH #23 | 13:51:05.234   CMD: ls -la                     ║
╚════════════════════════════════════════════════════════════════════════════╝

✅ NO FILTERING APPLIED:
   247 chars passed through unchanged
   Preview: 'total 48\ndrwxr-xr-x  5 user  staff   160 Jan  1 13:00 .\n'
```

This indicates the output was **useful** and **not filtered out**.

## Filter Types

The bot uses several types of filters:

| Filter            | Purpose                                   | Examples                                 |
| ----------------- | ----------------------------------------- | ---------------------------------------- |
| `is_ui_heavy`     | Removes UI box characters and decorations | `╭`, `╰`, `│`, `┃`                       |
| `is_box_char`     | Single box drawing characters             | `╭`, `╰`                                 |
| `is_box_line`     | Lines made entirely of box characters     | `─────`                                  |
| `is_api_metadata` | API usage stats (tokens, cost, timing)    | `Tokens:...`, `Cost:...`                 |
| `is_command_echo` | Echo of the command that was sent         | User types `ls` → bot receives `ls` back |

## Debugging Workflow

### Step 1: Enable Debug Mode
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py
```

### Step 2: Send a Command via Telegram
Send any command through Telegram, e.g., `/start` or `ls -la`

### Step 3: Watch Terminal Output
Watch the terminal where the bot is running to see the parsing diffs

### Step 4: Analyze the Output
- **Is output being filtered when it shouldn't?** → Filters are too aggressive
- **Is output passing through with UI clutter?** → Filters need tuning
- **Can't see which rule fired?** → Check the "Filters matched" section

## Common Debugging Scenarios

### Scenario 1: User Sees No Output
**Problem**: Command sent but user receives nothing

**Debugging Steps**:
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py
```
1. Send the command via Telegram
2. Look for the diff output in terminal
3. Check the **FINAL OUTPUT** section - is it empty?
4. Look at **Filters matched** - was it filtered out?

**Common Causes**:
- Output was all UI elements → check `is_ui_heavy`
- Output was command echo → check `is_command_echo`
- Output was API metadata → check `is_api_metadata`

### Scenario 2: User Sees Garbled/Incomplete Output
**Problem**: Output is truncated or malformed

**Debugging Steps**:
1. Look at RAW OUTPUT vs FINAL OUTPUT
2. Are important lines being removed?
3. Check which filter matched
4. You may need to adjust filter logic in `_process_output()`

### Scenario 3: Prompt Not Detected
**Problem**: Bot doesn't recognize interactive prompts

**Debugging Steps**:
1. Enable debug mode
2. Send a command that triggers a prompt
3. Look for "Interactive prompt detected" in the diffs
4. If not detected, the prompt pattern may need adjustment

## Advanced: Tweaking Filters

All filter logic is in the `_process_output()` method in `cline_telegram_bot.py`:

```python
# Lines 410-460: Filter detection logic
ui_score = sum(1 for indicator in ui_indicators if indicator in clean_output)
is_ui_heavy = ui_score >= 2 and not is_welcome_screen

# Lines 470-475: Filter matching collection
filters_matched = []
if is_ui_heavy:
    filters_matched.append("is_ui_heavy")
```

### To Make Filters Less Aggressive:
Increase thresholds:
```python
is_ui_heavy = ui_score >= 3  # Was >= 2 (stricter now)
```

### To Make Filters More Aggressive:
Add new patterns:
```python
api_patterns = [
    r'## API request completed',
    r'↑.*↓.*\$',
    r'YOUR_NEW_PATTERN_HERE',  # Add this
]
```

## Performance Considerations

**When Debug Mode is DISABLED** (`PARSING_DEBUG` not set or `0`):
- No performance overhead
- No terminal output is generated
- Tracer calls are instant no-ops

**When Debug Mode is ENABLED**:
- Minimal overhead (mostly just printing)
- Terminal output can be voluminous with high-frequency commands
- You can suppress output by redirecting stderr/stdout if needed

## Integration with Existing Logging

The parsing debug output is **separate** from the existing `debug_log()` system:
- `debug_log()` → Goes to stdout with timestamps
- `ParsingDiffTracer` → Goes to stdout with visual formatting
- Both can be combined in logs

Example combined log capture:
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py 2>&1 | tee full_debug.log
```

## Disabling Debug Mode

To disable, either:
1. Don't set `PARSING_DEBUG` environment variable
2. Set it to `0`:
   ```bash
   PARSING_DEBUG=0 python3 cline_telegram_bot.py
   ```
3. Or simply run normally:
   ```bash
   python3 cline_telegram_bot.py
   ```

## Tips & Tricks

### Tip 1: Filter Output by Command
Look for specific commands in the output:
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py | grep "CMD: ls"
```

### Tip 2: Save Debug Session
Capture everything to a file:
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py > debug_session.log 2>&1
```
Then analyze the log file afterward.

### Tip 3: Watch in Real-Time
Use `tail -f` to watch live output:
```bash
# Terminal 1: Start the bot
PARSING_DEBUG=1 python3 cline_telegram_bot.py

# Terminal 2: Watch output
tail -f /var/log/your_log_file
```

### Tip 4: Analyze Filter Effectiveness
Count how often each filter fires:
```bash
grep "Filters matched:" debug_session.log | sort | uniq -c
```

## Troubleshooting

### Q: No debug output appears
**A**: Make sure `PARSING_DEBUG=1` is set BEFORE the script name:
```bash
PARSING_DEBUG=1 python3 cline_telegram_bot.py  # ✅ Correct
python3 cline_telegram_bot.py PARSING_DEBUG=1  # ❌ Wrong
```

### Q: Output is very verbose
**A**: This is expected! The tracer logs every output chunk. You can:
- Filter to specific commands: `grep "CMD: ls"`
- Send fewer commands during debug session
- Use grep to find problems: `grep "Filters matched" debug.log`

### Q: Terminal colors look wrong
**A**: The tracer uses ANSI color codes. If your terminal doesn't support them:
- Try piping through `cat`: `... | cat` (usually helps)
- Use `TERM=xterm-256color` environment variable
- Redirect to a file and view in an editor that supports ANSI codes

## Examples

### Example 1: Debugging a Command That Returns No Output

```bash
# Start bot with debug enabled
$ PARSING_DEBUG=1 python3 cline_telegram_bot.py

# (In another terminal, send via Telegram: "echo hello")
# In bot terminal, see:

╔════════════════════════════════════════════════════════════════════════════╗
║ PARSING DEBUG #5    | 13:52:10.234   CMD: echo hello                     ║
╚════════════════════════════════════════════════════════════════════════════╝

📥 RAW OUTPUT (45 chars):
   Preview: 'hello\n'
   'hello'
   ''

📤 FINAL OUTPUT (5 chars):
   Preview: 'hello'
   'hello'

🔍 CHARACTER-LEVEL DIFF:
   ──────────────────────────────────────────────────────────────────────────
   (no changes)
   ──────────────────────────────────────────────────────────────────────────

📊 ANALYSIS:
   Characters removed: 0 (0.0%)
   Output queue size: 1
```

✅ Good! Output passed through unchanged and is queued.

### Example 2: Debugging Over-Aggressive Filtering

```
╔════════════════════════════════════════════════════════════════════════════╗
║ PARSING DEBUG #12   | 13:53:45.123   CMD: git status                     ║
╚════════════════════════════════════════════════════════════════════════════╝

📥 RAW OUTPUT (234 chars):
   Preview: 'On branch main\nYour branch is up to date...'

📤 FINAL OUTPUT (0 chars):
   Preview: ''

📊 ANALYSIS:
   Characters removed: 234 (100.0%)
   Filters matched:
      ✓ is_api_metadata
```

⚠️ Problem! `git status` output was filtered as API metadata. Need to fix filter.

---

For more information, see the main README.md and BOT_MANAGEMENT.md files.
