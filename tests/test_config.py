import unittest
from dataclasses import FrozenInstanceError

from mini_agent.config import OLLAMA_BASE_URL, ConfigError, load_config, Config


def base_env(**overrides: str) -> dict[str, str]:
    env = {"MINIAGENT_MODEL": "qwen3.5:9b"}
    env.update(overrides)
    return env


class TestLoadConfig(unittest.TestCase):
    def test_ollama_defaults(self) -> None:
        config = load_config(base_env())
        self.assertEqual(config.model, "qwen3.5:9b")
        self.assertEqual(config.base_url, OLLAMA_BASE_URL)
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.timeout, 120.0)
        self.assertEqual(config.reasoning_effort, "none")

    def test_custom_base_url_and_key(self) -> None:
        config = load_config(
            base_env(
                MINIAGENT_BASE_URL="https://api.example.com/v1/",
                MINIAGENT_API_KEY="sk-test",
            )
        )
        self.assertEqual(config.base_url, "https://api.example.com/v1")
        self.assertEqual(config.api_key, "sk-test")

    def test_missing_model_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MODEL=""))

    def test_invalid_timeout_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_TIMEOUT="abc"))

    def test_non_positive_timeout_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_TIMEOUT="0"))

    def test_repr_hides_api_key(self) -> None:
        config = load_config(base_env(MINIAGENT_API_KEY="sk-test"))
        self.assertNotIn("sk-test", repr(config))

    def test_run_limits_defaults(self) -> None:
        config = load_config(base_env())
        self.assertEqual(config.max_steps, 10)
        self.assertEqual(config.max_consecutive_invalid, 3)
        self.assertEqual(config.max_duplicate_calls, 3)

    def test_run_limits_from_env(self) -> None:
        config = load_config(
            base_env(
                MINIAGENT_MAX_STEPS="5",
                MINIAGENT_MAX_CONSECUTIVE_INVALID="2",
                MINIAGENT_MAX_DUPLICATE_CALLS="1",
            )
        )
        self.assertEqual(config.max_steps, 5)
        self.assertEqual(config.max_consecutive_invalid, 2)
        self.assertEqual(config.max_duplicate_calls, 1)

    def test_invalid_max_steps_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_STEPS="0"))
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_STEPS="abc"))
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_CONSECUTIVE_INVALID="0"))
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_DUPLICATE_CALLS="0"))

    def test_config_is_immutable(self) -> None:
        config = Config(model="m")
        with self.assertRaises(FrozenInstanceError):
            config.model = "other"  # type: ignore[misc]

    def test_tool_config_defaults(self) -> None:
        config = load_config(base_env())
        self.assertEqual(config.workspace, "workspace")
        self.assertEqual(config.max_tool_output_chars, 20000)

    def test_tool_config_from_env(self) -> None:
        config = load_config(
            base_env(
                MINIAGENT_WORKSPACE="sandbox",
                MINIAGENT_MAX_TOOL_OUTPUT_CHARS="1000",
            )
        )
        self.assertEqual(config.workspace, "sandbox")
        self.assertEqual(config.max_tool_output_chars, 1000)

    def test_invalid_max_tool_output_chars(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_TOOL_OUTPUT_CHARS="0"))
        with self.assertRaises(ConfigError):
            load_config(base_env(MINIAGENT_MAX_TOOL_OUTPUT_CHARS="abc"))

if __name__ == "__main__":
    unittest.main()