import re
import unittest
from pathlib import Path


FIRMWARE_DIR = Path(__file__).resolve().parents[1]


class DriverBehaviorMappingTests(unittest.TestCase):
    def test_every_model_class_has_an_explicit_ftms_mapping(self):
        preprocessing = (FIRMWARE_DIR / "driver_behavior_preprocessing.h").read_text()
        firmware = (FIRMWARE_DIR / "FTMS_LILYGO_002_PHASE2.ino").read_text()

        class_block = re.search(
            r"driver_behavior_class_names\[\]\s*=\s*\{(?P<body>.*?)\};",
            preprocessing,
            re.DOTALL,
        )
        self.assertIsNotNone(class_block)
        classes = re.findall(r'"([^"]+)"', class_block.group("body"))
        self.assertEqual(
            classes,
            [
                "sudden_acceleration",
                "sudden_braking",
                "sudden_left_turn",
                "sudden_right_turn",
            ],
        )

        mapping_function = firmware.split("String currentDrivingEventJson()", 1)[1].split(
            "// JSON HELPERS", 1
        )[0]
        expected_literals = {
            "sudden_acceleration": ("SUDDEN_ACCELERATION", "HARSH_ACCELERATION"),
            "sudden_braking": ("SUDDEN_BRAKING", "HARSH_BRAKING"),
            "sudden_left_turn": ("SUDDEN_LEFT_TURN", "SHARP_TURN"),
            "sudden_right_turn": ("SUDDEN_RIGHT_TURN", "SHARP_TURN"),
        }
        for model_class in classes:
            with self.subTest(model_class=model_class):
                normalized, ftms_event = expected_literals[model_class]
                self.assertIn(f'normalized == "{normalized}"', mapping_function)
                self.assertIn(f'"\\\"{ftms_event}\\\""', mapping_function)

        self.assertNotIn('"NORMAL"', mapping_function)
        self.assertRegex(mapping_function, r'return\s+"null";\s*}')


if __name__ == "__main__":
    unittest.main()
