# SPDX-License-Identifier: AGPL-3.0-only
"""Evidence coverage and integrity checks, independent of any model provider."""

import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from farmcredit.adapters.demo import DEMO_RECORDED_ON, load_demo_case, load_demo_evidence
from farmcredit.application.assess_evidence import assess_sourced_case, case_inputs
from farmcredit.domain.evidence import EvidenceBasis, EvidenceRecord, InputValue, review_evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.case = load_demo_case()
        self.records = load_demo_evidence()

    def test_complete_demo_sources_preserve_calculation(self):
        assessment = assess_sourced_case(self.case, self.records, as_of=DEMO_RECORDED_ON)
        self.assertEqual(assessment.issues, ())
        self.assertEqual(assessment.cashflow.cash_after_repayment, Decimal("40000"))
        self.assertTrue(all(record.synthetic for record in assessment.records))
        self.assertTrue(all(record.basis == EvidenceBasis.ASSUMED for record in assessment.records))

    def test_each_calculator_input_has_a_snapshot(self):
        fields = {record.input.field for record in self.records}
        self.assertEqual(len(fields), 12 + 2 * len(self.case.other_movements))
        self.assertIn("sale.price_per_kg", fields)
        self.assertIn("financing.charges", fields)
        for movement in self.case.other_movements:
            self.assertIn(f"cash/{movement.record_id}/amount", fields)
            self.assertIn(f"cash/{movement.record_id}/on", fields)

    def test_missing_source_blocks_calculation(self):
        with patch("farmcredit.application.assess_evidence.assess_case") as calculate:
            assessment = assess_sourced_case(self.case, self.records[1:], as_of=DEMO_RECORDED_ON)
        calculate.assert_not_called()
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].reason, "missing source")

    def test_different_sources_are_not_silently_resolved(self):
        original = next(
            record for record in self.records if record.input.field == "sale.price_per_kg"
        )
        conflicting = replace(
            original,
            record_id="other-quote",
            source="Another worksheet",
            input=replace(original.input, value=Decimal("50")),
        )
        assessment = assess_sourced_case(
            self.case, (*self.records, conflicting), as_of=DEMO_RECORDED_ON
        )
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].reason, "conflicting sources")
        self.assertEqual(assessment.issues[0].record_ids, (original.record_id, "other-quote"))
        self.assertIn(conflicting, assessment.records)

    def test_agreeing_sources_are_preserved(self):
        extra = replace(self.records[0], record_id="second-record", source="Second source")
        assessment = assess_sourced_case(self.case, (*self.records, extra), as_of=DEMO_RECORDED_ON)
        self.assertEqual(assessment.issues, ())
        self.assertEqual(len(assessment.records), len(self.records) + 1)

    def test_case_change_does_not_reuse_old_source_value(self):
        changed = replace(self.case, sale=replace(self.case.sale, price_per_kg=Decimal("50")))
        assessment = assess_sourced_case(changed, self.records, as_of=DEMO_RECORDED_ON)
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].field, "sale.price_per_kg")
        self.assertEqual(assessment.issues[0].reason, "source does not match current input")

    def test_wrong_units_block_calculation(self):
        original = next(
            record for record in self.records if record.input.field == "sale.price_per_kg"
        )
        wrong = replace(original, input=replace(original.input, unit="KES/90kg bag"))
        records = tuple(wrong if record == original else record for record in self.records)
        assessment = assess_sourced_case(self.case, records, as_of=DEMO_RECORDED_ON)
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].reason, "source does not match current input")

    def test_future_source_date_is_not_confused_with_planned_event_date(self):
        future_record = replace(self.records[0], recorded_on=date(2026, 10, 6))
        assessment = assess_sourced_case(
            self.case, (future_record, *self.records[1:]), as_of=DEMO_RECORDED_ON
        )
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].reason, "recorded after review date")

    def test_duplicate_ids_and_unknown_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate evidence"):
            assess_sourced_case(self.case, (*self.records, self.records[0]), as_of=DEMO_RECORDED_ON)
        unknown = replace(
            self.records[0],
            record_id="unknown",
            input=InputValue("wrong_field", Decimal("1"), "KES"),
        )
        assessment = assess_sourced_case(
            self.case, (*self.records, unknown), as_of=DEMO_RECORDED_ON
        )
        self.assertIsNone(assessment.cashflow)
        self.assertEqual(assessment.issues[0].reason, "unknown input")

    def test_unknown_value_is_not_zero_but_confirmed_zero_is_valid(self):
        with self.assertRaises(ValueError):
            InputValue("amount", None, "KES")
        zero = InputValue("amount", Decimal("0"), "KES")
        record = EvidenceRecord(
            "zero", zero, "Declared balance", DEMO_RECORDED_ON, EvidenceBasis.DECLARED, False
        )
        self.assertEqual(review_evidence([zero], [record], as_of=DEMO_RECORDED_ON), ())

    def test_metadata_is_required_and_input_snapshots_are_not_mutable(self):
        for changes in (
            {"source": ""},
            {"recorded_on": None},
            {"basis": "observed"},
            {"synthetic": None},
            {"record_id": " padded "},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.records[0], **changes)
        with self.assertRaises(AttributeError):
            self.records[0].input.value = Decimal("0")

    def test_duplicate_case_fields_cannot_hide_missing_evidence(self):
        inputs = case_inputs(self.case)
        with self.assertRaisesRegex(ValueError, "Duplicate input"):
            review_evidence((*inputs, inputs[0]), self.records, as_of=DEMO_RECORDED_ON)
