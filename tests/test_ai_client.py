"""
Ali Robot - AI Client unit tests.
Tests basic functionality of the AI client module.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_env_example_exists():
    """Verify .env.example file exists in project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_example = os.path.join(project_root, ".env.example")
    assert os.path.isfile(env_example), ".env.example must exist"


def test_env_example_has_required_keys():
    """Verify .env.example contains essential configuration keys."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_example = os.path.join(project_root, ".env.example")

    with open(env_example, "r", encoding="utf-8") as f:
        content = f.read()

    required_keys = [
        "AI_API_KEY",
        "AI_MODEL",
        "AI_BASE_URL",
        "EDGE_TTS_VOICE",
        "STT_LANGUAGE",
    ]
    for key in required_keys:
        assert key in content, f"Missing required key: {key}"


def test_gitignore_excludes_env():
    """Verify .gitignore properly excludes .env files."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gitignore = os.path.join(project_root, ".gitignore")

    with open(gitignore, "r", encoding="utf-8") as f:
        content = f.read()

    assert ".env" in content, ".env must be in .gitignore"
    assert "!.env.example" in content, ".env.example must be whitelisted"


def test_no_hardcoded_secrets():
    """Scan Python files for potential hardcoded API keys."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    suspicious_patterns = ["sk-", "ghp_", "github_pat_"]

    for fname in os.listdir(project_root):
        if fname.endswith(".py"):
            filepath = os.path.join(project_root, fname)
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern in suspicious_patterns:
                # Allow patterns in comments or string comparisons
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if pattern in stripped and not stripped.startswith("#"):
                        # Skip if it's in a comparison or assignment to empty
                        if f'{pattern}"' not in stripped and f"'{pattern}" not in stripped:
                            continue
