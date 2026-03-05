# Dagestan Development Environment Setup
# Usage: bash dev_setup.sh
set -e

echo "[Dagestan] Setting up local development environment..."

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing core and dev dependencies..."
if [ -f "pyproject.toml" ]; then
    pip install -e ".[dev,openai,anthropic]"
else
    echo "pyproject.toml not found! Exiting."
    exit 1
fi

echo "\n[Dagestan] Setup complete!"
echo "To activate your environment:"
echo "  source .venv/bin/activate"
echo "To run tests:"
echo "  pytest tests/"
echo "To check formatting:"
echo "  black dagestan/ tests/"
echo "To lint:"
echo "  flake8 dagestan/ tests/"
