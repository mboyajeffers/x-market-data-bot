"""
X Card Validator — AI overlap detection + auto-fix
Imported by all matplotlib card generators.

Usage (before plt.savefig):
    from card_validator import detect_and_fix_overlaps
    detect_and_fix_overlaps(fig)

Optional vision QA (post-save):
    CLAUDE_VISION_QA=1 python3 generate_finance_x_card.py
"""

import os
import subprocess
import sys
import matplotlib
import matplotlib.text


FONT_MICRO = 7          # absolute font floor (matches card_spec.py)
MAX_ITERATIONS = 5      # overlap-fix pass limit
SHRINK_FACTOR  = 0.92   # per-iteration font reduction when overlap detected


def _collect_texts(fig) -> list[matplotlib.text.Text]:
    """Gather all Text artists from figure level and all axes."""
    texts = [a for a in fig.get_children()
             if isinstance(a, matplotlib.text.Text) and a.get_text().strip()]
    for ax in fig.axes:
        texts.extend(
            t for t in ax.texts
            if isinstance(t, matplotlib.text.Text) and t.get_text().strip()
        )
        # Axis title, tick labels (skip axes where axis("off") was called — ax.axison
        # is False in that case, but individual tick Text objects still report visible=True,
        # causing false overlap reports against content text)
        if ax.title.get_text().strip():
            texts.append(ax.title)
        if ax.axison:
            texts.extend(t for t in ax.get_xticklabels() if t.get_text().strip())
            texts.extend(t for t in ax.get_yticklabels() if t.get_text().strip())
    # Deduplicate by id
    seen = set()
    unique = []
    for t in texts:
        if id(t) not in seen:
            seen.add(id(t))
            unique.append(t)
    return unique


def detect_and_fix_overlaps(fig) -> bool:
    """
    Detect overlapping text elements and iteratively shrink lower-priority
    text until no overlaps remain or FONT_MICRO is reached.

    Returns True if card is clean, False if overlap could not be resolved.
    Call this before plt.savefig().
    """
    # Force a draw so bounding boxes are populated
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    for iteration in range(MAX_ITERATIONS):
        texts = _collect_texts(fig)
        bboxes = []
        for t in texts:
            try:
                bb = t.get_window_extent(renderer=renderer)
                if bb.width > 0 and bb.height > 0:
                    bboxes.append((t, bb))
            except Exception:
                pass

        overlaps_found = False
        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                t1, b1 = bboxes[i]
                t2, b2 = bboxes[j]
                if b1.overlaps(b2):
                    overlaps_found = True
                    # Shrink whichever element has the larger current font size
                    # (prefer to shrink secondary over primary)
                    target = t2 if t2.get_fontsize() >= t1.get_fontsize() else t1
                    current = target.get_fontsize()
                    if current > FONT_MICRO:
                        adjusted = max(FONT_MICRO, current * SHRINK_FACTOR)
                        target.set_fontsize(adjusted)
                        label = target.get_text()[:40].replace("\n", " ")
                        print(f"ADJUSTED [{iteration+1}]: \"{label}\" "
                              f"fontsize {current:.1f} → {adjusted:.1f}")

        if not overlaps_found:
            if iteration > 0:
                print(f"Overlap resolved after {iteration} iteration(s).")
            return True

        # Re-draw after font changes so next iteration has fresh bboxes
        fig.canvas.draw()

    print("WARNING: overlap could not be fully resolved — inspect card before posting.")
    return False


def claude_vision_qa(png_path: str) -> tuple[bool, str]:
    """
    Post-save visual QA using Claude CLI (no API key — uses active session).
    Enable with: CLAUDE_VISION_QA=1

    Returns (passed: bool, notes: str).
    """
    if not os.path.exists(png_path):
        return False, f"PNG not found: {png_path}"

    prompt = (
        f"You are a card quality inspector. Examine this X post card image: {png_path}\n"
        "Report ONLY the following issues if present:\n"
        "1) Any text that overlaps other text\n"
        "2) Any text cut off at the image edges\n"
        "3) Any text or number too small to read at thumbnail size (under 100px wide)\n"
        "If none of these issues exist, respond with exactly: OK"
    )

    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "ANTHROPIC_API_KEY": ""}
        )
        output = result.stdout.strip()
        if output == "OK" or output.upper().startswith("OK"):
            return True, ""
        return False, output
    except FileNotFoundError:
        return True, "(claude CLI not found — skipping vision QA)"
    except subprocess.TimeoutExpired:
        return True, "(claude vision QA timed out — skipping)"
    except Exception as e:
        return True, f"(vision QA error: {e})"
