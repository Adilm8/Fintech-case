"""Unit and integration tests for IIK _diff_positions threshold (<=4 chars vs full replacement)."""

from __future__ import annotations

from app.risk.engine import _diff_positions, check_payment
from app.schemas import CheckRequest
from app.store import Store
from app.validators.kz import make_iik


class TestDiffPositions:
    def test_identical_strings_return_empty(self) -> None:
        iik = "KZ246010005016525808"
        assert _diff_positions(iik, iik) == []

    def test_up_to_four_differing_positions_are_returned(self) -> None:
        history = "KZ246010005016525808"
        assert _diff_positions("KZ246010005016525809", history) == [19]
        assert _diff_positions("KZ246010005016525899", history) == [18, 19]
        assert _diff_positions("KZ996010005016525809", history) == [2, 3, 19]
        assert _diff_positions("KZ996010005016525899", history) == [2, 3, 18, 19]

    def test_five_or_more_differing_positions_return_empty(self) -> None:
        history = "KZ246010005016525808"
        # Exactly 5 positions differ -> []
        assert _diff_positions("KZ996010005016525999", history) == []
        # Full replacement across banks (17 positions differ) -> []
        assert _diff_positions("KZ51856KZT2486117574", history) == []
        # Different account at another bank (12 positions differ) -> []
        assert _diff_positions("KZ509650006872032298", "KZ599980004227133320") == []

    def test_different_lengths_respect_four_char_threshold(self) -> None:
        assert _diff_positions("KZ24601000501652580812", "KZ246010005016525808") == [20, 21]
        assert _diff_positions("KZ24601000501652580812345", "KZ246010005016525808") == []
        assert _diff_positions("KZ2460100050165", "KZ246010005016525808") == []

    def test_check_payment_returns_positions_for_small_iik_diff_and_empty_for_full_diff(
        self,
    ) -> None:
        store = Store()
        green_item = next(q for q in store.queue if q["scenario"] == "green")
        base_req = CheckRequest(
            payer_id=green_item["payer_id"],
            recipient_name=green_item["recipient_name"],
            recipient_bin=green_item["recipient_bin"],
            recipient_iik=green_item["recipient_iik"],
            recipient_bik=green_item["recipient_bik"],
            amount_kzt=green_item["amount_kzt"],
            purpose=green_item["purpose"],
        )

        # Small change in the same bank (<=4 differing chars: check digits + last digit)
        small_diff_iik = make_iik("601", "0005016525809")
        small_res = check_payment(
            base_req.model_copy(update={"recipient_iik": small_diff_iik}),
            store,
        )
        small_iik_row = next(d for d in small_res.comparison if d.field == "iik")
        assert small_iik_row.differs is True
        assert 1 <= len(small_iik_row.diff_positions) <= 4
        assert 19 in small_iik_row.diff_positions

        # Completely different account at the same bank (>4 differing chars)
        full_diff_iik = make_iik("601", "0009876543210")
        full_res = check_payment(
            base_req.model_copy(update={"recipient_iik": full_diff_iik}),
            store,
        )
        full_iik_row = next(d for d in full_res.comparison if d.field == "iik")
        assert full_iik_row.differs is True
        assert full_iik_row.diff_positions == []
