"""Verification script to check capsule geometry before PDF output."""
import sys
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class CapsuleCheck:
    """Result of checking one capsule."""
    word: str
    cells: List[Tuple[int, int]]
    capsule_length: float
    capsule_width: float
    capsule_cx: float
    capsule_cy: float
    capsule_angle: float
    word_length: float
    end_pad: float
    side_pad: float
    font_size: float
    cell_size: float
    errors: List[str]
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def check_capsule_geometry(
    word: str,
    cells: List[Tuple[int, int]],
    grid_cell_size: float,
    grid_font_size: float,
    end_pad: float,
    side_pad: float,
    letter_centers: dict,  # {(row, col): (x, y)}
) -> CapsuleCheck:
    """Check if capsule geometry is correct for a word."""
    errors = []
    
    if len(cells) < 2:
        return CapsuleCheck(
            word=word, cells=cells,
            capsule_length=0, capsule_width=0,
            capsule_cx=0, capsule_cy=0, capsule_angle=0,
            word_length=0, end_pad=end_pad, side_pad=side_pad,
            font_size=grid_font_size, cell_size=grid_cell_size,
            errors=["Word must have at least 2 cells"]
        )
    
    # Get first and last letter positions
    first_cell = cells[0]
    last_cell = cells[-1]
    
    x1, y1 = letter_centers.get(first_cell, (0, 0))
    x2, y2 = letter_centers.get(last_cell, (0, 0))
    
    # Calculate center
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    
    # Calculate word length
    dx = x2 - x1
    dy = y2 - y1
    word_length = math.sqrt(dx * dx + dy * dy)
    
    # Calculate capsule dimensions
    capsule_length = word_length + end_pad * 2
    capsule_width = grid_font_size + side_pad * 2
    
    # Calculate angle
    if abs(dx) < 0.001:
        angle = 90.0 if dy > 0 else -90.0
    else:
        angle = math.degrees(math.atan2(dy, dx))
    
    # Check 1: First letter should be inside capsule (not touched by semicircle)
    # The semicircle extends end_pad beyond the first letter center
    # So the inner edge of semicircle is at x1 - end_pad
    inner_start = x1 - end_pad
    inner_end = x2 + end_pad
    
    # Check 2: For horizontal words, capsule should not extend beyond cell bounds
    # Check if side padding causes capsule to touch neighboring rows
    capsule_half_width = capsule_width / 2
    letter_half_height = grid_font_size / 2
    
    # Side check: capsule should fit within cell boundaries
    # The capsule edge should not extend into neighboring cells
    # For a horizontal word at row R, the capsule should stay within rows R-0.5 to R+0.5
    # This means capsule_half_width should be < cell_size / 2
    
    if capsule_width > grid_cell_size:
        # Capsule is wider than one cell - check if it's too wide
        excess = capsule_width - grid_cell_size
        if excess > side_pad * 2 * 0.5:  # More than 50% padding means too wide
            errors.append(
                f"Capsule width ({capsule_width:.1f}) too large for cell ({grid_cell_size:.1f}). "
                f"Will touch neighboring cells. Reduce side_pad."
            )
    
    # Check 3: Semicircles should not touch first/last letters
    # The semicircle extends end_pad beyond the letter center
    # The straight part starts at x1 and ends at x2
    # For the semicircle not to touch the letter, the letter edge should be inside the straight part
    
    # Letter edge is at distance (cell_size/2 - letter_size/2) from center
    # But simpler: just check if end_pad > 0
    
    if end_pad < grid_cell_size * 0.3:
        errors.append(
            f"End padding ({end_pad:.1f}) too small. "
            f"Semicircles may touch first/last letters. Increase end_pad to at least {grid_cell_size * 0.4:.1f}"
        )
    
    # Check 4: All cells should be within capsule bounds
    # After rotation, we need to check each cell's position relative to capsule
    
    # For simplicity, check the bounding box before rotation
    rows = [c[0] for c in cells]
    cols = [c[1] for c in cells]
    
    for row, col in cells:
        # Get cell bounds
        cell_left = col * grid_cell_size
        cell_right = (col + 1) * grid_cell_size
        cell_bottom = (grid_cell_size - 1 - row) * grid_cell_size
        cell_top = (grid_cell_size - row) * grid_cell_size
        
        # Capsule should cover cell center but not extend too far
        cx_cell, cy_cell = letter_centers.get((row, col), (0, 0))
        
        # Distance from capsule center in word direction
        if abs(dx) > abs(dy):  # More horizontal
            dist_from_center = abs(cx_cell - cx)
            if dist_from_center > word_length / 2 + grid_cell_size * 0.3:
                errors.append(f"Cell ({row}, {col}) may be outside capsule coverage")
        else:  # More vertical
            dist_from_center = abs(cy_cell - cy)
            if dist_from_center > word_length / 2 + grid_cell_size * 0.3:
                errors.append(f"Cell ({row}, {col}) may be outside capsule coverage")
    
    return CapsuleCheck(
        word=word,
        cells=cells,
        capsule_length=capsule_length,
        capsule_width=capsule_width,
        capsule_cx=cx,
        capsule_cy=cy,
        capsule_angle=angle,
        word_length=word_length,
        end_pad=end_pad,
        side_pad=side_pad,
        font_size=grid_font_size,
        cell_size=grid_cell_size,
        errors=errors
    )


def verify_and_fix_capsules(
    solution_table_entries: List[dict],
    grid_cell_size: float,
    grid_font_size: float,
    letter_centers: dict,
) -> Tuple[List[CapsuleCheck], bool]:
    """
    Verify all capsules and suggest fixes if needed.
    Returns (checks, all_valid).
    """
    end_pad = 12.0
    side_pad = 2.0
    
    checks = []
    all_valid = True
    
    for entry in solution_table_entries:
        word = entry.get('word', 'unknown')
        cells = entry.get('cells', [])
        
        check = check_capsule_geometry(
            word=word,
            cells=cells,
            grid_cell_size=grid_cell_size,
            grid_font_size=grid_font_size,
            end_pad=end_pad,
            side_pad=side_pad,
            letter_centers=letter_centers,
        )
        checks.append(check)
        
        if not check.is_valid:
            all_valid = False
    
    return checks, all_valid


def suggest_fixes(checks: List[CapsuleCheck]) -> dict:
    """
    Analyze failures and suggest parameter adjustments.
    Returns dict with recommended settings.
    """
    needs_more_end_pad = False
    needs_less_side_pad = False
    needs_more_side_pad = False
    
    for check in checks:
        for error in check.errors:
            if "End padding" in error or "semicircles may touch" in error:
                needs_more_end_pad = True
            if "touch neighboring cells" in error:
                needs_less_side_pad = True
    
    end_pad = 12.0
    side_pad = 2.0
    
    if needs_more_end_pad:
        end_pad = 15.0
    
    if needs_less_side_pad:
        side_pad = 1.0
    
    return {
        'CAPSULE_END_PAD': end_pad,
        'CAPSULE_SIDE_PAD': side_pad,
    }


if __name__ == '__main__':
    # Test with sample data
    print("Capsule verification module loaded successfully")
    print("Use verify_and_fix_capsules() to check capsule geometry")
