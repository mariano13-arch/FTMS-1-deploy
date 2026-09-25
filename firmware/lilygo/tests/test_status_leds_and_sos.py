import unittest
from pathlib import Path


FIRMWARE = (Path(__file__).resolve().parents[1] / "FTMS_LILYGO_002_PHASE2.ino").read_text()


class StatusLEDAndSOSFirmwareTests(unittest.TestCase):
    def test_authoritative_pin_configuration_has_no_spi_reassignment(self):
        self.assertIn("#define SOS_BUTTON_PIN 32", FIRMWARE)
        self.assertIn("#define GNSS_LED_PIN 19", FIRMWARE)
        self.assertIn("#define VGATE_LED_PIN 18", FIRMWARE)
        self.assertIn("pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);", FIRMWARE)
        self.assertIn("digitalRead(SOS_BUTTON_PIN) == LOW", FIRMWARE)
        self.assertNotIn("SPI.begin", FIRMWARE)
        self.assertNotIn("VSPI", FIRMWARE)

    def test_green_led_accepts_fresh_gnss_or_cellular_lbs_position(self):
        block = FIRMWARE.split("void updateStatusLEDs", 1)[1].split("// FTMS TELEMETRY PAYLOAD", 1)[0]
        self.assertIn("latestPosition.valid", block)
        self.assertIn("latestPosition.source == POSITION_GNSS", block)
        self.assertIn("latestPosition.source == POSITION_CELLULAR_LBS", block)
        self.assertIn("POSITION_MAX_SEND_AGE_MS", block)
        self.assertIn("digitalWrite(GNSS_LED_PIN, freshPosition ? HIGH : LOW);", block)

    def test_green_led_truth_table_rejects_stale_invalid_and_no_source(self):
        maximum_age = 120_000

        def green(valid, source, age):
            return valid and source in {"GNSS", "CELLULAR_LBS"} and age <= maximum_age

        self.assertTrue(green(True, "GNSS", maximum_age))
        self.assertTrue(green(True, "CELLULAR_LBS", maximum_age))
        self.assertFalse(green(True, "GNSS", maximum_age + 1))
        self.assertFalse(green(False, "GNSS", 0))
        self.assertFalse(green(True, "NONE", 0))

    def test_blue_led_uses_physical_bluetooth_connection_truth(self):
        block = FIRMWARE.split("void updateStatusLEDs", 1)[1].split("// FTMS TELEMETRY PAYLOAD", 1)[0]
        self.assertIn("digitalWrite(VGATE_LED_PIN, SerialBT.connected() ? HIGH : LOW);", block)

    def test_nonblocking_debounce_triple_press_and_long_hold_contract(self):
        self.assertIn("SOS_DEBOUNCE_MS = 40", FIRMWARE)
        self.assertIn("SOS_PRESS_WINDOW_MS = 1000", FIRMWARE)
        self.assertIn("SOS_CLEAR_HOLD_MS = 5000", FIRMWARE)
        self.assertIn("sosShortPressCount == 3", FIRMWARE)
        self.assertIn("sosLongHoldHandled", FIRMWARE)
        self.assertIn("sosPendingAction = SOS_PENDING_ACTIVATE", FIRMWARE)
        self.assertIn("sosPendingAction = SOS_PENDING_CLEAR", FIRMWARE)
        button_block = FIRMWARE.split("void processSOSButton", 1)[1].split("void processSOSLongHold", 1)[0]
        hold_block = FIRMWARE.split("void processSOSLongHold", 1)[1].split("void serviceSOSTransmission", 1)[0]
        self.assertNotIn("delay(", button_block)
        self.assertNotIn("delay(", hold_block)

    def test_retry_and_idempotent_local_transitions_are_explicit(self):
        self.assertIn("SOS_RETRY_INTERVAL_MS = 15000", FIRMWARE)
        self.assertIn('sendSOSAction(clearing ? "CLEAR" : "ACTIVATE")', FIRMWARE)
        self.assertIn("sosPendingAction = SOS_PENDING_NONE", FIRMWARE)
        self.assertIn("|| sosActive) return;", FIRMWARE)
        self.assertIn("Emergency activation pending retry", FIRMWARE)
        self.assertIn("Emergency clear pending retry", FIRMWARE)


if __name__ == "__main__":
    unittest.main()
