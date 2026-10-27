import unittest
from dataclasses import FrozenInstanceError

from mini_agent.config import OLLAMA_BASE_URL, Config, ConfigError, load_config


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

    def test_config_is_immutable(self) -> None:
        config = Config(model="m")
        with self.assertRaises(FrozenInstanceError):
            config.model = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()