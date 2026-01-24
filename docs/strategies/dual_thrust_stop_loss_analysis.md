# Dual Thrust Stop Loss Priority Analysis

## 1. Overview
This analysis evaluates the interaction between two stop-loss mechanisms within the Nautilus-based trading framework:
1.  **Base-level forced stop-loss**: A percentage-based fallback implemented in `strategy/base.py`.
2.  **Strategy-level custom stop-loss**: A strategy-specific stop (e.g., ATR-based stop in `strategy/dual_thrust.py`).

The goal was to determine if these mechanisms conflict during backtests, establish clear priority rules, and implement a safe, reliable coordination system.

## 2. Key Facts & Discoveries
*   **Initial Conflicts**:
    *   `BaseStrategy` originally created a stop-market order immediately on `on_position_opened`.
    *   `DualThrust` created its own ATR-based stop-market order on entry.
    *   Without coordination, if one stop triggered and closed the position, the remaining "ghost" stop order could later trigger and cause an unintended reverse position open (especially if `reduce_only=False`).
*   **Runtime Evidence**:
    *   Observed `OrderRejected` errors when using `reduce_only=True` due to position state sync timing in the engine.
    *   Observed redundant SL orders being submitted when both base and strategy levels acted independently.
*   **Attribute Issues**: Identified that stop order objects used `order_type` instead of `.type`.

## 3. Implementation Details & Fixes
*   **Lifecycle Management**: Moved base auto-SL management from `on_position_opened` to the `on_bar` lifecycle (specifically in `_manage_auto_stop_loss()`). This ensures the position is fully registered before the SL is placed.
*   **Redundancy Check**: `BaseStrategy` now checks for any existing stop orders on the instrument before placing its fallback SL.
*   **Cleanup**: Added logic to `on_position_closed` to immediately cancel all pending orders for that instrument, preventing "ghost" orders from triggering later.
*   **Configuration**: Introduced a `use_auto_sl` boolean flag in the base config. `DualThrust` disables this (sets to `False`) to prioritize its own ATR SL.
*   **Super Call**: Ensured all strategies call `super().on_bar(bar)` to maintain base risk management functionality.

## 4. Priority Policy
The following priority rules are now established:
1.  **Strategy-level stops (High Priority)**: If a strategy (like DualThrust) submits its own stop order (e.g., ATR-based), this takes precedence.
2.  **Base-level fallback (Low Priority)**: The percentage-based auto-SL acts as a safety net. It is only created if:
    *   `use_auto_sl` is enabled.
    *   No other stop orders currently exist for the instrument.
3.  **Position Closure (Absolute Priority)**: When a position is closed (for any reason), all associated orders are cancelled to ensure the state is cleared.

## 5. Safety Improvements
*   **Reverse Position Prevention**: By cancelling all orders on position close, we prevent the "double trigger" scenario where a second stop order opens an opposite trade.
*   **Timing Robustness**: Moving SL submission to the bar lifecycle reduces race conditions between order execution and position status updates.
*   **Hedged/Non-Hedged Compatibility**: Adjusted `reduce_only` handling to minimize rejections in backtesting environments while maintaining safety via explicit order management.

## 6. Action Items & Next Steps
- [x] Implement `_manage_auto_stop_loss()` in `BaseStrategy`.
- [x] Implement order cleanup in `on_position_closed`.
- [x] Add `use_auto_sl` config flag.
- [x] Fix attribute access (`.order_type`) and logging issues.
- [ ] Run full-duration backtests to ensure performance stability.
- [ ] Add unit tests for auto-SL skipping and cleanup logic.
- [ ] Document `use_auto_sl` settings for each strategy in the repository README.