
# Flight-Slate LED matrix configuration (safe to commit if it contains no secrets).
# Usage:
#   source .venv/bin/activate
#   source ./env.flight-slate.sh
#   sudo -E env "PATH=$PATH" python core_ui_demo.py

# --- Required for Adafruit RGB Matrix Bonnet/HAT wiring ---
export FLIGHT_SLATE_HARDWARE_MAPPING=adafruit-hat

# --- Panel geometry ---
# Your physical panel is 128x64, but it behaves like 2 chained 64x64 halves.
export FLIGHT_SLATE_MATRIX_ROWS=64
export FLIGHT_SLATE_MATRIX_COLS=64
export FLIGHT_SLATE_MATRIX_CHAIN=2
export FLIGHT_SLATE_MATRIX_PARALLEL=1

# --- Brightness and refresh ---
export FLIGHT_SLATE_MATRIX_BRIGHTNESS=80
export FLIGHT_SLATE_REFRESH_HZ=120

# --- Panel chipset init sequence (fixes “all black” on some panels) ---
export FLIGHT_SLATE_LED_PANEL_TYPE=FM6127

# --- Timing stability knobs (Pi 4 often needs slowdown) ---
export FLIGHT_SLATE_LED_GPIO_SLOWDOWN=4

# --- Optional: if you see “blank bars” or weird scan artifacts ---
# Try values: 5, 3, 1. Use -1 to disable/return to library defaults.
# export FLIGHT_SLATE_LED_ROW_ADDR_TYPE=5

# Try values 0..17 if row-addr-type alone doesn’t fix it. Use -1 to disable.
# export FLIGHT_SLATE_LED_MULTIPLEXING=-1

# If colors are swapped (e.g. red/green), try: RGB, RBG, GRB, GBR, BRG, BGR
# export FLIGHT_SLATE_LED_RGB_SEQUENCE=RGB

# --- Optional: quality/performance knobs ---
# 11 = best color depth; lowering can improve refresh on some setups.
# export FLIGHT_SLATE_MATRIX_PWM_BITS=11

# Default in rgbmatrix is often ~130; higher can reduce ghosting, lower can speed up.
# export FLIGHT_SLATE_LED_PWM_LSB_NANOSECONDS=130

# --- Optional: Map page (DON'T COMMIT real tokens) ---
# export MAPBOX_TOKEN=

