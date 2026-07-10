from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThndrFeeModel:
    brokerage_rate: float = 0.001      # 0.1%
    brokerage_min_egp: float = 1.5
    egx_transaction_rate: float = 0.000125   # 0.0125%
    egx_mcdr_sell_rate: float = 0.00005      # 0.005%

    def buy_fees(self, notional_egp: float) -> float:
        brokerage = max(self.brokerage_min_egp, notional_egp * self.brokerage_rate)
        egx_tx = notional_egp * self.egx_transaction_rate
        return brokerage + egx_tx

    def sell_fees(self, notional_egp: float) -> float:
        brokerage = max(self.brokerage_min_egp, notional_egp * self.brokerage_rate)
        egx_tx = notional_egp * self.egx_transaction_rate
        egx_mcdr = notional_egp * self.egx_mcdr_sell_rate
        return brokerage + egx_tx + egx_mcdr

    def round_trip_fees(self, entry_notional_egp: float, exit_notional_egp: float | None = None) -> float:
        exit_value = exit_notional_egp if exit_notional_egp is not None else entry_notional_egp
        return self.buy_fees(entry_notional_egp) + self.sell_fees(exit_value)

    def break_even_move_pct(self, entry_notional_egp: float) -> float:
        """
        Approximate required price move percentage to cover buy+sell fees.
        """
        if entry_notional_egp <= 0:
            return 0.0
        fees = self.round_trip_fees(entry_notional_egp)
        return fees / entry_notional_egp * 100.0
