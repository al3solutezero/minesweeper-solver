# Minesweeper Solver

A Python project that automates Minesweeper gameplay using Selenium on Chrome on website: https://minesweeperonline.com/

## Features

- Reads the board state from the browser.
- Identifies and flags mines using logical deductions.
- Applies pattern-based strategies, including 1-1 and 1-2 patterns.
- Uses a probabilistic decision to select the best cell when deterministic deductions are unavailable.

## Requirements

- Python 3
- Google Chrome
- Selenium

## Installation

Install the required Python package:

```bash
python -m pip install -r requirements.txt
```

## Usage

Run the solver with:

```bash
python minesweeper_solver.py
```

The program launches Chrome and interacts with the Minesweeper game.

## Limitations

The solver does not guarantee a win. Some board positions require guessing, and the current guess may select a cell that contains a mine.

## Future Improvements

- Improve guess selection by considering both mine probability and information gain.
- Benchmark performance across many boards.