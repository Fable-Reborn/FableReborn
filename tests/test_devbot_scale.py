import unittest

from utils.devbot_scale import DEV_BOT_OPERATORS, scale_argv


class TestDevBotScale(unittest.TestCase):
    def test_start_and_stop_only_touch_the_dev_deployment(self):
        start = scale_argv(1)
        stop = scale_argv(0)
        self.assertEqual(start[-1], "--replicas=1")
        self.assertEqual(stop[-1], "--replicas=0")
        for argv in (start, stop):
            self.assertEqual(
                argv,
                ["sudo", "-n", "k3s", "kubectl", "-n", "fable", "scale", "deploy/fable-bot-dev", argv[-1]],
            )
            self.assertIn("deploy/fable-bot-dev", argv)
            self.assertNotIn("deploy/fable-bot", argv)

    def test_replicas_above_one_are_rejected(self):
        for replicas in (2, -1, 3, True, False):
            with self.assertRaises(ValueError):
                scale_argv(replicas)

    def test_only_nut_and_lunar(self):
        self.assertEqual(DEV_BOT_OPERATORS, frozenset({
            273652235588599808,
            295173706496475136,
        }))


if __name__ == "__main__":
    unittest.main()
