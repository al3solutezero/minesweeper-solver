from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException

# ---------------------------------------------------------------
# Board geometry (expert board: 16 rows x 30 columns).
# Cells are [row, column], counted from 1.
# ---------------------------------------------------------------
m = 16
n = 30
Top_edge = [[1, y] for y in range(1, n + 1)]
Right_edge = [[x, n] for x in range(2, m + 1)]
Bottom_edge = [[m, y] for y in range(n - 1, 0, -1)]
Left_edge = [[x, 1] for x in range(m - 1, 1, -1)]
Edges = Top_edge + Right_edge + Bottom_edge + Left_edge
Vertices = [[1, 1], [1, n], [m, n], [m, 1]]
non_edges_cell = [[i, j] for i in range(2, m) for j in range(2, n)]
whole_board = Edges + non_edges_cell

FLAG = 'square bombflagged'
BLANK = 'square blank'
FIRST_CLICK = [1, 1]

# Cells we have deduced to be mines in the current game. They are only remembered here; no flags are placed on the page.
known_mines = set()


def nbh(cell):
    """Return the cells around the given cell (8 inside, 5 on an edge, 3 in a corner)."""
    x = cell[0]
    y = cell[1]
    if cell not in Edges:
        return [[x-1, y-1], [x-1, y], [x-1, y+1], [x, y+1], [x+1, y+1], [x+1, y], [x+1, y-1], [x, y-1]]
    elif cell == [1, 1]:
        return [[1, 2], [2, 2], [2, 1]]
    elif cell == [1, n]:
        return [[1, n-1], [2, n], [2, n-1]]
    elif cell == [m, n]:
        return [[m, n-1], [m-1, n], [m-1, n-1]]
    elif cell == [m, 1]:
        return [[m, 2], [m-1, 1], [m-1, 2]]
    elif cell in Top_edge:
        return [[x, y-1], [x, y+1], [x+1, y-1], [x+1, y], [x+1, y+1]]
    elif cell in Right_edge:
        return [[x-1, y], [x+1, y], [x-1, y-1], [x, y-1], [x+1, y-1]]
    elif cell in Bottom_edge:
        return [[x, y-1], [x, y+1], [x-1, y-1], [x-1, y], [x-1, y+1]]
    elif cell in Left_edge:
        return [[x-1, y], [x+1, y], [x-1, y+1], [x, y+1], [x+1, y+1]]


NBH = {tuple(c): nbh(c) for c in whole_board}


def extended_nbh(cell):
    """The 8 positions around a cell, in this order:
    0 top-left, 1 up, 2 top-right, 3 right, 4 bottom-right, 5 down, 6 bottom-left, 7 left.
    Positions outside the board are allowed ("imaginary" cells)."""
    x = cell[0]
    y = cell[1]
    return [[x-1, y-1], [x-1, y], [x-1, y+1], [x, y+1], [x+1, y+1], [x+1, y], [x+1, y-1], [x, y-1]]


def edges_of_cell(cell):
    """The four sides of the 3x3 block around a cell: top row, right column, bottom row, left column."""
    neighbors = extended_nbh(cell)
    return [
        [neighbors[0], neighbors[1], neighbors[2]],  # top
        [neighbors[2], neighbors[3], neighbors[4]],  # right
        [neighbors[4], neighbors[5], neighbors[6]],  # bottom
        [neighbors[6], neighbors[7], neighbors[0]],  # left
    ]


# ---------------------------------------------------------------
# Talking to the website
# ---------------------------------------------------------------
BOARD_JS = """
const out = {};
document.querySelectorAll('.square').forEach(e => { out[e.id] = e.className; });
return out;
"""


def read_board():
    """Snapshot of the board: {(row, col): class string}.
    Class strings look like 'square blank', 'square open3', 'square bombflagged'."""
    raw = driver.execute_script(BOARD_JS)
    board = {}
    for cell_id, cls in raw.items():
        parts = cell_id.split('_')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            r, c = int(parts[0]), int(parts[1])
            if 1 <= r <= m and 1 <= c <= n:        # real cells only
                board[(r, c)] = cls
    return board


def leftclick(cell):
    p = driver.find_element(By.ID, f'{cell[0]}_{cell[1]}')
    p.click()


def game_status():
    """'playing', 'lost' or 'won', read from the smiley face."""
    try:
        face = driver.find_element(By.ID, 'face').get_attribute('class')
    except UnexpectedAlertPresentException:
        # A pop-up ("new high score, enter your name") is blocking the page. Dismiss it
        # if it is still open, then ask again.
        try:
            driver.switch_to.alert.dismiss()
        except NoAlertPresentException:
            pass
        face = driver.find_element(By.ID, 'face').get_attribute('class')
    if 'dead' in face:
        return 'lost'
    if 'win' in face:
        return 'won'
    return 'playing'


def fresh_board():
    """Read the page and mark the mines we have found as flagged.
    Returns None if the game is over."""
    if game_status() != 'playing':
        return None
    board = read_board()
    for p in known_mines:
        board[p] = FLAG
    return board


def click_cells(cells):
    """Left-click every cell in `cells`."""
    try:
        for p in cells:
            leftclick(p)
    except Exception:
        # The winning (or losing) click can end the game in the middle of a round.
        # If the game is over, the remaining clicks no longer matter, so stop quietly;
        # if the game is still on, this is a real error, so raise it again.
        if game_status() == 'playing':
            raise


# ---------------------------------------------------------------
# Questions we can ask about a board snapshot.
# Anything outside the board (the "imaginary" cells) is simply not a number
# and not blank, so no special case is needed at the edges.
# ---------------------------------------------------------------
def is_number(board, cell):
    s = board.get(tuple(cell))
    return s is not None and s.startswith('square open')


def is_blank(board, cell):
    return board.get(tuple(cell)) == BLANK


def unoccupied_nbh(board, cell):
    """Blank neighbours of a cell, U(cell)."""
    return [p for p in NBH[tuple(cell)] if is_blank(board, p)]


def flagged_nbh(board, cell):
    return [p for p in NBH[tuple(cell)] if board[tuple(p)] == FLAG]


def remaining_mines(board, cell):
    """r(cell) = number shown - number of flagged neighbours."""
    return int(board[tuple(cell)][-1]) - len(flagged_nbh(board, cell))


def get_boundary(board):
    """The boundary: number cells that still have at least one blank neighbour.
    Only these cells can tell us anything new, so the techniques only look at them."""
    return [c for c in whole_board if is_number(board, c) and unoccupied_nbh(board, c)]


# ---------------------------------------------------------------
# Techniques.  Each takes (cell, board) and returns (cells_to_open, mines_found).
# They only look at the snapshot; nothing is clicked here.
# ---------------------------------------------------------------
def want_to_right_click(cell, board):
    """Simple technique 1: if r(C) == |U(C)|, every blank neighbour is a mine."""
    if not is_number(board, cell):
        return [], []
    U = unoccupied_nbh(board, cell)
    if U and remaining_mines(board, cell) == len(U):
        return [], U
    return [], []


def want_to_left_click(cell, board):
    """Simple technique 2: if r(C) == 0, every blank neighbour is safe."""
    if not is_number(board, cell):
        return [], []
    U = unoccupied_nbh(board, cell)
    if U and remaining_mines(board, cell) == 0:
        return U, []
    return [], []


# For each direction: (index of the neighbour in extended_nbh,
#                      index of that neighbour's far side in edges_of_cell,
#                      index of OUR side facing away from it in edges_of_cell)
#                up        right      down       left
DIRECTIONS = [(1, 0, 2), (3, 1, 3), (5, 2, 0), (7, 3, 1)]


def One_One_cell_teq(cell, board):
    """1-1 technique. cell has r = 1, its neighbour C in some direction also has r = 1,
    and the side of cell facing away from C has no blank cells. Then cell's mine is
    among the cells it shares with C, so C's mine is that same mine, and the blank
    cells on C's far side are safe."""
    if not is_number(board, cell) or remaining_mines(board, cell) != 1:
        return [], []
    to_open = []
    neighbors = extended_nbh(cell)
    eoc = edges_of_cell(cell)
    for nb_index, far_side, opposite_side in DIRECTIONS:      # every direction is checked
        C = neighbors[nb_index]
        if (is_number(board, C) and remaining_mines(board, C) == 1
                and not any(is_blank(board, p) for p in eoc[opposite_side])):
            to_open += [q for q in edges_of_cell(C)[far_side] if is_blank(board, q)]
    return to_open, []


def One_Two_cell_teq(cell, board):
    """1-2 technique (works for any numbers). If r(C) - r(cell) equals the number of
    blank cells on C's far side, then all of those blank cells are mines: the cells C
    shares with `cell` hold at most r(cell) mines, so the rest of C's mines must sit
    on the far side."""
    if not is_number(board, cell):
        return [], []
    r = remaining_mines(board, cell)
    mines = []
    neighbors = extended_nbh(cell)
    for nb_index, far_side, opposite_side in DIRECTIONS:      # (opposite_side is not needed here)
        C = neighbors[nb_index]
        if not is_number(board, C):
            continue
        far_blank = [q for q in edges_of_cell(C)[far_side] if is_blank(board, q)]
        if far_blank and remaining_mines(board, C) - r == len(far_blank):
            mines += far_blank
    return [], mines


# ---------------------------------------------------------------
# The guess (used only when no technique can find a certain move)
# ---------------------------------------------------------------
def best_guess(board):
    """Every number cell C says: "each of my blank neighbours is a mine with
    probability r(C) / |U(C)|". A blank cell touching several numbers gets several
    estimates, and we keep the lowest one. Returns the blank cell with the lowest
    estimate, and that estimate: (cell, probability). (None, None) if there is none."""
    risk = {}
    for cell in get_boundary(board):
        U = unoccupied_nbh(board, cell)
        p = remaining_mines(board, cell) / len(U)
        for q in U:
            q = tuple(q)
            if q not in risk or p < risk[q]:
                risk[q] = p
    if not risk:
        return None, None
    cell = min(risk, key=risk.get)
    return cell, risk[cell]


def guess():
    """Click the blank cell that looks least likely to be a mine.
    Returns True if a cell was clicked."""
    board = fresh_board()
    if board is None:
        return False
    cell, probability = best_guess(board)
    if cell is None:
        return False
    print(f"guess: {cell} with estimated mine probability {probability:.2f}")
    click_cells([cell])
    return True


# ---------------------------------------------------------------
# Stages
# ---------------------------------------------------------------
def run_stage(rule, name):
    """One round of ONE technique over the boundary:
    read the board, ask `rule` about every boundary cell, then click what it found.
    Returns True if the technique found something (the board changed).

    Reading a fresh board here also means any cells the game opened for us
    (the automatic clearing around a 0) are always seen before we decide anything."""
    board = fresh_board()
    if board is None:
        return False
    to_open, new_mines = set(), set()                     # sets: a cell deduced twice is used once
    for cell in get_boundary(board):
        opens, mines = rule(cell, board)
        to_open.update(tuple(p) for p in opens)
        new_mines.update(tuple(p) for p in mines)
    conflict = to_open & new_mines
    if conflict:
        print("Warning: contradictory deductions (a wrong mine?) for", sorted(conflict))
        to_open -= conflict                               # never open a cell we also think is a mine
    if not (to_open or new_mines):
        return False
    print(f"{name}: mines found {len(new_mines)}, opening {len(to_open)}")
    known_mines.update(new_mines)
    click_cells(to_open)
    return True


def repeat_stage(rule, name):
    """Run a stage again and again until it no longer changes the board.
    Returns True if it changed the board at least once."""
    changed = False
    while run_stage(rule, name):
        changed = True
    return changed


def process_cells():
    known_mines.clear()
    guesses = 0
    leftclick(FIRST_CLICK)                                # first click is always safe on this site
    while True:
        # Stage 1: flag rule, repeated until it stops working.
        repeat_stage(want_to_right_click, "stage 1 flag rule")
        # Stage 2: open rule, repeated until it stops working.
        # If it changed anything, go back to stage 1 (new numbers may allow new mines).
        if repeat_stage(want_to_left_click, "stage 2 open rule"):
            continue
        # Stage 3: 1-1 technique on every boundary cell. If it changed the board, back to stage 1.
        if run_stage(One_One_cell_teq, "stage 4 1-1 technique"):
            continue
        # Stage 4: 1-2 technique. If it changed the board, back to stage 1.
        if run_stage(One_Two_cell_teq, "stage 5 1-2 technique"):
            continue
        # Stage 5: nothing is certain. Guess, then go back to stage 1 with the new number.
        if guess():
            guesses += 1
            continue
        break                                             # game over (or nothing left to try)

    print("Game status:", game_status())
    print("Mines found:", len(known_mines), "| Guesses made:", guesses)


# ---------------------------------------------------------------
# Program entry
# ---------------------------------------------------------------
def get_user_input(prompt, valid_responses):
    while True:
        response = input(prompt).strip().lower()
        if response in valid_responses:
            return response
        print(f"Invalid input. Please type one of the following: {', '.join(valid_responses)}")


def main():
    global driver
    options = webdriver.ChromeOptions()
    # When a game is won the site may pop up "new high score, enter your name".
    # Dismiss pop-ups automatically so they never block the program.
    options.set_capability('unhandledPromptBehavior', 'dismiss')
    driver = webdriver.Chrome(options=options)
    driver.get('https://minesweeperonline.com/')

    while True:
        process_cells()
        proceed = get_user_input("Do you want to restart or exit the program (Y/Exit): ", {'y', 'exit'})
        if proceed == 'y':
            driver.find_element(By.ID, 'face').click()   # smiley face = new game
        else:
            driver.quit()
            break


if __name__ == '__main__':
    main()
